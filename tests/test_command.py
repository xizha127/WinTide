import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import wintide
from terminal_ui import Progress, logged_run
from wizard import Checkpoints


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.path=self.home/'client.json'
        self.config={'domain':'testvm','uri':'qemu:///system','core':'/example/core','command':str(self.home/'wintide'),
                     'app_dir':str(self.home/'apps'),'desktop_dir':str(self.home/'desktops'),
                     'ssh':{'enabled':True,'host':'test-host','config_file':'/example/ssh-config'},
                     'app_arguments':{},'setup_config':str(self.home/'setup.json')}
        wintide.atomic_json(self.path,self.config)
        self.client=wintide.Client(self.path,plain=True)

    def test_ssh_has_no_rdp_path_or_forwarding(self):
        completed=subprocess.CompletedProcess([],0,'hostname 127.0.0.1\nport 22\n','')
        with patch.object(self.client,'start') as start,patch.object(self.client,'launch') as launch,patch.object(self.client,'wait_rdp') as rdp,patch.object(wintide,'execute',return_value=completed),patch.object(wintide.socket,'create_connection'),patch.object(wintide.subprocess,'call',return_value=0) as call:
            self.assertEqual(self.client.ssh(['whoami']),0)
        start.assert_called_once();launch.assert_not_called();rdp.assert_not_called()
        argv=call.call_args.args[0]
        self.assertEqual(argv[0],'ssh')
        self.assertIn('ClearAllForwardings=yes',argv);self.assertIn('-x',argv);self.assertIn('-a',argv)
        self.assertEqual(argv[-2:],['test-host','whoami'])

    def test_launch_uses_reuse_and_preserves_literal_arguments(self):
        self.client.add('Example',r'C:\Program Files\Example\app.exe','example',['--flag','a "quoted" value'])
        with patch.dict(os.environ,{'WAYLAND_DISPLAY':'test-wayland'}),patch.object(self.client,'start'),patch.object(self.client,'wait_rdp'),patch.object(wintide.subprocess,'call',return_value=0) as call:
            self.client.launch(['example','$(not-a-shell)'])
        self.assertEqual(call.call_args.args[0],['/example/core','example','--flag','a "quoted" value','$(not-a-shell)'])
        self.assertEqual(call.call_args.kwargs['env']['WINTIDE_SESSION_REUSE'],'1')

    def test_failed_guarded_start_never_opens_rdp(self):
        with patch.dict(os.environ,{'WAYLAND_DISPLAY':'test'}),patch.object(self.client,'start',side_effect=RuntimeError('mounted disk')),patch.object(self.client,'wait_rdp') as rdp,patch.object(wintide.subprocess,'call') as call:
            with self.assertRaisesRegex(RuntimeError,'mounted disk'):self.client.launch(['windows'])
        rdp.assert_not_called();call.assert_not_called()

    def test_no_display_recommends_ssh_without_starting_vm(self):
        with patch.dict(os.environ,{},clear=True),patch.object(self.client,'start') as start:
            with self.assertRaisesRegex(RuntimeError,'--ssh'):self.client.launch(['windows'])
        start.assert_not_called()

    def test_existing_running_vm_does_not_run_start_command(self):
        with patch.object(self.client,'state',return_value='running'),patch.object(self.client,'runtime_command') as runtime:
            self.client.start()
        runtime.assert_not_called()

    def test_missing_host_integration_never_uses_unguarded_virsh_start(self):
        with patch.object(self.client,'state',return_value='shut off'),patch.object(Path,'exists',return_value=False),patch.object(wintide.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'unguarded'):self.client.start()
        run.assert_not_called()

    def test_adopted_start_and_stop_remain_explicit(self):
        self.client.config.update(existing_start='/existing/start',existing_stop='/existing/stop')
        self.assertEqual(self.client.runtime_command('start'),['/existing/start'])
        self.assertEqual(self.client.runtime_command('stop'),['/existing/stop'])

    def test_app_metadata_is_not_executed_and_custom_files_are_preserved(self):
        marker=self.home/'executed'
        self.client.add('Name $(touch '+str(marker)+')',r'C:\Tools\app.exe','literal')
        self.assertIn('$(touch',self.client.records()[0][1])
        self.assertFalse(marker.exists())
        custom=self.home/'apps/literal/user-note.txt';custom.write_text('keep')
        self.client.remove('literal')
        self.assertEqual(custom.read_text(),'keep')
        self.assertFalse((self.home/'desktops/wintide-literal.desktop').exists())

    def test_remove_never_deletes_upstream_metadata(self):
        folder=self.home/'apps/upstream';folder.mkdir(parents=True)
        (folder/'info').write_text("NAME='Upstream'\n")
        self.client.desktop('upstream','Upstream')
        self.client.remove('upstream')
        self.assertTrue((folder/'info').exists())

    def test_invalid_app_paths_rejected(self):
        for value in ['../escape','bad;name','with spaces']:
            with self.assertRaises(ValueError):self.client.remove(value)
        with self.assertRaises(ValueError):self.client.add('Bad','powershell -Command arbitrary')

    def test_ambiguous_guest_addresses_are_not_guessed(self):
        output='vnet0 aa ipv4 192.0.2.2/24\nvnet1 bb ipv4 192.0.2.3/24'
        with patch.object(self.client,'virsh',return_value=output):
            with self.assertRaisesRegex(RuntimeError,'one Windows address'):self.client.guest_address()

    def test_ssh_option_injection_refused(self):
        self.client.config['ssh']['host']='-oProxyCommand=bad'
        with self.assertRaises(ValueError):self.client.ssh_command()

    def test_desktop_arguments_round_trip_through_gio(self):
        try:
            import gi
            gi.require_version('Gio','2.0')
            from gi.repository import Gio
        except ImportError:
            self.skipTest('PyGObject is optional; this integration check runs where Gio is installed')
        script=self.home/'record.py';output=self.home/'result.json'
        script.write_text('import pathlib,sys,json;pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))')
        values=['space value','quote"value','back\\slash','$literal','%literal','`literal`']
        entry=self.home/'probe.desktop'
        entry.write_text('[Desktop Entry]\nType=Application\nName=Argument test\nExec='+ ' '.join(wintide.desktop_arg(x) for x in [sys.executable,str(script),str(output),*values])+'\n')
        app=Gio.DesktopAppInfo.new_from_filename(str(entry));self.assertIsNotNone(app);app.launch([],None)
        for _ in range(50):
            if output.exists():break
            time.sleep(.02)
        self.assertEqual(json.loads(output.read_text()),values)

    def test_default_command_and_flags_route_correctly(self):
        with patch.object(wintide,'Client') as cls:
            client=cls.return_value
            client.launch.return_value=0;client.ssh.return_value=0
            self.assertEqual(wintide.main(['--config',str(self.path)]),0)
            client.launch.assert_called_once_with(['windows'])
            client.launch.reset_mock()
            wintide.main(['--config',str(self.path),'--ssh','whoami'])
            client.ssh.assert_called_once_with(['whoami']);client.launch.assert_not_called()
            wintide.main(['--config',str(self.path),'--app','example','a b'])
            client.launch.assert_called_once_with(['example','a b'])


class SetupProgressTests(unittest.TestCase):
    def test_plain_mode_has_real_counts_and_no_escape_sequences(self):
        output=io.StringIO();progress=Progress(2,plain=True,stream=output)
        with progress.step('One'):pass
        with self.assertRaises(RuntimeError):
            with progress.step('Two'):raise RuntimeError('failure')
        self.assertEqual(progress.done,1)
        self.assertIn('1/2',output.getvalue());self.assertNotIn('\x1b',output.getvalue())

    def test_only_successful_stages_checkpoint_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';checkpoint=Checkpoints(path,'same-inputs');calls=[]
            progress=Progress(2,plain=True,stream=io.StringIO())
            checkpoint.run('built',lambda:calls.append('built'),progress)
            def failed():raise RuntimeError('guest not ready')
            with self.assertRaises(RuntimeError):checkpoint.run('guest',failed,progress)
            resumed=Checkpoints(path,'same-inputs')
            resumed.run('built',lambda:calls.append('unexpected'),progress)
            self.assertEqual(calls,['built']);self.assertEqual(resumed.data['completed'],['built'])
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):Checkpoints(path,'new-inputs')
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_failed_command_propagates_and_log_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'build.log'
            with self.assertRaisesRegex(RuntimeError,'exit 7'):
                logged_run([sys.executable,'-c','print("failure details");raise SystemExit(7)'],path)
            self.assertIn('failure details',path.read_text());self.assertEqual(path.stat().st_mode & 0o777,0o600)


if __name__=='__main__':unittest.main()
