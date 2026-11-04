#!/usr/bin/env python3
"""WinTide desktop, SSH and application command. No shell evaluation of app data."""
import argparse
import hashlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from terminal_ui import Progress


def execute(argv, **kwargs):
    return subprocess.run([str(x) for x in argv], check=True, **kwargs)


def privileged(argv):
    if os.geteuid() == 0:
        return list(argv)
    if sys.stdin.isatty():
        return ['sudo', '--', *argv]
    if subprocess.run(['sudo', '-n', 'true'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        return ['sudo', '-n', '--', *argv]
    if shutil.which('pkexec'):
        return ['pkexec', *argv]
    raise RuntimeError('Starting this VM needs authorization. Run wintide --start in a terminal first.')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)


def app_id(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
        raise ValueError('App IDs use letters, numbers, underscores and hyphens.')
    return value


def read_info(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key in {'NAME', 'FULL_NAME', 'WIN_EXECUTABLE'}:
            parts = shlex.split(value)
            if len(parts) == 1:
                result[key] = parts[0]
    return result


def desktop_arg(value):
    # Desktop Entry Exec quoting is different from shell quoting.
    if any(ord(c) < 32 for c in value):
        raise ValueError('Control characters are not valid in a desktop command.')
    value = value.replace('%', '%%')
    for char in ['\\', '"', '`', '$']:
        value = value.replace(char, '\\' + char)
    # Desktop-file value escaping is decoded before Exec's argument quoting.
    return '"' + value.replace('\\', '\\\\') + '"'


class Client:
    def __init__(self, path, plain=False, timeout=120):
        self.path = Path(path).expanduser().resolve()
        self.config = json.loads(self.path.read_text())
        self.domain = app_id(self.config['domain'])
        self.uri = self.config.get('uri', 'qemu:///system')
        if self.uri != 'qemu:///system':
            raise ValueError('Only system libvirt is supported.')
        self.apps = Path(self.config['app_dir']).expanduser()
        self.plain = plain
        self.timeout = timeout

    def virsh(self, *args):
        return execute(['virsh', '-c', self.uri, *args], capture_output=True, text=True).stdout.strip()

    def state(self):
        # virsh text output is parsed only in the C locale.
        return execute(['virsh', '-c', self.uri, 'domstate', self.domain],
                       env={**os.environ, 'LC_ALL': 'C'}, capture_output=True, text=True).stdout.strip()

    def runtime_command(self, mode):
        if mode in {'start','stop'} and self.config.get('existing_'+mode):
            return [self.config['existing_'+mode]]
        root = Path('/etc/wintide') / self.domain
        if not (root / 'config.json').exists():
            raise RuntimeError('Host integration is missing. Complete setup first; raw disks will not be started unguarded.')
        return privileged(['/usr/bin/python3', str(root/'runtime.py'), str(root/'config.json'), mode])

    def start(self):
        state = self.state()
        if state == 'running':
            return
        if state == 'paused':
            self.virsh('resume', self.domain)
            return
        if state != 'shut off':
            raise RuntimeError(f'Windows is {state}; refusing an automatic restart.')
        command = self.runtime_command('start')
        with Progress(plain=self.plain).step('Starting Windows'):
            execute(command)
            deadline = time.monotonic() + self.timeout
            while self.state() != 'running':
                if time.monotonic() >= deadline:
                    raise RuntimeError('Windows did not reach running state before the timeout.')
                time.sleep(1)

    def guest_address(self):
        if self.config.get('guest_address'):
            return str(ipaddress.ip_address(self.config['guest_address']))
        addresses = set()
        for source in ['lease', 'agent', 'arp']:
            try:
                output = self.virsh('domifaddr', self.domain, '--source', source)
            except subprocess.CalledProcessError:
                continue
            for match in re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}/\d+\b', output):
                ip = ipaddress.ip_interface(match).ip
                if not ip.is_loopback and not ip.is_link_local:
                    addresses.add(str(ip))
            if addresses:
                break
        if len(addresses) != 1:
            raise RuntimeError('Cannot identify one Windows address. Set guest_address in ' + str(self.path))
        return addresses.pop()

    def wait_rdp(self):
        deadline = time.monotonic() + self.timeout
        with Progress(plain=self.plain).step('Waiting for Windows Remote Desktop'):
            while True:
                try:
                    with socket.create_connection((self.guest_address(), self.config.get('rdp_port', 3389)), timeout=2):
                        return
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError('RDP is not ready. Run wintide --test for diagnostics.')
                    time.sleep(1)

    def launch(self, args):
        if not os.environ.get('WAYLAND_DISPLAY') and not os.environ.get('DISPLAY'):
            raise RuntimeError('Launch graphical apps from your desktop session. Use --ssh for terminal access.')
        if args and args[0] not in {'windows', 'manual'}:
            ident = app_id(args[0])
            if not (self.apps/ident/'info').is_file():
                raise RuntimeError(f'Unknown app {ident!r}. Use wintide apps list or apps refresh.')
            defaults = self.config.get('app_arguments', {}).get(ident, [])
            extra = self.apps/ident/'arguments.json'
            if extra.exists():
                defaults = json.loads(extra.read_text())
            if not isinstance(defaults, list) or not all(isinstance(a, str) for a in defaults):
                raise ValueError('Invalid app arguments metadata.')
            args = [ident, *defaults, *args[1:]]
        self.start()
        self.wait_rdp()
        # Preserve the tested WinApps core and FreeRDP askpass credential path.
        env = {**os.environ, 'LIBVIRT_DEFAULT_URI': self.uri, 'WINTIDE_SESSION_REUSE': '1'}
        return subprocess.call([self.config['core'], *args], env=env)

    def ssh_command(self, command=(), batch=False):
        conf = self.config.get('ssh') or {}
        if not conf.get('enabled'):
            raise RuntimeError('SSH was not configured. Run setup with SSH enabled or configure an existing SSH connection.')
        argv = ['ssh', '-x', '-a', '-o', 'ClearAllForwardings=yes', '-o', 'PermitLocalCommand=no',
                '-o', 'RemoteCommand=none', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new']
        if batch:
            argv += ['-o', 'BatchMode=yes']
        if conf.get('config_file'):
            argv += ['-F', str(Path(conf['config_file']).expanduser())]
        if conf.get('identity_file'):
            argv += ['-i', str(Path(conf['identity_file']).expanduser()), '-o', 'IdentitiesOnly=yes']
        if conf.get('port'):
            argv += ['-p', str(int(conf['port']))]
        if conf.get('user'):
            argv += ['-l', conf['user']]
        target = conf.get('host') or self.guest_address()
        if not target or target.startswith('-') or any(c.isspace() for c in target):
            raise ValueError('Invalid SSH destination.')
        argv += ['-t' if not command and sys.stdin.isatty() else '-T', target, *command]
        return argv

    def ssh(self, command):
        if not (self.config.get('ssh') or {}).get('enabled'):
            raise RuntimeError('SSH is not configured for this installation.')
        self.start()
        # Never enter the RDP path or start any graphical client here.
        deadline=time.monotonic()+self.timeout
        with Progress(plain=self.plain).step('Waiting for Windows SSH'):
            while True:
                try:
                    argv=self.ssh_command(command)
                    connection=self.ssh_command()
                    resolved=execute([connection[0],'-G',*connection[1:]],capture_output=True,text=True)
                    settings=dict(line.split(None,1) for line in resolved.stdout.splitlines() if ' ' in line)
                    with socket.create_connection((settings['hostname'],int(settings.get('port',22))),timeout=2):break
                except (OSError,RuntimeError,subprocess.SubprocessError):
                    if time.monotonic()>=deadline:raise RuntimeError('Windows SSH is not ready before the timeout')
                    time.sleep(1)
        return subprocess.call(argv)

    def records(self):
        result = []
        for path in sorted(self.apps.glob('*/info')):
            try:
                ident = app_id(path.parent.name)
                data = read_info(path)
                result.append((ident, data.get('NAME', ident)))
            except (ValueError, OSError):
                continue
        return result

    def desktop(self, ident, name):
        dest = Path(self.config.get('desktop_dir', str(Path.home()/'.local/share/applications')))
        dest.mkdir(parents=True, exist_ok=True)
        name = name.replace('\\', '\\\\').replace('\n', ' ').replace('\r', ' ')
        command = ' '.join(desktop_arg(v) for v in [self.config['command'], 'app', app_id(ident)])
        text = f'[Desktop Entry]\nType=Application\nName={name} (Windows)\nExec={command}\nIcon=applications-other\nTerminal=false\nCategories=Utility;\nX-WinTide=true\n'
        prefix=app_id(self.config.get('desktop_prefix','wintide'))
        target = dest/f'{prefix}-{ident}.desktop'
        if target.exists() and 'X-WinTide=true' not in target.read_text() and ' (Windows VM)' not in target.read_text():
            raise RuntimeError(f'Refusing to overwrite an unrelated entry: {target}')
        target.write_text(text)
        return target

    def refresh(self):
        self.start()
        setup = Path(__file__).with_name('setup.py')
        command = privileged(['/usr/bin/python3', str(setup), '--config', self.config['setup_config'], 'discover','--app-dir',str(self.apps)])
        with Progress(plain=self.plain).step('Discovering installed Windows apps'):
            execute(command)
        self.entries()

    def entries(self):
        records = self.records()
        for ident, name in records:
            self.desktop(ident, name)
        print(f'Added/updated {len(records)} WinTide desktop entries.')

    def add(self, name, exe, ident=None, arguments=()):
        if any(ord(c) < 32 for c in name+exe) or not re.match(r'^[A-Za-z]:\\.+\.exe$', exe, re.I):
            raise ValueError('Supply a display name and an absolute Windows .exe path.')
        ident = app_id(ident or (re.sub('[^a-z0-9]+', '-', name.lower()).strip('-') or 'app') + '-' + hashlib.sha256(exe.casefold().encode()).hexdigest()[:8])
        dest = self.apps/ident
        if dest.exists():
            raise RuntimeError(f'App {ident} already exists; choose another --id or remove its entry first.')
        dest.mkdir(parents=True)
        fields = {'NAME': name, 'FULL_NAME': name, 'WIN_EXECUTABLE': exe, 'CATEGORIES': 'Utility', 'MIME_TYPES': ''}
        (dest/'info').write_text(''.join(k+'='+shlex.quote(v)+'\n' for k,v in fields.items()))
        atomic_json(dest/'arguments.json', list(arguments))
        atomic_json(dest/'wintide-managed.json', {'created_by': 'wintide'})
        self.desktop(ident, name)
        print(f'Added {name}: wintide app {ident}')

    def remove(self, ident):
        ident = app_id(ident)
        prefix=app_id(self.config.get('desktop_prefix','wintide'))
        desktop = Path(self.config.get('desktop_dir', str(Path.home()/'.local/share/applications')))/f'{prefix}-{ident}.desktop'
        if desktop.exists():
            if 'X-WinTide=true' not in desktop.read_text():
                raise RuntimeError('This desktop entry is not managed by the current WinTide command.')
            desktop.unlink()
        dest = self.apps/ident
        if (dest/'wintide-managed.json').exists():
            for name in ['info', 'arguments.json', 'wintide-managed.json']:
                (dest/name).unlink(missing_ok=True)
            if not any(dest.iterdir()):
                dest.rmdir()
        print('Removed the WinTide entry. Nothing was uninstalled from Windows.')

    def test(self):
        failures = 0
        def check(label, operation):
            nonlocal failures
            try:
                detail = operation()
                print(f'PASS  {label}' + (f': {detail}' if detail else ''))
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
                failures += 1
                print(f'FAIL  {label}: {e}')
        def core():
            if not os.access(self.config['core'], os.X_OK):
                raise RuntimeError('Launcher core is not executable')
        check('Launcher', core)
        check('VM state', self.state)
        check('Windows address', self.guest_address)
        def port():
            with socket.create_connection((self.guest_address(), self.config.get('rdp_port',3389)), timeout=3):
                return 'accepting TCP connections (not an authentication or rendering test)'
        check('RDP', port)
        if (self.config.get('ssh') or {}).get('enabled'):
            check('SSH authentication', lambda: execute(self.ssh_command(['echo', 'WinTide-SSH-OK'], batch=True), capture_output=True, text=True, timeout=30).stdout.strip())
        print(f'{len(self.records())} app definitions. No graphical sessions were opened.')
        return 1 if failures else 0


def parser():
    p = argparse.ArgumentParser(prog='wintide',description='WinTide — Windows apps. Linux flow.', epilog='With no command, opens and logs into the Windows desktop. Apps share one SDL RemoteApp connection.')
    p.add_argument('--config', default=str(Path.home()/'.config/wintide/client.json'), help='client configuration JSON')
    p.add_argument('--plain', action='store_true', help='disable animations and ANSI output')
    p.add_argument('--timeout', type=int, default=120, help='startup/readiness timeout in seconds')
    modes = p.add_mutually_exclusive_group()
    descriptions={'ssh':'terminal-only SSH; optional remote command follows','test':'check VM, RDP and SSH without opening apps','status':'show the current VM state','start':'start Windows using the disk guard','stop':'request a clean shutdown; never force-stop','desktop':'open and log into the full Windows desktop'}
    for flag,description in descriptions.items():
        modes.add_argument('--'+flag, action='store_true',help=description)
    modes.add_argument('--app', metavar='ID')
    modes.add_argument('--add-apps', action='store_true', help='discover apps and install desktop entries')
    p.add_argument('command', nargs='?', help='app, manual, apps, ssh, desktop, start, stop, status, test, setup')
    p.add_argument('arguments', nargs=argparse.REMAINDER)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.timeout <= 0:
        raise ValueError('--timeout must be positive')
    if args.command == 'setup':
        return subprocess.call([sys.executable, str(Path(__file__).with_name('setup.py')), *args.arguments])
    client = Client(args.config, args.plain, args.timeout)
    flag = next((name for name in ['ssh','test','status','start','stop','desktop','app','add_apps'] if getattr(args,name)), None)
    command = flag or args.command or 'desktop'
    rest = ([args.command] if flag and args.command else []) + args.arguments
    if rest[:1] == ['--']:
        rest = rest[1:]
    if command == 'ssh':
        return client.ssh(rest)
    if command == 'test':
        return client.test()
    if command == 'status':
        print(f'{client.domain}: {client.state()}'); return 0
    if command == 'start':
        client.start(); return 0
    if command == 'stop':
        execute(client.runtime_command('stop')); return 0
    if command in {'desktop', 'windows'}:
        return client.launch(['windows', *rest])
    if command == 'manual':
        if not rest: raise ValueError('Usage: wintide manual C:\\Path\\app.exe [arguments]')
        return client.launch(['manual', *rest])
    if command == 'app':
        values = ([args.app] if args.app else []) + rest
        if not values: raise ValueError('Usage: wintide app ID [arguments]')
        return client.launch(values)
    if command == 'add_apps':
        client.refresh(); return 0
    if command == 'apps':
        ap = argparse.ArgumentParser(prog='wintide apps')
        sub = ap.add_subparsers(dest='action', required=True)
        for action in ['list', 'refresh', 'entries']:
            sub.add_parser(action)
        add = sub.add_parser('add');add.add_argument('--name',required=True);add.add_argument('--exe',required=True);add.add_argument('--id');add.add_argument('args',nargs=argparse.REMAINDER)
        remove=sub.add_parser('remove');remove.add_argument('id')
        a=ap.parse_args(rest)
        if a.action=='list':
            for ident,name in client.records():print(f'{ident:38} {name}')
        elif a.action=='refresh':client.refresh()
        elif a.action=='entries':client.entries()
        elif a.action=='add':client.add(a.name,a.exe,a.id,a.args[1:] if a.args[:1]==['--'] else a.args)
        elif a.action=='remove':client.remove(a.id)
        return 0
    # Keep existing desktop files invoking `wintide APP_ID` compatible.
    return client.launch([command, *rest])


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'WinTide: {error}', file=sys.stderr)
        sys.exit(1)
