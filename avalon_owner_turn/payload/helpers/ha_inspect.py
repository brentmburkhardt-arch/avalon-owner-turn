"""Fixed read-only HA WebSocket inspection through the App's existing supervisor token.
No tokens, configuration bodies, titles or provider settings are returned to the UI.
"""
import base64,hashlib,http.client,json,os,struct

ENTRY='01M0RKDE69R9H1DWM4WJYKYH5J'
SUBENTRY='01M0RKDE692GCFV6QQMFVPS5XE'
VERSION='2026.9.4+avalon.limbic.1'

class WS:
    def __enter__(self):
        token=os.environ.get('SUPERVISOR_TOKEN')
        if not token:raise ValueError('Existing App HA API capability unavailable')
        self.connection=http.client.HTTPConnection('supervisor',80,timeout=15)
        key=base64.b64encode(os.urandom(16)).decode()
        self.connection.request('GET','/core/websocket',headers={'Authorization':'Bearer '+token,'Upgrade':'websocket','Connection':'Upgrade','Sec-WebSocket-Version':'13','Sec-WebSocket-Key':key})
        self.response=self.connection.getresponse()
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if self.response.status!=101 or self.response.getheader('Sec-WebSocket-Accept')!=expected:raise ValueError('HA API upgrade unavailable')
        # HTTPResponse retains the buffered reader after status 101.
        self.reader=self.response.fp
        hello=self.read()
        if hello.get('type')!='auth_required':raise ValueError('HA API authentication protocol')
        self.send({'type':'auth','access_token':token})
        if self.read().get('type')!='auth_ok':raise ValueError('HA API authentication unavailable')
        self.sequence=0
        return self
    def __exit__(self,*a):self.response.close();self.connection.close()
    def exact(self,n):
        data=self.reader.read(n)
        if len(data)!=n:raise ValueError('HA API truncated frame')
        return data
    def send(self,value,opcode=1):
        raw=json.dumps(value,separators=(',',':')).encode() if opcode==1 else value
        mask=os.urandom(4);size=len(raw)
        head=bytes([0x80|opcode,0x80|size]) if size<126 else bytes([0x80|opcode,0x80|126])+struct.pack('!H',size)
        self.connection.sock.sendall(head+mask+bytes(v^mask[i%4] for i,v in enumerate(raw)))
    def read(self):
        chunks=[];total=0
        while True:
            first,second=self.exact(2);op=first&15
            if first&0x70 or second&0x80:raise ValueError('HA API frame flags')
            size=second&127
            if size==126:size=struct.unpack('!H',self.exact(2))[0]
            elif size==127:size=struct.unpack('!Q',self.exact(8))[0]
            if size>262144 or total+size>262144:raise ValueError('HA API frame size')
            data=self.exact(size)
            if op==9:self.send(data,10);continue
            if op not in (0,1) or (op==0 and not chunks) or (op==1 and chunks):raise ValueError('HA API frame opcode')
            chunks.append(data);total+=size
            if first&0x80:return json.loads(b''.join(chunks))
    def call(self,kind,**kwargs):
        allowed={'get_config':set(),'config_entries/get_single':{'entry_id'},'config_entries/subentries/list':{'entry_id'},'manifest/get':{'integration'}}
        if kind not in allowed or set(kwargs)!=allowed[kind]:raise ValueError('Read-only inspection allowlist')
        if kwargs.get('entry_id',ENTRY)!=ENTRY or kwargs.get('integration','llama_cpp')!='llama_cpp':raise ValueError('Inspection target')
        self.sequence+=1;self.send({'id':self.sequence,'type':kind,**kwargs});row=self.read()
        if row.get('id')!=self.sequence or row.get('type')!='result' or row.get('success') is not True:raise ValueError('HA API inspection rejected')
        return row['result']

def inspect():
    with WS() as ws:
        cfg=ws.call('get_config')
        if cfg.get('version')!='2026.9.4':raise ValueError('Core version fence')
        entry=ws.call('config_entries/get_single',entry_id=ENTRY)['config_entry']
        if entry.get('entry_id')!=ENTRY or entry.get('domain')!='llama_cpp' or entry.get('state')!='loaded':raise ValueError('Lyra entry fence')
        sub=ws.call('config_entries/subentries/list',entry_id=ENTRY)
        selected=[r for r in sub if r.get('subentry_id')==SUBENTRY and r.get('subentry_type')=='conversation']
        if len(selected)!=1:raise ValueError('Lyra subentry fence')
        manifest=ws.call('manifest/get',integration='llama_cpp')
        if manifest.get('domain')!='llama_cpp':raise ValueError('Integration fence')
        return {'core_version':cfg['version'],'entry':ENTRY,'subentry':SUBENTRY,'state':'loaded',
                'custom_version':manifest.get('version'),'safe_mode':bool(cfg.get('safe_mode',False))}
