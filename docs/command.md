# The WinTide command

Setup installs the executable command at `~/.local/bin/wintide`. It uses Python 3
and the tested WinApps core; no additional terminal UI package is required. Make
sure `~/.local/bin` is on your `PATH`.

| Command | Behavior |
|---|---|
| `wintide` or `wintide --desktop` | Start the VM through its disk guard if needed, wait for RDP, and log into the full Windows desktop using the existing askpass credentials. |
| `wintide --ssh` | Start the VM if needed, wait for SSH, and open a terminal session. No RDP client, X11, agent or port forwarding. |
| `wintide --ssh whoami` | Run a remote command through SSH and return its exit status. |
| `wintide app ID [arguments]` / `wintide --app ID` | Open a RemoteApp, reusing the existing SDL connection. |
| `wintide manual 'C:\Path\app.exe'` | Launch an executable without creating a desktop entry. |
| `wintide apps list` | List locally available app IDs and names. |
| `wintide apps refresh` / `wintide --add-apps` | Discover registered Windows executables through QGA and create/update WinTide desktop entries. Requires system authorization. |
| `wintide apps entries` | Generate desktop entries from existing metadata, without guest discovery. |
| `wintide apps add ...` | Define a portable/custom executable and add its desktop entry. |
| `wintide apps remove ID` | Remove the managed desktop entry; never uninstall the Windows app. Definitions imported from upstream remain. |
| `wintide --status` | Show the VM state without starting it. |
| `wintide --start` | Start Windows through the configured disk guard; no login window. |
| `wintide --stop` | Request a clean shutdown and eligible host-mount restoration; never force-stop Windows. Save work first. |
| `wintide --test` | Check the launcher, libvirt state, guest address, RDP TCP availability and configured SSH authentication. Does not start the VM or open graphical apps. |

Full-desktop login can switch the Windows session away from RemoteApps. Use
`app`, rather than bare `wintide`, to add another application without replacing
the current RemoteApp connection. SSH does not switch the graphical session.

Global options precede the command: `--plain` disables animation, `--timeout 180`
changes startup/readiness timeouts, and `--config PATH` selects a client JSON.
The normal client configuration is `~/.config/wintide/client.json`; it contains
paths/settings, not the Windows password. Fresh installations store the RDP
password separately with mode `0600` and use FreeRDP askpass. Do not put passwords
in commands or desktop files.

## Add an application

For example, if Steam is installed at its usual Windows location but was not
registered for discovery:

```sh
wintide apps add --id steam --name Steam --exe 'C:\Program Files (x86)\Steam\steam.exe'
wintide app steam
```

Add default arguments after `--`:

```sh
wintide apps add --id editor --name Editor --exe 'C:\Tools\Editor\editor.exe' -- --new-window
```

This creates metadata and a desktop entry; it does not verify that the executable
exists or install it. Arguments remain separate values, never shell expressions.
Settings uses URI activation rather than a normal portable `.exe`; fresh setup
includes its dedicated `settings-broker` entry. Explorer's `explorer-broker` opens
a new window for every invocation.

Refreshing entries affects only WinTide entries. It does not remove an older
Docker/WinApps launcher collection. A second collection can therefore coexist;
review older entries before disabling them. After a Windows app is uninstalled,
remove its stale WinTide entry explicitly.

## Add the command to an existing working installation

This adopts explicitly named existing launch/start/stop scripts. It does not
replace guest drivers, reconnect RDP, change credentials, migrate old paths or
reconfigure libvirt:

```sh
./setup.sh --config local-config.json install-command \
  --windows-user USER \
  --existing-launcher /absolute/path/to/working-launcher \
  --existing-start /absolute/path/to/guarded-start \
  --existing-stop /absolute/path/to/clean-stop \
  --app-dir /absolute/path/to/existing/apps \
  --ssh-config /absolute/path/to/ssh-config --ssh-host windows-alias
```

The existing scripts must be executable and retain their own disk guards. The
SSH alias uses your existing SSH config/keys; no Windows SSH setup is performed
in adoption mode. GUI launching is delegated to the existing launcher, so it
must already use the patched SDL client and support WinApps arguments.

`--existing-stop` is optional, but stop requires it when no standard WinTide host
runtime is installed. Existing desktop files keep their original launch commands
until you choose to generate WinTide entries.

To refresh installed command/toolkit code from a newer checkout while preserving
the client JSON and credentials:

```sh
./setup.sh --config local-config.json install-command --update-command
```

The command installs a reviewed toolkit snapshot under the WinTide app-data
directory, so it still works after the original checkout is moved. To access
individual setup operations through that snapshot, use:

```sh
wintide setup --config /absolute/path/to/setup-config.json doctor
```

## Separate test installations

Set `"client_profile": "validation"` in a separate setup config to install
`wintide-validation`, with its own credentials and app data under
`~/.config/wintide/profiles/validation/` and
`~/.local/share/wintide/profiles/validation/`. Its desktop filenames begin with
`wintide-validation-`. The default `wintide` profile stays unchanged.
Also use a separate libvirt domain, `prefix`, `work_dir` and `--plan-dir`; a client
profile alone does not isolate VM disks or host builds. For disposable testing,
use `disk_mode: "image"`, `physical_disks: []` and a standalone disk image.

## Diagnostics

`--test` is a connectivity check, not proof of successful RDP authentication,
Direct3D rendering or every application's resize behavior. Use the manual
[validation checks](validation.md) for those. If address discovery is ambiguous,
set `guest_address` in the client JSON to the VM's intended address; the command
does not guess among multiple adapters.

Graphical launches require a desktop session with `WAYLAND_DISPLAY` or `DISPLAY`.
For a stopped VM, authorization uses sudo in a terminal, cached sudo or polkit
from a desktop entry. There is no new blanket passwordless-sudo rule. SSH keeps
host-key checking enabled and uses trust-on-first-use for a new host.
