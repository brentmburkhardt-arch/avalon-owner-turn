"""Closed regular-file inventory and confined, non-overwriting package extraction."""
import hashlib,json,os,stat,tarfile
from pathlib import Path,PurePosixPath

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def regular(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('Unexpected file type')
    return st

def directories(path):
    for p in (path,*path.parents):
        if p.exists() and not stat.S_ISDIR(p.lstat().st_mode):raise ValueError('Unsafe parent')

def inventory(root):
    directories(root)
    result={}
    for p in root.rglob('*'):
        st=p.lstat()
        if stat.S_ISDIR(st.st_mode):continue
        regular(p);result[p.relative_to(root).as_posix()]=digest(p)
    return result

def verify(root,expected):
    if inventory(root)!=expected:raise ValueError('Package inventory or digest mismatch')

def extract(archive,destination,expected):
    regular(archive);directories(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('Destination already exists')
    with tarfile.open(archive,'r:') as tar:
        members=tar.getmembers();names=[m.name for m in members]
        if len(set(names))!=len(names) or set(names)!=set(expected):raise ValueError('Archive inventory')
        for m in members:
            path=PurePosixPath(m.name)
            if not m.isfile() or m.mode!=0o644 or path.is_absolute() or '..' in path.parts or str(path)!=m.name:raise ValueError('Archive member')
            if m.size>2_000_000:raise ValueError('Archive member size')
            if hashlib.sha256(tar.extractfile(m).read()).hexdigest()!=expected[m.name]:raise ValueError('Archive checksum')
        destination.mkdir(mode=0o700)
        for m in members:
            p=destination/m.name;p.parent.mkdir(parents=True,exist_ok=True)
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'wb') as f:f.write(tar.extractfile(m).read());f.flush();os.fsync(f.fileno())
    verify(destination,expected)

def write_new(path,data,mode=0o600):
    directories(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    sync_dir(path.parent)

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def move(source,destination):
    directories(source.parent);directories(destination.parent)
    if destination.exists() or destination.is_symlink():raise ValueError('Refuse overwrite')
    os.rename(source,destination);sync_dir(source.parent);sync_dir(destination.parent)

def load(path):regular(path);return json.loads(path.read_text())
