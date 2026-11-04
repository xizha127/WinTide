import importlib.util,json,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
import setup,runtime

XML='''<domain type="kvm"><name>testvm</name><cpu mode="custom"><model>Skylake-Client-IBRS</model></cpu><devices><emulator>/usr/bin/qemu-system-x86_64</emulator><disk type="block"><source dev="/dev/example"/></disk><graphics type="spice"/><video><model type="qxl"/></video><channel type="spicevmc"/><interface type="network"><source network="default"/></interface></devices></domain>'''
C={'domain':'testvm','prefix':'/opt/test','uid':1000,'gid':1000,'tpm_gid':973,'home':'/example','hostmem_bytes':4294967296,'display':':0','wayland_display':'wayland-1','physical_disks':[],'uri':'qemu:///system','shared_directory':'/mnt/test','shared_uuid':'expected','share_tag':'host-games','share_letter':'H'}
class SetupTests(unittest.TestCase):
 def test_guest_binary_copy_handles_partial_writes_and_closes(self):
  data=b'abcdef';calls=[]
  def agent(c,command,args):
   calls.append((command,args))
   if command=='guest-file-open':return 42
   if command=='guest-file-write':return {'count':2}
   return {}
  with patch.object(runtime,'agent',side_effect=agent):runtime.guest_write(C,'C:\\helper.exe',data)
  import base64
  chunks=[base64.b64decode(a['buf-b64']) for command,a in calls if command=='guest-file-write']
  self.assertEqual(chunks,[b'abcdef',b'cdef',b'ef'])
  self.assertEqual(calls[-1],('guest-file-close',{'handle':42}))
 def test_guest_binary_copy_closes_after_failure(self):
  calls=[]
  def agent(c,command,args):
   calls.append(command)
   if command=='guest-file-open':return 42
   if command=='guest-file-write':return {'count':0}
   return {}
  with patch.object(runtime,'agent',side_effect=agent):
   with self.assertRaisesRegex(RuntimeError,'progress'):runtime.guest_write(C,'C:\\helper.exe',b'data')
  self.assertEqual(calls[-1],'guest-file-close')
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
 def test_share_xml_does_not_force_always_cache(self):
  text=setup.share_xml(C);self.assertNotIn('always',text);self.assertNotIn('<lock',text)
if __name__=='__main__':unittest.main()

class ClientTests(unittest.TestCase):
 def test_generated_profile_and_broker_preserve_quoting(self):
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as tmp:
   home=pathlib.Path(tmp);src=home/'work/sources/winapps';(src/'bin').mkdir(parents=True)
   (src/'bin/winapps').write_text('#!/bin/bash\nreadonly APPDATA_PATH="${HOME}/.local/share/winapps"\nreadonly CONFIG_PATH="${HOME}/.config/winapps/winapps.conf"\nreadonly SYS_APP_PATH="/usr/local/share/winapps"\n')
   c={**C,'home':str(home),'work_dir':str(home/'work')}
   with patch.object(setup.os,'getuid',return_value=1000),patch.object(setup,'run',return_value=subprocess.CompletedProcess([],0,setup.LOCK['winapps']['commit'],'')),patch.object(setup.getpass,'getpass',return_value='test-only-fixture'):
    setup.install_client(c,SimpleNamespace(windows_user='example-user'))
    setup.launchers(c)
   self.assertIn('export WINTIDE_SESSION_REUSE=1', (home/'.local/bin/winapps-yttrium').read_text())
   profile=home/'.config/winapps-yttrium/profile.conf'
   self.assertEqual(profile.stat().st_mode & 0o777,0o600)
   self.assertNotIn('test-only-fixture',profile.read_text())
   self.assertIn('RDP_ASKPASS=',profile.read_text())
   info=home/'.local/share/winapps-yttrium/apps/explorer-broker/info'
   result=subprocess.run(['bash','-c','source "$1"; printf "%s" "$WIN_EXECUTABLE"','_',str(info)],capture_output=True,text=True,check=True)
   self.assertEqual(result.stdout,'C:\\Windows\\System32\\wscript.exe')
   desktop=next((home/'.local/share/applications').glob('*.desktop')).read_text()
   self.assertIn('explorer-broker.vbs',desktop)

class PermissionGuardTests(unittest.TestCase):
 def test_guarded_backend_is_selected_without_changing_source_or_tag(self):
  c={**C,'virtiofsd_binary':'/etc/example/virtiofsd-guard'}
  root=setup.ET.fromstring(setup.share_xml(c))
  self.assertEqual(root.find('binary').get('path'),c['virtiofsd_binary'])
  self.assertEqual(root.find('source').get('dir'),C['shared_directory'])
  self.assertEqual(root.find('target').get('dir'),C['share_tag'])
