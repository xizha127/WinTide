#!/usr/bin/env python3
"""Root-owned VM runtime installed by setup.py. No credentials are stored here."""
import base64,json,os,pathlib,subprocess,sys,time,xml.etree.ElementTree as ET

def run(args,check=True,timeout=20):
 return subprocess.run(args,check=check,capture_output=True,text=True,timeout=timeout,env={**os.environ,'LC_ALL':'C'})
def v(c,*args):return run(['virsh','-c',c['uri'],*args])
def state(c):return v(c,'domstate',c['domain']).stdout.strip()
def mounts(disk):
 data=json.loads(run(['lsblk','-J','-o','PATH,MOUNTPOINTS',disk]).stdout)
 def walk(n):
  for m in n.get('mountpoints') or []:
   if m:yield {'source':n['path'],'target':m}
  for ch in n.get('children',[]):yield from walk(ch)
 return [r for n in data['blockdevices'] for r in walk(n)]
def agent(c,command,args=None):
 q={'execute':command}
 if args is not None:q['arguments']=args
 return json.loads(v(c,'qemu-agent-command',c['domain'],json.dumps(q),'--timeout','5').stdout)['return']
def guest_ps(c,script,timeout=120,quiet=False):
 encoded=base64.b64encode(script.encode('utf-16le')).decode()
 pid=agent(c,'guest-exec',{'path':'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe','arg':['-NoProfile','-NonInteractive','-EncodedCommand',encoded],'capture-output':True})['pid']
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  r=agent(c,'guest-exec-status',{'pid':pid})
  if r['exited']:
   for field in ['out-data','err-data']:
    if r.get(field) and not quiet:print(base64.b64decode(r[field]).decode(errors='replace'))
   if r.get('exitcode',1):raise RuntimeError('Guest command failed; inspect output above')
   return base64.b64decode(r.get('out-data','')).decode(errors='replace')
  time.sleep(1)
 raise RuntimeError(f'Guest process {pid} still running; do not launch duplicate work')
def guard(c,xml):
 root=ET.fromstring(xml)
 disks={str(pathlib.Path(s.get('dev')).resolve()) for s in root.findall('./devices/disk/source[@dev]')}
 disks.update(str(pathlib.Path(p).resolve()) for p in c['physical_disks'])
 for disk in disks:
  rows=mounts(disk)
  if rows:raise RuntimeError('Physical VM disk has mounted filesystems: '+json.dumps(rows))
 images={str(pathlib.Path(s.get('file')).resolve()) for s in root.findall('./devices/disk/source[@file]')}
 loops=json.loads(run(['losetup','--json','--list','--output','NAME,BACK-FILE']).stdout)
 for loop in loops.get('loopdevices',[]):
  if str(pathlib.Path(loop['back-file']).resolve()) in images and mounts(loop['name']):
   raise RuntimeError('VM image is loop-mounted on Linux')
def prepare(c,root):
 if state(c)!='shut off':raise RuntimeError('Disk preparation requires a shut-off VM')
 rows=[r for d in c['physical_disks'] for r in mounts(d)]
 if any(not r['target'].startswith(('/mnt/','/run/media/')) for r in rows):
  raise RuntimeError('Refusing to unmount a system or unexpected mount')
 root.mkdir(parents=True,exist_ok=True);(root/'active').touch(mode=0o600)
 if rows:(root/'mounts.json').write_text(json.dumps(rows))
 run(['udevadm','trigger','--subsystem-match=block','--action=change']);run(['udevadm','settle'])
 for r in sorted(rows,key=lambda r:len(r['target']),reverse=True):run(['umount','--',r['target']])
 guard(c,v(c,'dumpxml',c['domain'],'--inactive').stdout)
 for disk in c['physical_disks']:
  data=json.loads(run(['lsblk','-J','-o','PATH,FSTYPE',disk]).stdout)
  def probe(node):
   if node.get('fstype')=='ntfs':run(['ntfs-3g.probe','--readwrite',node['path']])
   for child in node.get('children',[]):probe(child)
  for node in data['blockdevices']:probe(node)
def restore(c,root):
 if state(c)!='shut off':raise RuntimeError('Refusing to remount while VM is active')
 (root/'active').unlink(missing_ok=True)
 run(['udevadm','trigger','--subsystem-match=block','--action=change']);run(['udevadm','settle'])
 saved=root/'mounts.json'
 if saved.exists():
  for row in json.loads(saved.read_text()):
   if not row['target'].startswith(('/mnt/','/run/media/')):raise RuntimeError('Unexpected saved mount target')
   if run(['mountpoint','-q',row['target']],False).returncode:run(['mount',row['target']])
  saved.unlink()
def share(c,root):
 if not c.get('shared_directory') or state(c)!='running':return
 m=run(['findmnt','-rn','-M',c['shared_directory'],'-o','UUID'],False)
 if m.returncode or m.stdout.strip()!=c['shared_uuid']:
  print('Optional share absent; VM continues without it.');return
 xml=ET.fromstring(v(c,'dumpxml',c['domain']).stdout)
 current=[f for f in xml.findall('./devices/filesystem') if f.find('target') is not None and f.find('target').get('dir')==c['share_tag']]
 if current:
  if current[0].find('source').get('dir')!=c['shared_directory']:raise RuntimeError('Share tag collision')
 else:v(c,'attach-device',c['domain'],str(root/'share.xml'),'--live')
 for _ in range(30):
  try:agent(c,'guest-ping');break
  except subprocess.SubprocessError:time.sleep(2)
 else:raise RuntimeError('Guest agent unavailable; share attached but Windows service not started')
 guest_ps(c,"Start-Service VirtioFsSvc -ErrorAction Stop; if (!(Test-Path "+c['share_letter']+":\\)) { exit 1 }")
def main():
 config=pathlib.Path(sys.argv[1]);c=json.loads(config.read_text());mode=sys.argv[2];args=sys.argv[3:];root=config.parent
 if mode=='qemu':
  for i,a in enumerate(args[:-1]):
   if a=='-accel' and args[i+1].split(',')[0]=='kvm' and c.get('honor_guest_pat') and 'honor-guest-pat=' not in args[i+1]:args[i+1]+=',honor-guest-pat=on'
   if a=='-sandbox':args[i+1]=args[i+1].replace('spawn=deny','spawn=allow')
  binary=c['prefix']+'/bin/qemu-system-x86_64';os.execv(binary,[binary,*args])
 if mode=='hook':
  if args[:3]==[c['domain'],'prepare','begin']:guard(c,sys.stdin.read())
  if args[:3]==[c['domain'],'started','begin'] and c.get('shared_directory'):
   run(['systemctl','start','--no-block',c['service']])
 elif mode=='automount':
  if (root/'active').exists():
   node=pathlib.Path(args[0]);parent=run(['lsblk','-ndo','PKNAME',str(node)],False).stdout.strip()
   actual=str(pathlib.Path('/dev',parent).resolve()) if parent else str(node.resolve())
   if actual in [str(pathlib.Path(p).resolve()) for p in c['physical_disks']]:print('ignore')
 elif mode=='start':
  s=state(c)
  if s=='running':return
  if s!='shut off':raise RuntimeError('VM must be running or shut off')
  prepare(c,root);v(c,'start',c['domain'])
 elif mode=='stop':
  if state(c)!='shut off':
   v(c,'shutdown',c['domain'])
   for _ in range(120):
    if state(c)=='shut off':break
    time.sleep(1)
   else:raise RuntimeError('Windows did not shut down; no force-stop or remount performed')
  restore(c,root)
 elif mode=='share':share(c,root)
 elif mode=='restore-mounts':restore(c,root)
 else:raise RuntimeError('Unknown runtime operation')
if __name__=='__main__':
 try:main()
 except (RuntimeError,subprocess.SubprocessError) as e:sys.exit(str(e))
