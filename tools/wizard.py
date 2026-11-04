"""Guided, checkpointed orchestration of the existing reviewed setup operations."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from terminal_ui import Progress, logged_run
from wintide import atomic_json


def guest_lifecycle(c, mode):
    import setup
    import runtime
    if os.geteuid() != 0:
        raise RuntimeError('Guest lifecycle operations require sudo')
    if mode == 'prepare-guest':
        state = runtime.state(c)
        if state == 'running':
            return
        if state != 'shut off':
            raise RuntimeError('Base VM must be running or cleanly shut off')
        installed = Path('/etc/wintide')/c['domain']
        if (installed/'config.json').exists():
            setup.show_run('/usr/bin/python3',str(installed/'runtime.py'),str(installed/'config.json'),'start')
        else:
            # The plan was validated before this stage. This is still the user's base VM.
            runtime.prepare(c,Path('/run/wintide')/c['domain'])
            runtime.v(c,'start',c['domain'])
        return
    if mode == 'shutdown-guest':
        if runtime.state(c) == 'shut off':
            return
        runtime.v(c,'shutdown',c['domain'])
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if mode == 'shutdown-guest':
            if runtime.state(c) == 'shut off':
                return
        else:
            try:
                runtime.agent(c,'guest-ping')
                return
            except (subprocess.SubprocessError,KeyError,ValueError):
                pass
        time.sleep(2)
    raise RuntimeError('Timed out waiting for '+('clean shutdown; no force-stop performed' if mode=='shutdown-guest' else 'QEMU Guest Agent'))


class Checkpoints:
    def __init__(self, path, fingerprint):
        self.path = Path(path)
        self.data = {'fingerprint': fingerprint, 'completed': []}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get('fingerprint') != fingerprint:
                raise RuntimeError(f'Setup inputs changed since the previous attempt. Review {self.path} and the installed state before starting a different plan.')

    def run(self, name, operation, progress):
        if name in self.data['completed']:
            progress.done += 1
            print(progress.line(name+' (previously completed)', '✓'), file=progress.stream)
            return
        operation()
        self.data['completed'].append(name)
        atomic_json(self.path,self.data)


def install(c, args):
    import setup
    if os.geteuid()==0 or os.getuid()!=c['uid']:
        raise RuntimeError('Run guided setup as desktop_user. It requests sudo only for system stages.')
    if not args.windows_user:
        if not sys.stdin.isatty():raise ValueError('--windows-user is required')
        args.windows_user=input('Local Windows account name: ').strip()
    if not args.windows_user:raise ValueError('A Windows account is required')
    required=['sudo','virsh','git','meson','ninja','cmake','pkg-config','gcc','g++','lsblk','losetup','blockdev','virt-xml-validate','qemu-img']
    if not args.skip_ssh:required+=['ssh','ssh-keygen']
    if c.get('shared_directory') and c.get('share_permission_guard',True):required+=['cargo']
    missing=[x for x in required if not shutil.which(x)]
    if missing:raise RuntimeError('Install host prerequisites first: '+', '.join(missing)+'; see docs/requirements.md')
    if args.yes and not args.enable_test_signing:
        raise RuntimeError('Unattended driver setup requires --enable-test-signing; see docs/security.md')
    if args.yes and c.get('disk_mode','physical')=='physical' and not args.disable_hibernation:
        raise RuntimeError('Physical-disk guided setup also requires --disable-hibernation')
    if not args.skip_ssh and not args.ssh_key:
        args.ssh_key=str(Path(c['home'])/'.ssh'/('wintide_'+c['domain']))
    work=Path(c['work_dir'])/'setup'
    work.mkdir(parents=True,exist_ok=True,mode=0o700);work.chmod(0o700)
    raw={'config':c,'user':args.windows_user,'ssh_key':args.ssh_key,'skip_ssh':args.skip_ssh}
    fingerprint=hashlib.sha256(json.dumps(raw,sort_keys=True).encode())
    files=[setup.ROOT/'components.lock.json']
    for folder,pattern in [('tools','*.py'),('guest','*.ps1'),('patches','*.patch')]:
        files.extend(sorted((setup.ROOT/folder).glob(pattern)))
    for file in files:
        fingerprint.update(str(file.relative_to(setup.ROOT)).encode())
        fingerprint.update(file.read_bytes())
    checkpoint=Checkpoints(work/(c['domain']+'-steps.json'),fingerprint.hexdigest())
    config=Path(args.config).resolve()
    base=[sys.executable,str(setup.ROOT/'tools/setup.py'),'--config',str(config),'--plan-dir',str(Path(args.plan_dir).resolve())]
    logs=work/(c['domain']+'-logs');logs.mkdir(exist_ok=True,mode=0o700)
    def command(name, extra=(), root=False, interactive=False):
        argv=[*base,name,*extra]
        if root:
            argv=['sudo','-n','--',*argv]
        if interactive:
            subprocess.run(argv,check=True)
        else:
            logged_run(argv,logs/(name+'-'+('-'.join(extra[:2]).replace('/','_') or 'step')+'.log'))
    def ready():
        command('prepare-guest',root=True)
        command('wait-guest',root=True)
    def key():
        path=Path(args.ssh_key).expanduser();path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not path.exists():
            logged_run(['ssh-keygen','-q','-t','ed25519','-N','','-C','WinTide','-f',str(path)],logs/'ssh-key.log')
        if not Path(str(path)+'.pub').exists():raise RuntimeError('SSH public key is missing: '+str(path)+'.pub')
        if path.stat().st_mode & 0o077:raise RuntimeError('Protect the SSH private key with chmod 600 before continuing')
    def guest(mode):
        # A resumed setup may find Windows powered off; readiness is not a stale checkpoint.
        ready()
        options=['--guest-mode',mode,'--windows-user',args.windows_user]
        if mode=='yttrium':
            options+=['--enable-test-signing']
            if args.disable_hibernation:options+=['--disable-hibernation']
        if mode=='ssh':options+=['--ssh-key',args.ssh_key]
        command('guest',options,root=True)
    def install_client():
        options=['--windows-user',args.windows_user]
        if not args.skip_ssh:options+=['--ssh-key',args.ssh_key]
        if args.password_file:options+=['--password-file',str(Path(args.password_file).expanduser().resolve())]
        command('install-client',options,interactive=not args.password_file)
    def discovery():
        ready();command('discover',root=True);command('launchers')
    def verify():
        from wintide import Client
        client=Client(setup.client_paths(c)[1]/'client.json',plain=True,timeout=180)
        client.wait_rdp()
        logged_run([str(setup.client_paths(c)[2]),'--plain','--test'],logs/'verify.log')
    stages=[('Build pinned host components',lambda:command('build',['--jobs',str(args.jobs)]),False),
            ('Enable Windows RemoteApps',lambda:guest('rdp'),False)]
    if not args.skip_ssh:
        stages += [('Prepare SSH key',key,False),('Configure Windows SSH',lambda:guest('ssh'),False)]
    stages += [('Install matching graphics driver',lambda:guest('yttrium'),False),
               ('Shut Windows down cleanly',lambda:command('shutdown-guest',root=True),False),
               ('Install guarded libvirt integration',lambda:command('apply-host',root=True),False),
               ('Start Windows and wait for guest agent',ready,False)]
    if c.get('shared_directory'):
        stages += [('Configure optional file sharing',lambda:guest('share'),False)]
    stages += [('Install WinTide command and login profile',install_client,not args.password_file),
               ('Discover apps and add desktop entries',discovery,False),
               ('Verify Windows connections',verify,False)]
    progress=Progress(len(stages)+1,plain=args.plain);progress.banner()
    print('Domain:',c['domain'],'  Storage:',c.get('disk_mode','physical'))
    print('Logs:',logs)
    def plan():
        with progress.step('Generate reviewable VM plan'):
            command('plan')
    checkpoint.run('Generate reviewable VM plan',plan,progress)
    print('Review:',Path(args.plan_dir).resolve()/'domain.wintide.xml')
    print('Setup installs the test-signed graphics driver, configures RDP'+(' and key-only SSH' if not args.skip_ssh else '')+', and shuts down/restarts Windows. Save Windows work first.')
    if not args.yes:
        if not sys.stdin.isatty():raise RuntimeError('Review the plan, then rerun with --yes --enable-test-signing (and --disable-hibernation for physical disks).')
        if input('Apply this plan and enable Windows test signing? [y/N] ').strip().lower() not in ['y','yes']:
            raise RuntimeError('Stopped after planning; no VM settings changed.')
        args.enable_test_signing=True
        if c.get('disk_mode','physical')=='physical' and not args.disable_hibernation:
            if input('Disable Windows hibernation/Fast Startup for the shared physical installation? [y/N] ').strip().lower() not in ['y','yes']:
                raise RuntimeError('Physical-disk setup requires hibernation to be disabled.')
            args.disable_hibernation=True
    for name, action, interactive in stages:
        def operation(action=action,name=name,interactive=interactive):
            if name not in ['Build pinned host components','Prepare SSH key','Install WinTide command and login profile','Verify Windows connections']:
                # Authenticate outside the spinner so sudo's prompt stays visible.
                subprocess.run(['sudo','-v'],check=True)
            with progress.step(name,animate=not interactive):action()
        checkpoint.run(name,operation,progress)
    installed=setup.client_paths(c)[2].name
    print('\nWinTide is installed. Run: '+installed+' --test')
    print('Desktop: '+installed+'    Apps: '+installed+' apps list'+('    SSH: '+installed+' --ssh' if not args.skip_ssh else ''))
    print('Completed stages are checkpointed. Re-running the same setup resumes unfinished stages; failed stages are not marked complete.')
