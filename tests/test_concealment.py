import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET
import subprocess
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
import concealment as c

XML = '''<domain type="kvm" xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
<name>example</name><uuid>unchanged</uuid><memory>16777216</memory>
<os><loader>/firmware/code</loader><nvram>/firmware/vars</nvram></os>
<features><hyperv><synic state="on"/></hyperv></features>
<cpu mode="custom"><model>Skylake-Client-IBRS</model></cpu>
<devices><emulator>/working/qemu</emulator><disk type="block"><source dev="/dev/disk/by-id/example"/></disk>
<interface><mac address="52:54:00:00:00:01"/></interface>
<input type="tablet" bus="usb"/></devices>
<qemu:commandline><qemu:arg value="-device"/><qemu:arg value="virtio-vga-gl,venus=on"/>
<qemu:env name="DISPLAY" value=":0"/></qemu:commandline></domain>'''
IDENTITY = dict(manufacturer='Example', product='Computer', board='Board')


def transform(xml=XML, profile='metadata'):
    return c.transform(xml, '/candidate/wrapper', '/candidate/code', '/candidate/vars',
                       '/candidate/template', IDENTITY, profile)


class ConcealmentTests(unittest.TestCase):
    def test_preserves_working_gpu_disks_network_cpu_and_guest_identity(self):
        before, after = ET.fromstring(XML), ET.fromstring(transform())
        for path in ['uuid', 'memory', 'cpu', 'features', 'devices/disk', 'devices/interface', 'devices/input']:
            self.assertEqual(ET.canonicalize(ET.tostring(before.find(path)), strip_text=True),
                             ET.canonicalize(ET.tostring(after.find(path)), strip_text=True))
        values = [n.get('value') for n in after.findall(f'{{{c.Q}}}commandline/{{{c.Q}}}arg')]
        self.assertEqual(values[:2], ['-device', 'virtio-vga-gl,venus=on'])
        self.assertEqual(after.find(f'{{{c.Q}}}commandline/{{{c.Q}}}env').get('value'), ':0')

    def test_cpu_concealment_keeps_hyperv_performance_and_cpu_model(self):
        result = ET.fromstring(transform(profile='cpu-hidden'))
        self.assertEqual(result.find('cpu/model').text, 'Skylake-Client-IBRS')
        self.assertEqual(result.find('features/hyperv/synic').get('state'), 'on')
        self.assertEqual(result.find("cpu/feature[@name='hypervisor']").get('policy'), 'disable')
        self.assertEqual(result.find('features/kvm/hidden').get('state'), 'on')
        self.assertEqual(result.find('features/hyperv/vendor_id').get('value'), 'GenuineIntel')

    def test_existing_identity_configuration_is_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, 'SMBIOS'):
            transform(XML.replace('<features>', '<sysinfo type="smbios"/><features>'))

    def test_custom_firmware_uses_explicit_selection(self):
        result = ET.fromstring(transform(XML.replace('<os>', '<os firmware="efi"><firmware><feature name="secure-boot" enabled="no"/></firmware>')))
        self.assertNotIn('firmware', result.find('os').attrib)
        self.assertIsNone(result.find('os/firmware'))
        self.assertEqual(result.find('os/loader').get('secure'), 'no')

    def test_secure_boot_is_not_silently_disabled(self):
        with self.assertRaisesRegex(ValueError, 'Secure Boot'):
            transform(XML.replace('<os>', '<os><firmware><feature name="secure-boot" enabled="yes"/></firmware>'))

    def test_running_vm_cannot_be_activated_or_rolled_back(self):
        with patch.object(c, 'virsh', return_value='running\n'):
            with self.assertRaisesRegex(RuntimeError, 'disk-guarded'):
                c.require_off('example')

    def test_saved_memory_cannot_be_used_with_changed_hardware(self):
        with patch.object(c, 'virsh', return_value='shut off\n'), patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(RuntimeError, 'saved memory'):
                c.require_off('example')

    def test_wrapper_preserves_renderer_sandbox_and_pat_workarounds(self):
        import tempfile
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'wrapper.py'
            # Intercept exec in a subprocess, proving the resulting invocation.
            script = c.wrapper('/candidate/qemu').replace('os.execv(binary, [binary, *args])', 'print(repr([binary, *args]))')
            path.write_text(script)
            output = subprocess.check_output([sys.executable, str(path), '-accel', 'kvm', '-sandbox',
                                              'on,elevateprivileges=deny,spawn=deny'], text=True)
            self.assertIn('honor-guest-pat=on', output)
            self.assertIn('elevateprivileges=deny,spawn=allow', output)


if __name__ == '__main__':
    unittest.main()
