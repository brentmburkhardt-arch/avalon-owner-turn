"""Fixed one-shot 43↔43 source exchange. Never touches private custody or .storage."""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from package_io import directories, regular, inventory, load, extract, sync_dir, write_new
from ha_inspect import inspect, VERSION, BASE_VERSION

ROOT=Path('/homeassistant')
WORK=ROOT/'.avalon-ha-2026104-recovery-v1'
LIVE=ROOT/'custom_components/llama_cpp'
PAYLOAD=Path('/opt/avalon-ha-recovery/payload')
OPERATIONS=('preflight','prepare','install','verify','remove','verify-removed')

def expect(which):
    return load(PAYLOAD/('HA_'+which+'_FILES.json'))

def live_verify_at(root,expected):
    files={p.removeprefix('llama_cpp/'):h for p,h in expected.items()}
    directories(root)
    if not root.is_dir():raise ValueError('Missing accepted integration')
    actual=inventory(root)
    for name in list(actual):
        p=Path(name)
        if p.parent.name=='__pycache__' and p.suffix=='.pyc':
            stem=p.name.removesuffix('.pyc').removesuffix('.opt-1').removesuffix('.opt-2')
            if not stem.endswith('.cpython-314'):raise ValueError('Unexpected cache')
            source=(p.parent.parent/(stem.removesuffix('.cpython-314')+'.py')).as_posix()
            if source not in files:raise ValueError('Unexpected cache source')
            del actual[name]
    if actual!=files:raise ValueError('Source inventory mismatch')

def live_verify(expected):
    live_verify_at(LIVE,expected)

def preserve_metadata(source,target):
    # Same 43-file shape; preserve ownership and modes instead of changing application identity.
    for dst in [target,*target.rglob('*')]:
        src=source/dst.relative_to(target)
        st=src.lstat()
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise ValueError('Metadata source type')
        os.chown(dst,st.st_uid,st.st_gid,follow_symlinks=False)
        os.chmod(dst,stat.S_IMODE(st.st_mode),follow_symlinks=False)

def selected(operation):
    row=inspect()
    if row['safe_mode']:raise ValueError('Safe mode')
    expected=VERSION if operation=='verify' else BASE_VERSION
    if operation=='remove':
        if row['custom_version'] not in (BASE_VERSION,VERSION):raise ValueError('Custom selection mismatch')
    elif row['custom_version']!=expected:raise ValueError('Custom selection mismatch')
    if operation=='verify' and row['state']!='loaded':raise ValueError('Candidate not loaded')
    return row

def backup_gate():
    row=load(WORK/'owner-backup.json')
    flags={'manual_completed','configuration_included','database_exclusion_off','successful','downloaded_off_appliance','recovery_material_available'}
    if set(row)!=flags|{'core_version','bytes','sha256','completed_at','rollback_sha256','rollback_reviewed'} or any(row[k] is not True for k in flags):raise ValueError('Backup receipt')
    import re,datetime
    if row['rollback_sha256']!='35896633124ca9baef9b9f53706fba520acacc1c683d8bf95e4387740e50a189' or row['rollback_reviewed'] is not True:raise ValueError('Reviewed rollback required')
    if row['core_version']!='2026.10.4' or type(row['bytes']) is not int or row['bytes']<=0:raise ValueError('Backup receipt')
    if type(row['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}',row['sha256']):raise ValueError('Backup receipt')
    if datetime.datetime.fromisoformat(row['completed_at']).tzinfo is None:raise ValueError('Backup time')

def exchange(a,b):
    """Linux atomic exchange: no absent/mixed loader-tree window, no deletion."""
    libc=ctypes.CDLL(None,use_errno=True)
    fn=libc.renameat2;fn.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];fn.restype=ctypes.c_int
    if fn(-100,os.fsencode(a),-100,os.fsencode(b),2)!=0:raise OSError('Atomic source exchange failed')
    sync_dir(a.parent);sync_dir(b.parent)

def durable_tree(path):
    for p in sorted((p for p in path.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync_dir(p)
    sync_dir(path);sync_dir(path.parent)

def execute(operation):
    if operation not in OPERATIONS:raise ValueError('Fixed operation required')
    directories(ROOT);regular(ROOT/'configuration.yaml')
    selected(operation)
    if operation=='preflight':
        live_verify(expect('BASELINE'));return 'accepted_custom_no_writes'
    if operation=='prepare':
        live_verify(expect('BASELINE'))
        if WORK.exists() or WORK.is_symlink():raise ValueError('Existing preparation; preserve state')
        WORK.mkdir(mode=0o700);sync_dir(ROOT)
        return 'work_directory_ready_for_fresh_backup_receipt'
    directories(WORK)
    if not WORK.is_dir() or stat.S_IMODE(WORK.stat().st_mode)!=0o700:raise ValueError('Private work directory required')
    # The accepted maintenance lock coordinates with the old App; receipts stay intact.
    lock=ROOT/'.avalon-limbic-promotion/operation.lock';st=regular(lock)
    if stat.S_IMODE(st.st_mode)!=0o600:raise ValueError('Maintenance lock mode')
    fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if operation in ('verify','verify-removed'):
            phase='install' if operation=='verify' else 'remove'
            regular(WORK/(phase+'.complete.json'))
            live_verify(expect('FORWARD' if phase=='install' else 'BASELINE'))
            return 'verified_candidate_loaded' if operation=='verify' else 'old_source_verified_dependency_failure_expected'
        if operation=='install':backup_gate()
        before,after=('BASELINE','FORWARD') if operation=='install' else ('FORWARD','BASELINE')
        if operation=='remove':
            intent_record=load(WORK/'install.intent.json')
            if intent_record.get('baseline_manifest_sha256')!=hashlib.sha256((PAYLOAD/'HA_BASELINE_FILES.json').read_bytes()).hexdigest() or intent_record.get('forward_manifest_sha256')!=hashlib.sha256((PAYLOAD/'HA_FORWARD_FILES.json').read_bytes()).hexdigest():raise ValueError('Intent identity mismatch')
            verify_retained=inventory(WORK/'install-retained')
            expected_retained=expect('BASELINE')
            # Retained bytecode is validated by the same strict baseline verifier below.
            if any(k not in expected_retained and '/__pycache__/' not in k for k in verify_retained):raise ValueError('Retained tree mismatch')
        live_verify(expect(before))
        intent=WORK/(operation+'.intent.json');complete=WORK/(operation+'.complete.json')
        if intent.exists() or intent.is_symlink() or complete.exists() or complete.is_symlink():raise ValueError('Prior attempt; no replay')
        staged=WORK/(operation+'-retained')
        if staged.exists() or staged.is_symlink():raise ValueError('Unexpected staged tree')
        record={'version':1,'operation':operation,
                'baseline_manifest_sha256':hashlib.sha256((PAYLOAD/'HA_BASELINE_FILES.json').read_bytes()).hexdigest(),
                'forward_manifest_sha256':hashlib.sha256((PAYLOAD/'HA_FORWARD_FILES.json').read_bytes()).hexdigest(),
                'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        write_new(intent,(json.dumps(record,sort_keys=True)+'\n').encode())
        if operation=='install':
            extract(PAYLOAD/'ha-forward.tar',staged,expect(after))
            preserve_metadata(LIVE,staged/'llama_cpp')
            durable_tree(staged)
        else:
            staged=WORK/'install-retained'
            live_verify_at(staged/'llama_cpp',expect('BASELINE'))
        live_verify(expect(before))
        exchange(LIVE,staged/'llama_cpp')
        live_verify(expect(after))
        write_new(complete,(json.dumps({**record,'completed':True},sort_keys=True)+'\n').encode())
        return 'source_exchanged_restart_required'
    finally:os.close(fd)
