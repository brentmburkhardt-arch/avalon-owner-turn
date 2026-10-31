"""Temporary fixed-function source update App; no commands/paths/URLs from options."""
import hashlib,json,os,stat,sys
from pathlib import Path
PAYLOAD=Path('/opt/avalon-ha-recovery/payload')
OPTIONS=Path('/data/options.json')
ALLOWED={'HA_BASELINE_FILES.json','HA_FORWARD_FILES.json','ha-baseline.tar','ha-forward.tar',
         'helpers/package_io.py','helpers/ha_inspect.py','helpers/ha_owner_turn.py'}

def read(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('Unexpected input')
    return path.read_bytes()

def payload_gate():
    expected=json.loads(read(PAYLOAD/'PAYLOAD.json'))
    if set(expected)!=ALLOWED:raise ValueError('Payload schema')
    seen=set()
    for p in PAYLOAD.rglob('*'):
        if p.is_dir() and not p.is_symlink():continue
        name=p.relative_to(PAYLOAD).as_posix();data=read(p);seen.add(name)
        if name!='PAYLOAD.json' and hashlib.sha256(data).hexdigest()!=expected.get(name):raise ValueError('Payload digest')
    if seen!=ALLOWED|{'PAYLOAD.json'}:raise ValueError('Payload inventory')

def main():
    operation='unselected';os.umask(0o077)
    try:
        if len(sys.argv)!=1:raise ValueError('No arguments')
        payload_gate()
        raw=read(OPTIONS)
        if len(raw)>256:raise ValueError('Options size')
        def pairs(items):
            result={}
            for k,v in items:
                if k in result:raise ValueError('Duplicate option')
                result[k]=v
            return result
        options=json.loads(raw,object_pairs_hook=pairs)
        if type(options) is not dict or set(options)!={'operation'}:raise ValueError('Fixed options')
        sys.path.insert(0,str(PAYLOAD/'helpers'))
        import ha_owner_turn
        if options['operation'] not in ha_owner_turn.OPERATIONS:raise ValueError('Fixed operation')
        operation=options['operation'];outcome=ha_owner_turn.execute(operation)
        print(json.dumps({'app_version':'1.0.0','package':'ha-2026104-recovery-v1','operation':operation,'outcome':outcome}));return 0
    except BaseException:
        print(json.dumps({'app_version':'1.0.0','package':'ha-2026104-recovery-v1','operation':operation,'outcome':'stopped_preserve_state'}));return 1
if __name__=='__main__':raise SystemExit(main())
