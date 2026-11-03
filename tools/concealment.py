#!/usr/bin/env python3
"""Opt-in metadata candidate. Never stops a VM or accesses its physical disks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
Q = 'http://libvirt.org/schemas/domain/qemu/1.0'
ET.register_namespace('qemu', Q)
LOCK = json.loads((ROOT / 'components.lock.json').read_text())


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def virsh(*args):
    return subprocess.check_output(['virsh', '-c', 'qemu:///system', *args], text=True)


def require_off(domain):
    if virsh('domstate', domain).strip() != 'shut off':
        raise RuntimeError('Shut down using the existing disk-guarded stop command first')
    saved = subprocess.run(['virsh', '-c', 'qemu:///system', 'managedsave-dumpxml', domain], capture_output=True)
    if saved.returncode == 0:
        raise RuntimeError('Resume the saved memory state and shut Windows down fully first')


def source(name, work, patch):
    target = work / name
    if not target.exists():
        run('git', 'init', target)
        run('git', '-C', target, 'remote', 'add', 'origin', LOCK[name]['url'])
        run('git', '-C', target, 'fetch', '--depth', '1', 'origin', LOCK[name]['commit'])
        run('git', '-C', target, 'checkout', '--detach', LOCK[name]['commit'])
    head = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
    if head != LOCK[name]['commit']:
        raise RuntimeError('Wrong source revision: ' + str(target))
    # A separate index verifies the COMPLETE working diff, not merely that the
    # expected patch can be reversed. Preserve and reject unrelated local edits.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=tmp + '/index')
        run('git', '-C', target, 'read-tree', 'HEAD', env=env)
        expected = ROOT / 'patches' / patch
        dirty = subprocess.check_output(['git', '-C', str(target), 'diff', 'HEAD', '--binary'])
        if dirty:
            run('git', '-C', target, 'apply', '--cached', expected, env=env)
            run('git', '-C', target, 'diff', '--exit-code', env=env, stdout=subprocess.DEVNULL)
        else:
            run('git', '-C', target, 'apply', expected)
    if subprocess.check_output(['git', '-C', str(target), 'ls-files', '--others', '--exclude-standard']):
        raise RuntimeError('Untracked source files require review: ' + str(target))
    return target


def build(args):
    if os.geteuid() == 0:
        raise RuntimeError('Build as the desktop user, never root')
    work, prefix, renderer = args.work.resolve(), args.prefix.resolve(), args.renderer_prefix.resolve()
    if prefix == renderer:
        raise ValueError('Candidate prefix must differ from the working renderer/QEMU prefix')
    work.mkdir(parents=True, exist_ok=True)
    qemu = source('qemu', work, 'qemu-metadata.patch')
    edk = source('edk2', work, 'ovmf-metadata.patch')
    builddir = work / 'build-qemu'
    builddir.mkdir(exist_ok=True)
    env = dict(os.environ, PKG_CONFIG_PATH=f'{renderer}/lib/pkgconfig:{renderer}/share/pkgconfig',
               LDFLAGS=f'-Wl,-rpath,{renderer}/lib')
    run(qemu / 'configure', f'--prefix={prefix}', '--libdir=lib', '--target-list=x86_64-softmmu',
        '--enable-kvm', '--enable-slirp', '--disable-fdt', '--enable-virglrenderer', '--enable-opengl',
        '--enable-gtk', '--enable-spice', '--enable-spice-protocol', '--enable-pa', '--audio-drv-list=pa',
        '--disable-docs', '--disable-werror', '--disable-guest-agent', '--disable-vte', '--disable-sdl', cwd=builddir, env=env)
    run('ninja', '-C', builddir, f'-j{args.jobs}', 'install')
    modules = ['CryptoPkg/Library/OpensslLib/openssl', 'CryptoPkg/Library/MbedTlsLib/mbedtls',
               'BaseTools/Source/C/BrotliCompress/brotli', 'MdeModulePkg/Library/BrotliCustomDecompressLib/brotli',
               'MdePkg/Library/BaseFdtLib/libfdt', 'MdePkg/Library/MipiSysTLib/mipisyst',
               'SecurityPkg/DeviceSecurity/SpdmLib/libspdm', 'TcgTpmPkg/Library/TpmLib/TPM',
               'MdeModulePkg/Universal/RegularExpressionDxe/oniguruma']
    run('git', '-C', edk, 'submodule', 'update', '--init', '--depth', '1', '--jobs', str(args.jobs), *modules)
    run('make', '-C', edk / 'BaseTools', f'-j{args.jobs}')
    script = 'export WORKSPACE="$PWD"; source edksetup.sh >/dev/null; build -a X64 -b RELEASE -t GCC -p OvmfPkg/OvmfPkgX64.dsc -n "$1" -D FD_SIZE_4MB=TRUE -D SMM_REQUIRE=TRUE -D SECURE_BOOT_ENABLE=TRUE -D TPM2_ENABLE=TRUE'
    run('bash', '-c', script, 'firmware-build', str(args.jobs), cwd=edk)
    dest = prefix / 'share/firmware'
    dest.mkdir(parents=True, exist_ok=True)
    for part in ['CODE', 'VARS']:
        shutil.copy2(edk / f'Build/OvmfX64/RELEASE_GCC/FV/OVMF_{part}.fd', dest / f'OVMF_{part}.4m.fd')
    verify_firmware(dest)


def verify_firmware(directory):
    for part, size in [('CODE', 3653632), ('VARS', 540672)]:
        if (directory / f'OVMF_{part}.4m.fd').stat().st_size != size:
            raise ValueError('Unsupported firmware layout: ' + part)


def transform(xml, emulator, code, nvram, template, identity, profile):
    root = ET.fromstring(xml)
    if root.find('sysinfo') is not None or root.find('os/smbios') is not None:
        raise ValueError('Existing SMBIOS configuration requires manual integration')
    if root.findall('devices/hostdev'):
        raise ValueError('Passthrough devices require separate review')
    osnode = root.find('os')
    if osnode is None or osnode.find('loader') is None or osnode.find('nvram') is None:
        raise ValueError('An existing explicit OVMF configuration is required')
    if (osnode.find("firmware/feature[@name='secure-boot'][@enabled='yes']") is not None
            or osnode.find('loader').get('secure') == 'yes'):
        raise ValueError('This experimental-driver recipe requires Secure Boot already disabled')
    # Explicit firmware paths are outside libvirt's auto-selection descriptors.
    # Use manual pflash selection instead of adding a global firmware override.
    osnode.attrib.pop('firmware', None)
    firmware = osnode.find('firmware')
    if firmware is not None:
        osnode.remove(firmware)
    osnode.find('loader').set('secure', 'no')
    model = root.find('cpu/model')
    if model is None or not model.text:
        raise ValueError('Preserve an explicit working CPU model before proceeding')
    command = root.find('{' + Q + '}commandline')
    if command is None:
        command = ET.SubElement(root, '{' + Q + '}commandline')
    if any(x.get('value') == '-smbios' for x in command.findall('{' + Q + '}arg')):
        raise ValueError('Existing custom SMBIOS arguments require review')
    root.find('devices/emulator').text = str(emulator)
    osnode.find('loader').text = str(code)
    varsnode = osnode.find('nvram')
    varsnode.text = str(nvram)
    varsnode.set('template', str(template))
    varsnode.set('templateFormat', 'raw')
    # Identity values are labels only; never propagate host UUID/serial numbers.
    def escaped(value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('Invalid SMBIOS text')
        return value.replace(',', ',,')
    options = ['type=0,vendor=OEM,version=1.0,uefi=on,vm=off',
               'type=1,manufacturer=' + escaped(identity['manufacturer']) + ',product=' + escaped(identity['product']),
               'type=2,manufacturer=' + escaped(identity['manufacturer']) + ',product=' + escaped(identity['board']),
               'type=3,manufacturer=' + escaped(identity['manufacturer'])]
    for value in options:
        ET.SubElement(command, '{' + Q + '}arg', {'value': '-smbios'})
        ET.SubElement(command, '{' + Q + '}arg', {'value': value})
    # Do not silently remove device integration or Hyper-V performance features.
    if profile == 'cpu-hidden':
        cpu = root.find('cpu')
        for feature in list(cpu.findall("feature[@name='hypervisor']")):
            cpu.remove(feature)
        ET.SubElement(cpu, 'feature', {'policy': 'disable', 'name': 'hypervisor'})
        features = root.find('features')
        if features is None:
            features = ET.SubElement(root, 'features')
        kvm = features.find('kvm')
        if kvm is None:
            kvm = ET.SubElement(features, 'kvm')
        hidden = kvm.find('hidden')
        if hidden is None:
            hidden = ET.SubElement(kvm, 'hidden')
        hidden.set('state', 'on')
        hyperv = features.find('hyperv')
        if hyperv is not None:
            vendor = hyperv.find('vendor_id')
            if vendor is None:
                vendor = ET.SubElement(hyperv, 'vendor_id')
            vendor.set('state', 'on')
            vendor.set('value', 'GenuineIntel')
    ET.indent(root)
    return ET.tostring(root, encoding='unicode') + '\n'


def wrapper(binary):
    return '''#!/usr/bin/python3
import os, sys
binary = %r
args = sys.argv[1:]
for i, value in enumerate(args[:-1]):
    if value == '-accel' and args[i+1].split(',')[0] == 'kvm' and 'honor-guest-pat=' not in args[i+1]:
        args[i+1] += ',honor-guest-pat=on'
    if value == '-sandbox':
        args[i+1] = args[i+1].replace('spawn=deny', 'spawn=allow')
os.execv(binary, [binary, *args])
''' % str(binary)


def stage(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.domain):
        raise ValueError('Invalid domain name')
    out = args.out.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Use an empty private staging directory')
    out.chmod(0o700)
    prefix = args.prefix.resolve()
    binary = prefix / 'bin/qemu-system-x86_64'
    if not binary.is_file():
        raise ValueError('Build candidate QEMU first')
    firmware = prefix / 'share/firmware'
    verify_firmware(firmware)
    xml = virsh('dumpxml', args.domain, '--inactive')
    original = ET.fromstring(xml)
    nvram = Path(original.find('os/nvram').text)
    if nvram.stat().st_size != 540672:
        raise ValueError('Existing NVRAM layout differs')
    if Path(original.find('os/loader').text).stat().st_size != 3653632:
        raise ValueError('Existing firmware layout differs')
    target = f'/usr/local/libexec/{args.domain}-concealment-{args.profile}-qemu'
    candidate_vars = nvram.with_name(args.domain + '-concealment-' + args.profile + '_VARS.fd')
    identity = {key: Path('/sys/class/dmi/id/' + field).read_text().strip() for key, field in
                [('manufacturer', 'sys_vendor'), ('product', 'product_name'), ('board', 'board_name')]}
    candidate = transform(xml, target, firmware / 'OVMF_CODE.4m.fd', candidate_vars,
                          firmware / 'OVMF_VARS.4m.fd', identity, args.profile)
    (out / 'domain.before.xml').write_text(xml)
    (out / 'domain.candidate.xml').write_text(candidate)
    (out / 'qemu-wrapper.py').write_text(wrapper(binary))
    state = dict(domain=args.domain, uuid=original.findtext('uuid'), wrapper=target,
                 original_nvram=str(nvram), candidate_nvram=str(candidate_vars), profile=args.profile,
                 original_sha256=hashlib.sha256(xml.encode()).hexdigest())
    (out / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
    for path in out.iterdir():
        path.chmod(0o600)
    run('virt-xml-validate', out / 'domain.candidate.xml', 'domain')
    print('Staged only; VM unchanged:', out)


def activate(args):
    out = args.out.resolve()
    state = json.loads((out / 'state.json').read_text())
    if os.geteuid() != 0:
        raise RuntimeError('Activation/rollback requires root')
    require_off(state['domain'])
    current = virsh('dumpxml', state['domain'], '--inactive')
    if args.action == 'activate':
        if (out / 'activated').exists():
            raise RuntimeError('This staging directory was already activated')
        if hashlib.sha256(current.encode()).hexdigest() != state['original_sha256']:
            raise RuntimeError('VM configuration changed since staging; stage again')
        source_vars = Path(state['original_nvram'])
        candidate_vars = Path(state['candidate_nvram'])
        if candidate_vars.exists() or Path(state['wrapper']).exists():
            raise RuntimeError('Candidate runtime paths already exist; review before replacing')
        shutil.copy2(source_vars, out / 'nvram.before.fd')
        shutil.copy2(source_vars, candidate_vars)
        stat = source_vars.stat()
        os.chown(candidate_vars, stat.st_uid, stat.st_gid)
        shutil.copy2(out / 'qemu-wrapper.py', state['wrapper'])
        Path(state['wrapper']).chmod(0o755)
        try:
            run('virsh', '-c', 'qemu:///system', 'define', out / 'domain.candidate.xml')
        except Exception:
            candidate_vars.unlink()
            Path(state['wrapper']).unlink()
            raise
        (out / 'activated').touch()
        (out / 'domain.activated.xml').write_text(virsh('dumpxml', state['domain'], '--inactive'))
        print('Candidate defined. Start with the existing disk-guarded start command.')
    else:
        root = ET.fromstring(current)
        if root.findtext('uuid') != state['uuid'] or root.findtext('devices/emulator') != state['wrapper']:
            raise RuntimeError('Current domain is not this candidate; refuse to overwrite newer changes')
        if current != (out / 'domain.activated.xml').read_text():
            raise RuntimeError('Candidate configuration changed after activation; review before rollback')
        run('virsh', '-c', 'qemu:///system', 'define', out / 'domain.before.xml')
        print('Original definition restored. Original firmware/NVRAM were never modified.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    b = sub.add_parser('build')
    b.add_argument('--work', type=Path, required=True)
    b.add_argument('--prefix', type=Path, required=True)
    b.add_argument('--renderer-prefix', type=Path, required=True)
    b.add_argument('--jobs', type=int, default=6)
    s = sub.add_parser('stage')
    s.add_argument('--domain', required=True)
    s.add_argument('--prefix', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--profile', choices=['metadata', 'cpu-hidden'], default='metadata')
    for name in ['activate', 'rollback']:
        sub.add_parser(name).add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    {'build': build, 'stage': stage, 'activate': activate, 'rollback': activate}[args.action](args)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
