#!/usr/bin/env python3
"""Reproduce the tested stack on an existing bootable Windows/libvirt installation."""
import argparse,ast,base64,datetime,getpass,json,os,pathlib,pwd,re,shlex,shutil,stat,subprocess,sys,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import runtime
Q='http://libvirt.org/schemas/domain/qemu/1.0'
ET.register_namespace('qemu',Q)
LOCK=json.loads((ROOT/'components.lock.json').read_text())

def run(*args,cwd=None,env=None,check=True):
 return subprocess.run([str(a) for a in args],cwd=cwd,env=env,check=check,text=True,capture_output=True)
def show_run(*args,**kw):
 print('+',shlex.join(str(a) for a in args),flush=True)
 p=subprocess.run([str(a) for a in args],**kw)
 if p.returncode:raise RuntimeError(f'Command failed ({p.returncode})')
def config(path):
 c=json.loads(pathlib.Path(path).read_text())
 for key in ['domain','desktop_user','prefix','work_dir']:
  if not c.get(key) or 'CHANGE_ME' in str(c[key]):raise ValueError('Configure '+key)
 if not re.fullmatch(r'[A-Za-z0-9_-]+',c['domain']):raise ValueError('Invalid domain name')
 if c.get('client_profile') and not re.fullmatch(r'[A-Za-z0-9_-]+',c['client_profile']):raise ValueError('Invalid client_profile name')
 user=pwd.getpwnam(c['desktop_user']);home=pathlib.Path(user.pw_dir)
 if user.pw_uid==0:raise ValueError('Desktop user must be unprivileged')
 for key in ['prefix','work_dir']:
  c[key]=str(home/c[key][2:]) if c[key].startswith('~/') else c[key]
  if not pathlib.Path(c[key]).is_absolute():raise ValueError(key+' must be absolute or ~/ relative')
 c.setdefault('disk_mode','physical');c.setdefault('physical_disks',[])
 if c['disk_mode'] not in ['physical','image']:raise ValueError('disk_mode must be physical or image')
 if c['disk_mode']=='physical' and not c['physical_disks']:raise ValueError('Configure physical_disks or explicitly select disk_mode=image')
 if c['disk_mode']=='image' and c['physical_disks']:raise ValueError('Image mode cannot include physical_disks')
 for disk in c['physical_disks']:
  if not disk.startswith('/dev/disk/by-id/') or not pathlib.Path(disk).exists():raise ValueError('Use an existing stable by-id physical disk path')
  if not stat.S_ISBLK(os.stat(disk).st_mode):raise ValueError('Physical disk is not a block device')
 c.setdefault('uri','qemu:///system')
 if c['uri']!='qemu:///system':raise ValueError('This recipe currently supports qemu:///system')
 c['uid']=user.pw_uid;c['gid']=user.pw_gid;c['home']=str(home)
 c.setdefault('gpu_nodes',[]);c.setdefault('hostmem_bytes',4294967296)
 c.setdefault('share_letter','H');c.setdefault('share_tag','host-games')
 if c['hostmem_bytes']<1073741824 or c['hostmem_bytes']%1073741824:raise ValueError('hostmem_bytes must be a positive whole GiB')
 if not re.fullmatch('[D-Z]',c['share_letter']):raise ValueError('share_letter must be D-Z')
 if not re.fullmatch('[A-Za-z0-9_-]{1,36}',c['share_tag']):raise ValueError('Invalid share tag')
 if c.get('shared_directory'):
  if not pathlib.Path(c['shared_directory']).is_absolute() or not c.get('shared_uuid'):raise ValueError('Share requires absolute shared_directory and shared_uuid')
 c['service']='wintide-'+c['domain']+'-share.service'
 return c

def virsh(c,*args):return run('virsh','-c',c['uri'],*args).stdout

def pinned(name,work):
 d=work/'sources'/name;info=LOCK[name]
 if not d.exists():
  d.parent.mkdir(parents=True,exist_ok=True);show_run('git','init',str(d))
  show_run('git','remote','add','origin',info['url'],cwd=d)
 if run('git','status','--porcelain',cwd=d).stdout:raise RuntimeError('Dirty source tree: '+str(d))
 show_run('git','fetch','--depth','1','origin',info['commit'],cwd=d)
 show_run('git','checkout','--detach',info['commit'],cwd=d)
 return d

def patch(source,name):
 p=ROOT/'patches'/name
 if run('git','apply','--reverse','--check',str(p),cwd=source,check=False).returncode==0:return
 show_run('git','apply','--check',str(p),cwd=source);show_run('git','apply',str(p),cwd=source)

def build(c,jobs):
 if os.geteuid()==0:raise RuntimeError('Build as the desktop user, never root')
 if os.getuid()!=c['uid']:raise RuntimeError('Run build as configured desktop_user')
 work=pathlib.Path(c['work_dir']);prefix=c['prefix'];work.mkdir(parents=True,exist_ok=True)
 sources={}
 for n in ['renderer','qemu','freerdp','winapps']+(['virtiofsd'] if c.get('shared_directory') and c.get('share_permission_guard',True) else []):
  # Re-running a patched checkout is allowed only when its diff equals our patch.
  d=work/'sources'/n
  if d.exists() and run('git','status','--porcelain',cwd=d).stdout:
   p={'renderer':'renderer-libvirt-seccomp.patch','freerdp':'freerdp-sdl-resize.patch','virtiofsd':'virtiofsd-preserve-host-permissions.patch'}.get(n)
   if not p or run('git','apply','--reverse','--check',str(ROOT/'patches'/p),cwd=d,check=False).returncode:
    raise RuntimeError('Unreviewed source modifications: '+str(d))
   # Verify there are no changes beyond the expected patch using a temporary index.
   with __import__('tempfile').TemporaryDirectory() as tmp:
    env={**os.environ,'GIT_INDEX_FILE':tmp+'/index'}
    run('git','read-tree','HEAD',cwd=d,env=env)
    run('git','apply','--cached',str(ROOT/'patches'/p),cwd=d,env=env)
    if run('git','diff','--exit-code',cwd=d,env=env,check=False).returncode:raise RuntimeError('Extra source modifications: '+str(d))
   if run('git','rev-parse','HEAD',cwd=d).stdout.strip()!=LOCK[n]['commit']:raise RuntimeError('Wrong patched revision')
   sources[n]=d
  else:sources[n]=pinned(n,work)
 patch(sources['renderer'],'renderer-libvirt-seccomp.patch');patch(sources['freerdp'],'freerdp-sdl-resize.patch')
 b=work/'build';b.mkdir(exist_ok=True);r=b/'renderer'
 meson=['meson','setup']+(['--reconfigure'] if (r/'build.ninja').exists() else [])+[str(r),str(sources['renderer']),f'--prefix={prefix}','--libdir=lib','--buildtype=debugoptimized','-Db_ndebug=false','-Dcheck-gl-errors=true','-Dplatforms=egl,glx','-Dtests=false','-Dvenus=true','-Dvulkan-dload=true','-Dvulkan-preload=false']
 show_run(*meson);show_run('ninja','-C',str(r),f'-j{jobs}','install')
 q=b/'qemu';q.mkdir(exist_ok=True)
 env={**os.environ,'PKG_CONFIG_PATH':prefix+'/lib/pkgconfig:'+prefix+'/share/pkgconfig:'+os.environ.get('PKG_CONFIG_PATH',''),'LDFLAGS':'-Wl,-rpath,'+prefix+'/lib'}
 show_run(str(sources['qemu']/'configure'),f'--prefix={prefix}','--libdir=lib','--target-list=x86_64-softmmu','--enable-kvm','--enable-slirp','--disable-fdt','--enable-virglrenderer','--enable-opengl','--enable-gtk','--enable-spice','--enable-spice-protocol','--enable-pa','--audio-drv-list=pa','--disable-docs','--disable-werror','--disable-guest-agent','--disable-vte','--disable-sdl',cwd=q,env=env)
 show_run('ninja',f'-j{jobs}','install',cwd=q)
 f=b/'freerdp';fp=prefix+'/freerdp'
 show_run('cmake','-S',str(sources['freerdp']),'-B',str(f),'-G','Ninja',f'-DCMAKE_INSTALL_PREFIX={fp}','-DCMAKE_BUILD_TYPE=RelWithDebInfo','-DWITH_CLIENT_SDL=ON','-DWITH_CLIENT_SDL3=ON','-DWITH_CLIENT_SDL2=OFF','-DWITH_CLIENT_SDL_VERSIONED=OFF','-DWITH_BINARY_VERSIONING=OFF','-DWITH_SERVER=OFF','-DWITH_FFMPEG=OFF','-DWITH_SWSCALE=OFF','-DWITH_AAD=OFF','-DWITH_OPENH264=OFF','-DWITH_AOM=OFF','-DWITH_DAV1D=OFF','-DBUILD_TESTING=OFF','-DWITH_WAYLAND=ON','-DWITH_X11=ON')
 show_run('cmake','--build',str(f),'--parallel',str(jobs));show_run('cmake','--install',str(f))
 if 'virtiofsd' in sources:
  patch(sources['virtiofsd'],'virtiofsd-preserve-host-permissions.patch')
  target=b/'virtiofsd'
  cargo_env={**os.environ,'CARGO_TARGET_DIR':str(target)}
  show_run('cargo','test','--locked','--lib',cwd=sources['virtiofsd'],env=cargo_env)
  show_run('cargo','build','--release','--locked',cwd=sources['virtiofsd'],env=cargo_env)
  binary=pathlib.Path(prefix)/'libexec/virtiofsd-guard-bin';binary.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(target/'release/virtiofsd',binary)
 print('Pinned host stack and patched SDL client installed:',prefix)

def transform(xml,c,base):
 root=ET.fromstring(xml)
 if root.findall('./devices/hostdev'):raise ValueError('Remove/review PCI or USB passthrough before applying this shared-GPU recipe')
 # Do not silently lose unrelated custom QEMU arguments.
 args=root.find('{'+Q+'}commandline')
 if args is not None:raise ValueError('Existing custom QEMU arguments require manual integration; refusing to replace them')
 if root.find('memoryBacking') is not None:root.remove(root.find('memoryBacking'))
 backing=ET.SubElement(root,'memoryBacking');ET.SubElement(backing,'source',{'type':'memfd'});ET.SubElement(backing,'access',{'mode':'shared'})
 devices=root.find('devices');emulator=devices.find('emulator')
 if emulator is None:emulator=ET.SubElement(devices,'emulator')
 emulator.text=str(base/'qemu')
 for node in list(devices):
  if node.tag in ['graphics','video','redirdev'] or (node.tag=='channel' and node.get('type')=='spicevmc'):devices.remove(node)
 video=ET.SubElement(devices,'video');ET.SubElement(video,'model',{'type':'none'})
 if not devices.findall("./channel/target[@name='org.qemu.guest_agent.0']"):
  channel=ET.SubElement(devices,'channel',{'type':'unix'});ET.SubElement(channel,'target',{'type':'virtio','name':'org.qemu.guest_agent.0'})
 for label in list(root.findall("seclabel[@model='dac']")):root.remove(label)
 # QEMU must access the desktop and the libvirt swtpm directory. Keep tss as its primary group.
 label=ET.SubElement(root,'seclabel',{'type':'static','model':'dac','relabel':'yes'});ET.SubElement(label,'label').text=f"{c['uid']}:{c['tpm_gid']}"
 command=ET.SubElement(root,'{'+Q+'}commandline')
 # Let QEMU allocate a free PCI address; a hard-coded address can collide on another VM.
 for a in ['-display','gtk,gl=on,window-close=off','-device',f"virtio-vga-gl,id=wintide-gpu,hostmem={c['hostmem_bytes']},blob=on,venus=on"]:ET.SubElement(command,'{'+Q+'}arg',{'value':a})
 for n,value in {'DISPLAY':c.get('display',':0'),'WAYLAND_DISPLAY':c.get('wayland_display','wayland-1'),'XDG_RUNTIME_DIR':f"/run/user/{c['uid']}",'DBUS_SESSION_BUS_ADDRESS':f"unix:path=/run/user/{c['uid']}/bus",'HOME':c['home']}.items():
  ET.SubElement(command,'{'+Q+'}env',{'name':n,'value':value})
 ET.indent(root);return ET.tostring(root,encoding='unicode')

def gpu_acl(text,nodes):
 defaults=['/dev/null','/dev/full','/dev/zero','/dev/random','/dev/urandom','/dev/ptmx','/dev/userfaultfd']
 matches=list(re.finditer(r'^cgroup_device_acl\s*=\s*(\[[\s\S]*?\])',text,re.M))
 if len(matches)>1:raise ValueError('Multiple active cgroup_device_acl definitions; review manually')
 old=defaults
 if matches:
  raw=re.sub(r'#[^\n]*','',matches[0].group(1));old=ast.literal_eval(raw)
  if not isinstance(old,list) or not all(isinstance(s,str) for s in old):raise ValueError('Invalid device ACL')
 acl=list(dict.fromkeys(old+nodes));new='cgroup_device_acl = '+json.dumps(acl,indent=2)
 return text[:matches[0].start()]+new+text[matches[0].end():] if matches else text+'\n# Shared GPU rendering (WinTide)\n'+new+'\n'

def share_xml(c):
 f=ET.Element('filesystem',{'type':'mount','accessmode':'passthrough'})
 ET.SubElement(f,'driver',{'type':'virtiofs','queue':'1024'});ET.SubElement(f,'binary',{'path':c.get('virtiofsd_binary','/usr/lib/virtiofsd'),'xattr':'on'})
 ET.SubElement(f,'source',{'dir':c['shared_directory']});ET.SubElement(f,'target',{'dir':c['share_tag']})
 ET.indent(f);return ET.tostring(f,encoding='unicode')

def write(path,data,mode=0o644):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp')
 tmp.write_text(data);tmp.chmod(mode);tmp.replace(path)

def doctor(c):
 tools=['virsh','git','meson','ninja','cmake','pkg-config','vulkaninfo','lsblk','blockdev']
 for t in tools:print(('OK      ' if shutil.which(t) else 'MISSING ')+t)
 print('VM state:',virsh(c,'domstate',c['domain']).strip())
 for d in c['physical_disks']:print('Physical disk mounts:',json.dumps(runtime.mounts(d)))
 for d in c['gpu_nodes']:print('GPU node:',d,'present' if pathlib.Path(d).exists() else 'MISSING')
 if c.get('shared_directory'):print('Optional share mount:',run('findmnt','-rn','-M',c['shared_directory'],'-o','UUID',check=False).stdout.strip() or 'absent')
 print('No changes made. Inspect Vulkan capabilities with vulkaninfo before applying.')

def plan(c,out):
 import grp
 c['tpm_gid']=__import__('grp').getgrnam('tss').gr_gid
 if c.get('shared_directory') and c.get('share_permission_guard',True):
  c['virtiofsd_binary']='/etc/wintide/'+c['domain']+'/virtiofsd-guard'
 base=pathlib.Path('/etc/wintide')/c['domain']
 xml=virsh(c,'dumpxml',c['domain'],'--inactive')
 disks=ET.fromstring(xml).findall('./devices/disk/source[@dev]')
 configured={str(pathlib.Path(d).resolve()) for d in c['physical_disks']}
 if any(str(pathlib.Path(d.get('dev')).resolve()) not in configured for d in disks):
  raise ValueError('Every raw disk in the VM must be explicitly listed in physical_disks; image mode forbids raw disks')
 if c.get('disk_mode')=='image':
  images=ET.fromstring(xml).findall('./devices/disk[@device="disk"]/source[@file]')
  if not images:raise ValueError('Image mode requires a file-backed Windows disk in the existing VM')
  for source in images:
   info=json.loads(run('qemu-img','info','--force-share','--output=json',source.get('file')).stdout)
   if info.get('backing-filename'):raise ValueError('Image mode currently requires standalone disks, not backing chains or physical-disk overlays')
 # A raw Windows disk must never be the disk holding host root/boot/home.
 for target in ['/','/boot',c['home']]:
  result=run('findmnt','-rn','-T',target,'-o','SOURCE').stdout.strip().split('[')[0]
  if result.startswith('/dev/'):
   parents=run('lsblk','-srn','-o','PATH',result).stdout.split()
   if any(str(pathlib.Path(d).resolve()) in parents for d in c['physical_disks']):raise ValueError('Configured physical disk contains the running Linux system')
 out.mkdir(parents=True,exist_ok=True);out.chmod(0o700)
 write(out/'domain.before.xml',xml,0o600);write(out/'domain.wintide.xml',transform(xml,c,base),0o600)
 write(out/'config.json',json.dumps(c,indent=2),0o600)
 show_run('virt-xml-validate',str(out/'domain.wintide.xml'),'domain')
 print('Reviewable plan written outside Git:',out)
 print('Preserved CPU/storage/firmware/network; replaced graphics, enabled shared memory, added QGA channel.')
 return c

def apply_host(c,out):
 if os.geteuid()!=0:raise RuntimeError('apply-host requires sudo')
 if virsh(c,'domstate',c['domain']).strip()!='shut off':raise RuntimeError('Shut Windows down cleanly first; installer never force-stops it')
 # Detection only: never write into or silently supersede a legacy installation.
 for root in ['/etc/winapps-yttrium','/var/lib/winapps-yttrium']:
  if (pathlib.Path(root)/c['domain']).exists():raise RuntimeError('Legacy installation detected; migrate its hooks, state and backups together before installing WinTide. See docs/getting-started.md')
 base=pathlib.Path('/etc/wintide')/c['domain']
 if base.exists():raise RuntimeError('Installation already exists. Use its backups or a new plan, not a destructive rerun')
 if (pathlib.Path('/var/lib/wintide')/c['domain']).exists():raise RuntimeError('Rollback backups already exist; preserve them before a new installation')
 c=plan(c,out);runtime.guard(c,(out/'domain.before.xml').read_text())
 for p in ['bin/qemu-system-x86_64','lib/libvirglrenderer.so.1','libexec/virgl_render_server']:
  if not (pathlib.Path(c['prefix'])/p).exists():raise RuntimeError('Build missing: '+p)
 if c.get('shared_directory') and c.get('share_permission_guard',True) and not (pathlib.Path(c['prefix'])/'libexec/virtiofsd-guard-bin').exists():
  raise RuntimeError('Build the permission-guard backend before host installation')
 for p in c['gpu_nodes']:
  if not pathlib.Path(p).exists() or not stat.S_ISCHR(os.stat(p).st_mode):raise RuntimeError('Invalid GPU character device: '+p)
 # Verify effective access rather than chmodding globally or changing host GPU binding.
  access=run(sys.executable,'-c','import os,sys;os.setgroups([]);os.setgid(int(sys.argv[1]));os.setuid(int(sys.argv[2]));fd=os.open(sys.argv[3],os.O_RDWR);os.close(fd)',str(c['tpm_gid']),str(c['uid']),p,check=False)
  if access.returncode:raise RuntimeError('Desktop VM user needs read/write GPU device ACL first: '+p)
 backup=pathlib.Path('/var/lib/wintide')/c['domain'];backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
 shutil.copy2(out/'domain.before.xml',backup/'domain.before.xml')
 qconf=pathlib.Path('/etc/libvirt/qemu.conf');shutil.copy2(qconf,backup/'qemu.conf.before')
 acl=gpu_acl(qconf.read_text(),c['gpu_nodes'])
 base.mkdir(parents=True,mode=0o755)
 write(base/'config.json',json.dumps(c,indent=2));write(base/'runtime.py',(ROOT/'tools/runtime.py').read_text(),0o755)
 write(base/'qemu','#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(base/'runtime.py'))+' '+shlex.quote(str(base/'config.json'))+' qemu "$@"\n',0o755)
 hook=pathlib.Path('/etc/libvirt/hooks/qemu.d')/('90-wintide-'+c['domain'])
 write(hook,'#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(base/'runtime.py'))+' '+shlex.quote(str(base/'config.json'))+' hook "$@"\n',0o755)
 rule=pathlib.Path('/etc/udev/rules.d')/('90-wintide-'+c['domain']+'.rules')
 write(rule,'SUBSYSTEM=="block", PROGRAM="/usr/bin/python3 '+str(base/'runtime.py')+' '+str(base/'config.json')+' automount %N", RESULT=="ignore", ENV{UDISKS_IGNORE}="1"\n')
 if c.get('shared_directory'):
  if c.get('share_permission_guard',True):
   guarded=pathlib.Path(c['prefix'])/'libexec/virtiofsd-guard-bin'
   if not guarded.exists():raise RuntimeError('Build the permission-guard backend first')
   shutil.copy2(guarded,base/'virtiofsd-guard-bin')
   write(base/'virtiofsd-guard','#!/bin/sh\nexec '+shlex.quote(str(base/'virtiofsd-guard-bin'))+' --preserve-host-permissions "$@"\n',0o755)
  write(base/'share.xml',share_xml(c))
  unit='[Unit]\nDescription=Optional Windows VirtioFS share\nAfter=virtqemud.service\n\n[Service]\nType=oneshot\nEnvironment=LC_ALL=C\nExecStart=/usr/bin/python3 '+str(base/'runtime.py')+' '+str(base/'config.json')+' share\nTimeoutStartSec=240\n'
  write('/etc/systemd/system/'+c['service'],unit)
  mount=run('systemd-escape','-p','--suffix=mount',c['shared_directory']).stdout.strip()
  write('/etc/systemd/system/'+mount+'.d/wintide-'+c['domain']+'.conf','[Unit]\nWants='+c['service']+'\nBefore='+c['service']+'\n')
 write(qconf,acl)
 show_run('udevadm','control','--reload');show_run('systemctl','daemon-reload')
 daemon='virtqemud' if run('systemctl','is-active','virtqemud',check=False).returncode==0 else 'libvirtd'
 show_run('systemctl','restart',daemon)
 show_run('virsh','-c',c['uri'],'define',str(out/'domain.wintide.xml'))
 print('Installed. Start with: sudo ./setup.sh --config CONFIG start')
 print('Rollback XML and qemu.conf backup:',backup)

def guest(c,mode,args):
 if os.geteuid()!=0:raise RuntimeError('Guest setup requires sudo access to system libvirt/QGA')
 if mode=='yttrium' and not args.enable_test_signing:raise RuntimeError('Use --enable-test-signing after reading docs/security.md')
 quoted=lambda s:"'"+str(s).replace("'","''")+"'"
 if mode=='ssh':
  if not args.windows_user or not args.ssh_key:raise ValueError('SSH setup requires --windows-user and --ssh-key (private key path; only its .pub file is sent)')
  key=pathlib.Path(args.ssh_key).expanduser().with_suffix(pathlib.Path(args.ssh_key).suffix+'.pub').read_text().strip()
  script=(ROOT/'guest/Configure-SSH.ps1').read_text()
  params=' -PublicKey '+quoted(key)+' -UserName '+quoted(args.windows_user)+' -HostAddress '+quoted(c.get('host_address','192.168.122.1'))+' -InstallServer'
  runtime.guest_ps(c,'& {\n'+script+'\n}'+params,timeout=900);return
 script=(ROOT/'guest/Configure-Windows.ps1').read_text()
 params=' -Mode '+quoted(mode)+' -HostAddress '+quoted(c.get('host_address','192.168.122.1'))+' -ShareTag '+quoted(c['share_tag'])+' -DriveLetter '+quoted(c['share_letter'])+f" -Owner '{c['uid']}:{c['gid']}'"
 if args.windows_user:params+=' -WindowsUser '+quoted(args.windows_user)
 if mode=='yttrium':params+=' -EnableTestSigning'
 if args.disable_hibernation:params+=' -DisableHibernation'
 runtime.guest_ps(c,'& {\n'+script+'\n}'+params,timeout=900)

def client_paths(c):
 home=pathlib.Path(c['home']);base=home/'.local/share/wintide';conf=home/'.config/wintide';name='wintide'
 if c.get('client_profile'):
  profile=c['client_profile']
  if not re.fullmatch(r'[A-Za-z0-9_-]+',profile):raise ValueError('Invalid client_profile name')
  base=base/'profiles'/profile;conf=conf/'profiles'/profile;name+='-'+profile
 return base,conf,home/'.local/bin'/name

def install_command(c,args):
 if os.getuid()!=c['uid'] or os.geteuid()==0:raise RuntimeError('Install the command as desktop_user, never root')
 from wintide import atomic_json
 home=pathlib.Path(c['home']);base,conf,command=client_paths(c)
 existing=getattr(args,'existing_launcher',None)
 destination=conf/'client.json'
 if destination.exists() and not getattr(args,'update_command',False):raise RuntimeError('WinTide command is already configured. Use --update-command to refresh code while preserving client settings')
 saved=json.loads(destination.read_text()) if destination.exists() else None
 if saved:
  existing=saved['core'] if saved.get('existing_launcher') else None
  args.existing_start=saved.get('existing_start');args.existing_stop=saved.get('existing_stop');args.app_dir=saved['app_dir']
 if existing:
  if not getattr(args,'app_dir',None) or not getattr(args,'existing_start',None):raise ValueError('Adoption requires --existing-launcher, --existing-start and --app-dir')
  for binary in [existing,args.existing_start]+([args.existing_stop] if getattr(args,'existing_stop',None) else []):
   if not pathlib.Path(binary).is_absolute() or not os.access(binary,os.X_OK):raise ValueError('Existing launcher/start command must be an executable absolute path')
  appdir=pathlib.Path(args.app_dir).expanduser().resolve()
 else:appdir=base/'apps'
 core=existing or str(base/'wintide-core')
 if not os.access(core,os.X_OK):raise RuntimeError('Install the client profile first, or specify an existing launcher')
 # Only these reviewed toolkit sources are copied; never copy local configs or build trees.
 files=['setup.sh','components.lock.json','examples/config.example.json']
 files += ['tools/'+n for n in ['setup.py','runtime.py','wintide.py','terminal_ui.py','wizard.py']]
 files += ['guest/'+n for n in ['Configure-Windows.ps1','Configure-SSH.ps1','Discover-Apps.ps1','Explorer-Broker.ps1','Settings-Broker.ps1']]
 files += ['patches/'+n for n in ['freerdp-sdl-resize.patch','renderer-libvirt-seccomp.patch','virtiofsd-preserve-host-permissions.patch']]
 toolkit=base/'toolkit'
 for name in files:
  source=ROOT/name;target=toolkit/name
  if source.resolve()!=target.resolve():write(target,source.read_text(),0o755 if name.endswith('.sh') else 0o644)
 if command.exists() and 'wintide' not in command.read_text(errors='replace').lower():raise RuntimeError('Refusing to replace an unrelated wintide command')
 if not destination.exists():
  key=getattr(args,'ssh_key',None);ssh_config=getattr(args,'ssh_config',None)
  ssh={'enabled':bool(key or ssh_config),'host':getattr(args,'ssh_host',None),'user':None if ssh_config else args.windows_user,'identity_file':str(pathlib.Path(key).expanduser()) if key else None,'config_file':str(pathlib.Path(ssh_config).expanduser()) if ssh_config else None,'port':22 if not ssh_config else None}
  defaults={}
  for ident in ['explorer-broker','settings-broker']:
   broker=appdir/ident/(ident+'.vbs')
   if broker.exists():defaults[ident]=[str(broker)]
  # Preserve broker arguments in an adopted installation without evaluating desktop entries.
  if existing:
   for entry in (home/'.local/share/applications').glob('*.desktop'):
    for line in entry.read_text(errors='replace').splitlines():
     if not line.startswith('Exec='):continue
     try:words=shlex.split(line[5:])
     except ValueError:continue
     if len(words)>=2 and words[0]==existing and (appdir/words[1]/'info').is_file():
      defaults[words[1]]=[x for x in words[2:] if x not in ['%F','%f','%U','%u']]
  atomic_json(conf/'setup.json',c)
  atomic_json(destination,{'domain':c['domain'],'uri':c['uri'],'core':core,'command':str(command),'app_dir':str(appdir),'desktop_dir':str(home/'.local/share/applications'),'desktop_prefix':command.name,'setup_config':str(conf/'setup.json'),'existing_launcher':bool(existing),'existing_start':getattr(args,'existing_start',None),'existing_stop':getattr(args,'existing_stop',None),'guest_address':c.get('guest_address'),'ssh':ssh,'app_arguments':defaults})
 write(command,'#!/bin/sh\nexec /usr/bin/python3 '+shlex.quote(str(toolkit/'tools/wintide.py'))+' --config '+shlex.quote(str(destination))+' "$@"\n',0o755)
 print('Installed WinTide command:',command)
 if str(command.parent) not in os.environ.get('PATH','').split(os.pathsep):print('Add ~/.local/bin to PATH, or use the absolute command above.')

def install_client(c,args):
 if os.getuid()!=c['uid']:raise RuntimeError('Install client as desktop_user')
 base,conf,_=client_paths(c)
 if (conf/'profile.conf').exists() or (conf/'client.json').exists():raise RuntimeError('Profile already exists; preserved it. Use install-command --update-command for code updates')
 for relative in ['.config/winapps-yttrium','.local/share/winapps-yttrium','.local/bin/winapps-yttrium']:
  if (pathlib.Path(c['home'])/relative).exists():raise RuntimeError('Legacy client detected; migrate its credentials and launchers together before installing WinTide. See docs/getting-started.md')
 src=pathlib.Path(c['work_dir'])/'sources/winapps'
 if not args.windows_user:raise RuntimeError('--windows-user is required')
 if not src.exists():raise RuntimeError('Run build first (also fetches pinned WinApps)')
 if run('git','rev-parse','HEAD',cwd=src).stdout.strip()!=LOCK['winapps']['commit']:raise RuntimeError('Wrong WinApps source revision')
 base.mkdir(parents=True,exist_ok=True);conf.mkdir(parents=True,mode=0o700,exist_ok=True)
 if (conf/'profile.conf').exists():raise RuntimeError('Profile already exists; preserved it. Edit manually if needed')
 core=(src/'bin/winapps').read_text()
 core=core.replace('readonly APPDATA_PATH="${HOME}/.local/share/winapps"',f'readonly APPDATA_PATH={shlex.quote(str(base))}')
 core=core.replace('readonly CONFIG_PATH="${HOME}/.config/winapps/winapps.conf"',f'readonly CONFIG_PATH={shlex.quote(str(conf/"profile.conf"))}')
 core=core.replace('readonly SYS_APP_PATH="/usr/local/share/winapps"',f'readonly SYS_APP_PATH={shlex.quote(str(src))}')
 core=core.replace('[ "$DEBUG" = "true" ] && echo "[$(date)-$RUNID] $1" >>"$LOG_PATH"','if [ "$DEBUG" = "true" ]; then echo "[$(date)-$RUNID] $1" >>"$LOG_PATH"; fi\n    return 0')
 write(base/'wintide-core',core,0o755)
 # Preserve local credentials on rerun. Never print or put the password in argv.
 password=conf/'rdp-password'
 if not password.exists():
  supplied=getattr(args,'password_file',None)
  if supplied:
   source=pathlib.Path(supplied).expanduser();st=source.stat()
   if st.st_uid!=c['uid'] or st.st_mode & 0o077:raise ValueError('Password file must be owned by desktop_user with mode 0600')
   value=source.read_text().rstrip('\r\n')
  else:value=getpass.getpass('Windows account password (not PIN): ')
  if not value:raise ValueError('Windows RemoteApps requires a nonempty account password')
  write(password,value,0o600)
 ask=conf/'askpass';write(ask,'#!/bin/sh\nexec cat '+shlex.quote(str(password))+'\n',0o700)
 profile=conf/'profile.conf'
 if profile.exists():raise RuntimeError('Profile already exists; preserved it. Edit manually if needed')
 if not args.windows_user:raise RuntimeError('--windows-user is required')
 s={'RDP_USER':args.windows_user,'RDP_DOMAIN':'','RDP_IP':'','VM_NAME':c['domain'],'WAFLAVOR':'libvirt','FREERDP_COMMAND':c['prefix']+'/freerdp/bin/sdl-freerdp','RDP_ASKPASS':str(ask),'RDP_FLAGS':'/cert:tofu /wm-class:wintide +home-drive','RDP_FLAGS_NON_WINDOWS':'/wm-class:wintide /gdi:sw -decorations +dynamic-resolution','RDP_FLAGS_WINDOWS':'/wm-class:wintide -decorations /dynamic-resolution','DEBUG':'false','AUTOPAUSE':'off'}
 write(profile,'\n'.join(k+'='+shlex.quote(value) for k,value in s.items())+'\n',0o600)
 # App metadata is generated independently from installed registrations by discover.
 (base/'apps').mkdir(exist_ok=True)
 for ident,title,script in [('explorer-broker','Explorer window','Explorer-Broker.ps1'),('settings-broker','Windows Settings','Settings-Broker.ps1')]:
  broker=base/'apps'/ident;broker.mkdir(exist_ok=True)
  ps=(ROOT/'guest'/script).read_text();encoded=base64.b64encode(ps.encode('utf-16le')).decode()
  write(broker/(ident+'.vbs'),'Set shell = CreateObject("WScript.Shell")\nshell.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+encoded+'", 0, True\n')
  write(broker/'info',f"NAME='{title}'\nFULL_NAME='{title}'\nWIN_EXECUTABLE='C:\\Windows\\System32\\wscript.exe'\nCATEGORIES='Utility'\nMIME_TYPES=''\n")
 install_command(c,args)
 print('Isolated WinTide profile installed. VM must be running. Test manual Notepad as shown in README.')
 print('Discover installed apps: sudo ./setup.sh --config CONFIG discover')
 print('Then generate entries: ./setup.sh --config CONFIG launchers')

def discover(c,app_dir=None):
 if os.geteuid()!=0:raise RuntimeError('Discovery requires system QGA access; run with sudo')
 data=json.loads(runtime.guest_ps(c,(ROOT/'guest/Discover-Apps.ps1').read_text(),quiet=True))
 if not isinstance(data,list):raise RuntimeError('Expected an app list from Windows')
 base=pathlib.Path(app_dir).expanduser().resolve() if app_dir else client_paths(c)[0]/'apps'
 if not base.is_relative_to(pathlib.Path(c['home']).resolve()):raise ValueError('App metadata must stay inside the configured desktop home')
 base.mkdir(parents=True,exist_ok=True)
 os.chown(base,c['uid'],c['gid'])
 for app in data:
  name=app['name'];exe=app['exe']
  if not isinstance(name,str) or not isinstance(exe,str) or any(ord(x)<32 for x in name+exe):raise RuntimeError('Invalid Windows app record')
  if not re.match(r'^[A-Za-z]:\\',exe) or not exe.lower().endswith('.exe'):continue
  slug=re.sub('[^a-z0-9]+','-',pathlib.PureWindowsPath(exe).stem.lower()).strip('-')
  slug+='-'+__import__('hashlib').sha256(exe.casefold().encode()).hexdigest()[:8]
  folder=base/slug;folder.mkdir(exist_ok=True);os.chown(folder,c['uid'],c['gid'])
  info='\n'.join(k+'='+shlex.quote(v) for k,v in {'NAME':name,'FULL_NAME':name,'WIN_EXECUTABLE':exe,'CATEGORIES':'Utility','MIME_TYPES':''}.items())+'\n'
  write(folder/'info',info);os.chown(folder/'info',c['uid'],c['gid'])
 print('Discovered',len(data),'registered executables; metadata written locally. UWP apps and unregistered portable apps may need manual entries.')

def launchers(c):
 # Read independently generated metadata as quoted values, never execute guest data.
 if os.getuid()!=c['uid']:raise RuntimeError('Run launcher generation as desktop_user')
 client_config=client_paths(c)[1]/'client.json'
 if client_config.exists():
  from wintide import Client
  Client(client_config).entries();return
 profile_base,_,command=client_paths(c)
 base=profile_base/'apps';dest=pathlib.Path(c['home'])/'.local/share/applications'
 dest.mkdir(parents=True,exist_ok=True);count=0
 for d in sorted(base.glob('*')):
  if not re.fullmatch('[a-zA-Z0-9_-]+',d.name):continue
  info=d/'info'
  if not info.exists():continue
  text=info.read_text();match=re.search(r'^NAME=(.+)$',text,re.M)
  values=shlex.split(match.group(1)) if match else []
  name=values[0] if len(values)==1 else d.name
  if any(x in name for x in ['\n','\r']):continue
  exe=str(command)
  if any(x in exe for x in ['"','%','\n','\\']):raise RuntimeError('Unsupported desktop Exec path')
  extra=' "'+str(base/'explorer-broker/explorer-broker.vbs')+'"' if d.name=='explorer-broker' else ''
  desktop='[Desktop Entry]\nType=Application\nName='+name+' (Windows VM)\nExec="'+exe+'" '+d.name+extra+'\nIcon=applications-other\nTerminal=false\nCategories=Utility;\n'
  write(dest/(command.name+'-'+d.name+'.desktop'),desktop);count+=1
 print(f'Created {count} discovered app launchers. Existing Docker launchers unchanged.')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--plan-dir',default=str(ROOT/'local-plan'))
 p.add_argument('command',choices=['install','doctor','build','plan','apply-host','guest','install-client','install-command','discover','launchers','start','stop','share','restore-mounts','rollback-host','prepare-guest','wait-guest','shutdown-guest'])
 p.add_argument('--jobs',type=int,default=min(os.cpu_count() or 4,12));p.add_argument('--guest-mode',choices=['rdp','yttrium','share','ssh'],default='rdp');p.add_argument('--windows-user');p.add_argument('--enable-test-signing',action='store_true');p.add_argument('--disable-hibernation',action='store_true')
 p.add_argument('--plain',action='store_true');p.add_argument('--yes',action='store_true',help='accept the displayed setup plan and clean shutdown')
 p.add_argument('--skip-ssh',action='store_true');p.add_argument('--ssh-key');p.add_argument('--ssh-config');p.add_argument('--ssh-host')
 p.add_argument('--password-file',help='read the RDP password from a private desktop-user-owned file instead of prompting')
 p.add_argument('--existing-launcher');p.add_argument('--existing-start');p.add_argument('--existing-stop');p.add_argument('--app-dir');p.add_argument('--update-command',action='store_true')
 a=p.parse_args();c=config(a.config);out=pathlib.Path(a.plan_dir).resolve()
 if a.command=='install':
  from wizard import install
  install(c,a)
 elif a.command=='doctor':doctor(c)
 elif a.command=='build':build(c,a.jobs)
 elif a.command=='plan':plan(c,out)
 elif a.command=='apply-host':apply_host(c,out)
 elif a.command=='guest':guest(c,a.guest_mode,a)
 elif a.command=='install-client':install_client(c,a)
 elif a.command=='install-command':install_command(c,a)
 elif a.command=='discover':discover(c,a.app_dir)
 elif a.command=='launchers':launchers(c)
 elif a.command=='rollback-host':
  if os.geteuid()!=0 or virsh(c,'domstate',c['domain']).strip()!='shut off':raise RuntimeError('Rollback requires root and a shut-off VM')
  before=pathlib.Path('/var/lib/wintide')/c['domain']/'domain.before.xml'
  show_run('virsh','-c',c['uri'],'define',str(before));print('Previous graphics restored. Host GPU ACL retained to avoid affecting other VMs; see rollback docs.')
 elif a.command in ['prepare-guest','wait-guest','shutdown-guest']:
  from wizard import guest_lifecycle
  guest_lifecycle(c,a.command)
 else:
  if os.geteuid()!=0:raise RuntimeError('Runtime actions require sudo')
  installed=pathlib.Path('/etc/wintide')/c['domain']/'config.json'
  if not installed.exists():raise RuntimeError('Apply host setup first')
  show_run('/usr/bin/python3',str(installed.parent/'runtime.py'),str(installed),a.command)
if __name__=='__main__':
 try:main()
 except (ValueError,RuntimeError,subprocess.SubprocessError,KeyError,OSError) as e:sys.exit('ERROR: '+str(e))
