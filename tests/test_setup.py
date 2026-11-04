import importlib.util,json,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import setup,runtime

XML='''<domain type="kvm"><name>testvm</name><cpu mode="custom"><model>Skylake-Client-IBRS</model></cpu><devices><emulator>/usr/bin/qemu-system-x86_64</emulator><disk type="block"><source dev="/dev/example"/></disk><graphics type="spice"/><video><model type="qxl"/></video><channel type="spicevmc"/><interface type="network"><source network="default"/></interface></devices></domain>'''
C={'domain':'testvm','prefix':'/opt/test','uid':1000,'gid':1000,'tpm_gid':973,'home':'/example','hostmem_bytes':4294967296,'display':':0','wayland_display':'wayland-1','physical_disks':[],'uri':'qemu:///system','shared_directory':'/mnt/test','shared_uuid':'expected','share_tag':'host-games','share_letter':'H'}
class SetupTests(unittest.TestCase):
 def test_image_mode_requires_explicit_opt_in(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   path=pathlib.Path(tmp)/'config.json'
   c={**C,'desktop_user':'example','work_dir':'/example/cache'}
   path.write_text(json.dumps(c))
   account=SimpleNamespace(pw_dir='/example',pw_uid=1000,pw_gid=1000)
   with patch.object(setup.pwd,'getpwnam',return_value=account):
    with self.assertRaisesRegex(ValueError,'physical_disks'):setup.config(path)
    c['disk_mode']='image';path.write_text(json.dumps(c))
    self.assertEqual(setup.config(path)['physical_disks'],[])
 def test_image_plan_refuses_raw_disks_and_backing_chains(self):
  from types import SimpleNamespace
  import grp
  with tempfile.TemporaryDirectory() as tmp,patch.object(grp,'getgrnam',return_value=SimpleNamespace(gr_gid=973)),patch.object(setup,'show_run'):
   c={**C,'disk_mode':'image'}
   with patch.object(setup,'virsh',return_value=XML):
    with self.assertRaisesRegex(ValueError,'Every raw disk'):setup.plan(c,pathlib.Path(tmp))
   image_xml=XML.replace('<disk type="block"><source dev="/dev/example"/></disk>','<disk type="file" device="disk"><source file="/example/windows.qcow2"/></disk>')
   def command(*args,**kwargs):return subprocess.CompletedProcess(args,0,json.dumps({'backing-filename':'/dev/example'}) if args[0]=='qemu-img' else '','')
   with patch.object(setup,'virsh',return_value=image_xml),patch.object(setup,'run',side_effect=command):
    with self.assertRaisesRegex(ValueError,'standalone'):setup.plan(c,pathlib.Path(tmp))
   def standalone(*args,**kwargs):return subprocess.CompletedProcess(args,0,'{}' if args[0]=='qemu-img' else '','')
   with patch.object(setup,'virsh',return_value=image_xml),patch.object(setup,'run',side_effect=standalone):setup.plan(c,pathlib.Path(tmp))
   self.assertTrue((pathlib.Path(tmp)/'domain.wintide.xml').is_file())
 def test_restore_saved_memory_refuses_before_touching_mounts(self):
  with patch.object(runtime,'state',return_value='shut off'),patch.object(runtime,'run',return_value=subprocess.CompletedProcess([],0,'','')):
   with self.assertRaisesRegex(RuntimeError,'saved Windows memory'):runtime.restore(C,pathlib.Path('/missing'))
 def test_restore_skips_unconfigured_desktop_mounts(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);(root/'mounts.json').write_text(json.dumps([{'source':'/dev/example1','target':'/run/media/user/example'}]))
   calls=[]
   def command(args,check=True,timeout=20):
    calls.append(args);return subprocess.CompletedProcess(args,1 if args[0] in ['virsh','mountpoint','findmnt'] else 0,'','')
   with patch.object(runtime,'state',return_value='shut off'),patch.object(runtime,'run',side_effect=command):runtime.restore(C,root)
   self.assertFalse(any(args[0]=='mount' for args in calls))
   self.assertFalse((root/'mounts.json').exists())
 def test_prepare_refuses_readonly_raw_disks_without_ntfs_mount_probe(self):
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   def command(args,check=True,timeout=20):
    calls.append(args);return subprocess.CompletedProcess(args,0,'1\n' if args[0]=='blockdev' else '','')
   c={**C,'physical_disks':['/dev/disk/by-id/example']}
   with patch.object(runtime,'state',return_value='shut off'),patch.object(runtime,'mounts',return_value=[]),patch.object(runtime,'guard'),patch.object(runtime,'v',return_value=subprocess.CompletedProcess([],0,XML,'')),patch.object(runtime,'run',side_effect=command):
    with self.assertRaisesRegex(RuntimeError,'read-only'):runtime.prepare(c,pathlib.Path(tmp))
   self.assertFalse(any(args[0]=='ntfs-3g.probe' for args in calls))
 def test_transform_preserves_boot_cpu_storage_network(self):
  root=setup.ET.fromstring(setup.transform(XML,C,pathlib.Path('/etc/example')))
  self.assertEqual(root.find('cpu/model').text,'Skylake-Client-IBRS')
  self.assertEqual(root.find('./devices/disk/source').get('dev'),'/dev/example')
  self.assertEqual(root.find('./devices/interface/source').get('network'),'default')
  self.assertIsNone(root.find('./devices/graphics'))
  self.assertEqual(root.find('./devices/video/model').get('type'),'none')
  self.assertEqual(root.find('./memoryBacking/access').get('mode'),'shared')
  self.assertIsNotNone(root.find("./devices/channel/target[@name='org.qemu.guest_agent.0']"))
  values=[e.get('value') for e in root.findall('./{'+setup.Q+'}commandline/{'+setup.Q+'}arg')]
  self.assertIn('gtk,gl=on,window-close=off',values)
  self.assertNotIn('addr=',values[-1])
 def test_existing_custom_args_not_overwritten(self):
  xml=XML.replace('<domain type="kvm">','<domain type="kvm" xmlns:qemu="'+setup.Q+'">').replace('</domain>','<qemu:commandline/></domain>')
  with self.assertRaises(ValueError):setup.transform(xml,C,pathlib.Path('/etc/example'))
 def test_passthrough_requires_review(self):
  with self.assertRaises(ValueError):setup.transform(XML.replace('<devices>','<devices><hostdev/>'),C,pathlib.Path('/etc/example'))
 def test_acl_preserves_existing_is_idempotent(self):
  text='# unrelated\ncgroup_device_acl = ["/dev/null", "/dev/custom"]\nuser="qemu"\n'
  result=setup.gpu_acl(text,['/dev/nvidia0'])
  self.assertIn('/dev/custom',result);self.assertIn('user="qemu"',result)
  self.assertEqual(result,setup.gpu_acl(result,['/dev/nvidia0']))
 def test_acl_injection_rejected(self):
  with self.assertRaises((ValueError,SyntaxError)):setup.gpu_acl('cgroup_device_acl = [do_something()]',[])
 def test_duplicate_acl_rejected(self):
  with self.assertRaises(ValueError):setup.gpu_acl('cgroup_device_acl = []\ncgroup_device_acl = []',[])
 def test_guard_rejects_mounted_raw_disk(self):
  with patch.object(runtime,'mounts',return_value=[{'target':'/mnt/windows'}]):
   with self.assertRaisesRegex(RuntimeError,'mounted'):runtime.guard(C,XML)
 def test_guard_checks_partition_not_just_whole_disk(self):
  output={'blockdevices':[{'path':'/dev/example','mountpoints':[None],'children':[{'path':'/dev/example1','mountpoints':['/mnt/windows']}]}]}
  with patch.object(runtime,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(output),'')):
   self.assertEqual(runtime.mounts('/dev/example')[0]['target'],'/mnt/windows')
 def test_share_absent_never_attaches(self):
  with patch.object(runtime,'state',return_value='running'),patch.object(runtime,'run',return_value=subprocess.CompletedProcess([],1,'','')),patch.object(runtime,'v') as v:
   runtime.share(C,pathlib.Path('/etc/example'));v.assert_not_called()
 def test_share_wrong_uuid_never_attaches(self):
  with patch.object(runtime,'state',return_value='running'),patch.object(runtime,'run',return_value=subprocess.CompletedProcess([],0,'different','')),patch.object(runtime,'v') as v:
   runtime.share(C,pathlib.Path('/etc/example'));v.assert_not_called()
 def test_restore_running_vm_never_remounts(self):
  with patch.object(runtime,'state',return_value='running'),patch.object(runtime,'run') as r:
   with self.assertRaises(RuntimeError):runtime.restore(C,pathlib.Path('/missing'))
   r.assert_not_called()
 def test_apply_running_vm_never_changes_host(self):
  with patch.object(setup.os,'geteuid',return_value=0),patch.object(setup,'virsh',return_value='running\n'),patch.object(setup,'write') as w:
   with self.assertRaisesRegex(RuntimeError,'Shut Windows'):setup.apply_host(C,pathlib.Path('/missing'))
   w.assert_not_called()
 def test_apply_preserves_legacy_state_and_existing_rollback_backups(self):
  for existing in ['/etc/winapps-yttrium/testvm','/var/lib/winapps-yttrium/testvm','/var/lib/wintide/testvm']:
   with self.subTest(existing=existing),patch.object(setup.os,'geteuid',return_value=0),patch.object(setup,'virsh',return_value='shut off\n'),patch.object(pathlib.Path,'exists',autospec=True,side_effect=lambda p:str(p)==existing),patch.object(setup,'plan') as plan,patch.object(setup,'write') as write:
    with self.assertRaises(RuntimeError):setup.apply_host(C,pathlib.Path('/unused'))
    plan.assert_not_called();write.assert_not_called()
 def test_share_xml_does_not_force_always_cache(self):
  text=setup.share_xml(C);self.assertNotIn('always',text);self.assertNotIn('<lock',text)
if __name__=='__main__':unittest.main()

class ClientTests(unittest.TestCase):
 def test_named_profile_cannot_replace_default_client(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   home=pathlib.Path(tmp);conf=home/'.config/wintide';conf.mkdir(parents=True)
   default=conf/'client.json';default.write_text('existing default settings')
   c={**C,'home':str(home),'client_profile':'validation'}
   base,profile,command=setup.client_paths(c)
   self.assertEqual(profile,conf/'profiles/validation')
   self.assertEqual(command,home/'.local/bin/wintide-validation')
   core=base/'wintide-core';core.parent.mkdir(parents=True);core.write_text('#!/bin/sh\n');core.chmod(0o755)
   with patch.object(setup.os,'getuid',return_value=1000):
    setup.install_command(c,SimpleNamespace(windows_user='test'))
   settings=json.loads((profile/'client.json').read_text())
   from wintide import Client
   entry=Client(profile/'client.json').desktop('example','Example')
   self.assertEqual(entry.name,'wintide-validation-example.desktop')
   self.assertEqual(default.read_text(),'existing default settings')
   with patch.object(setup.os,'getuid',return_value=1000),patch.object(setup,'write') as write:
    with self.assertRaisesRegex(RuntimeError,'Profile already exists'):setup.install_client(c,SimpleNamespace(windows_user='test'))
    write.assert_not_called()
 def test_legacy_client_refused_before_writes_or_password_prompt(self):
  from types import SimpleNamespace
  for relative in ['.config/winapps-yttrium','.local/share/winapps-yttrium','.local/bin/winapps-yttrium']:
   with self.subTest(relative=relative),tempfile.TemporaryDirectory() as tmp:
    home=pathlib.Path(tmp);legacy=home/relative;legacy.parent.mkdir(parents=True)
    legacy.write_text('existing state')
    with patch.object(setup.os,'getuid',return_value=1000),patch.object(setup,'write') as write,patch.object(setup.getpass,'getpass') as password:
     with self.assertRaisesRegex(RuntimeError,'Legacy client'):setup.install_client({**C,'home':str(home)},SimpleNamespace(windows_user='example'))
     write.assert_not_called();password.assert_not_called()
    self.assertEqual(legacy.read_text(),'existing state')
    self.assertFalse((home/'.config/wintide').exists())
 def test_generated_profile_and_broker_preserve_quoting(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   home=pathlib.Path(tmp);src=home/'work/sources/winapps';(src/'bin').mkdir(parents=True)
   (src/'bin/winapps').write_text('#!/bin/bash\nreadonly APPDATA_PATH="${HOME}/.local/share/winapps"\nreadonly CONFIG_PATH="${HOME}/.config/winapps/winapps.conf"\nreadonly SYS_APP_PATH="/usr/local/share/winapps"\n')
   with (src/'bin/winapps').open('a') as fixture:
    fixture.write('source "$CONFIG_PATH"\nprintf "%s\\n" "$APPDATA_PATH" "$SYS_APP_PATH" "$WINTIDE_SESSION_REUSE" "$RDP_FLAGS" "$1"\n')
   c={**C,'home':str(home),'work_dir':str(home/'work')}
   with patch.object(setup.os,'getuid',return_value=1000),patch.object(setup,'run',return_value=subprocess.CompletedProcess([],0,setup.LOCK['winapps']['commit'],'')),patch.object(setup.getpass,'getpass',return_value='test-only-fixture'):
    setup.install_client(c,SimpleNamespace(windows_user='example-user'))
    setup.launchers(c)
   launched=subprocess.run([str(home/'.local/bin/wintide'),'apps','list'],capture_output=True,text=True,check=True)
   self.assertIn('explorer-broker',launched.stdout)
   self.assertIn('settings-broker',launched.stdout)
   command_config=json.loads((home/'.config/wintide/client.json').read_text())
   self.assertEqual(command_config['app_arguments']['explorer-broker'],[str(home/'.local/share/wintide/apps/explorer-broker/explorer-broker.vbs')])
   profile=home/'.config/wintide/profile.conf'
   self.assertEqual(profile.stat().st_mode & 0o777,0o600)
   self.assertNotIn('test-only-fixture',profile.read_text())
   self.assertIn('RDP_ASKPASS=',profile.read_text())
   info=home/'.local/share/wintide/apps/explorer-broker/info'
   result=subprocess.run(['bash','-c','source "$1"; printf "%s" "$WIN_EXECUTABLE"','_',str(info)],capture_output=True,text=True,check=True)
   self.assertEqual(result.stdout,'C:\\Windows\\System32\\wscript.exe')
   desktop=(home/'.local/share/applications/wintide-explorer-broker.desktop').read_text()
   self.assertIn('"app" "explorer-broker"',desktop)
   self.assertIn(str(home/'.local/bin/wintide'),desktop)
   self.assertTrue((home/'.local/share/applications/wintide-explorer-broker.desktop').exists())

class PermissionGuardTests(unittest.TestCase):
 def test_guarded_backend_is_selected_without_changing_source_or_tag(self):
  c={**C,'virtiofsd_binary':'/etc/example/virtiofsd-guard'}
  root=setup.ET.fromstring(setup.share_xml(c))
  self.assertEqual(root.find('binary').get('path'),c['virtiofsd_binary'])
  self.assertEqual(root.find('source').get('dir'),C['shared_directory'])
  self.assertEqual(root.find('target').get('dir'),C['share_tag'])
