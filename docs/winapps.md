# Linux launcher integration

`install-client` fetches no account data from the existing host setup. It takes the pinned upstream WinApps core already fetched by `build`, preserves its source copyright notices, and generates an isolated copy locally. It changes only profile/app-data/source paths and the debug helper's return status. That generated third-party core is not committed or redistributed in this repository.

The profile lives in `~/.config/winapps-yttrium/`; app data lives in `~/.local/share/winapps-yttrium/`; the command is `~/.local/bin/winapps-yttrium`. Existing Docker configuration, auto-start policy, app data, and desktop files are left unchanged. If old and new launchers coexist, disable the old entries manually after making a backup. Stopping a Docker VM is not part of this installer.

After installing the client profile:

```sh
sudo ./setup.sh --config local-config.json discover
./setup.sh --config local-config.json launchers
```

Discovery queries HKLM/loaded-user App Paths registrations plus Notepad, checks that executables exist, and returns JSON through QGA. It never evaluates Windows-produced Bash. Generated metadata uses shell quoting, and desktop entry IDs use normalized names plus a path hash. UWP apps, unregistered portable apps and programs only registered for an unloaded user hive may need manual configuration. Entries are named `(Windows VM)` to distinguish them from existing launchers.

For a manual app:

```sh
winapps-yttrium manual 'C:\Windows\System32\notepad.exe'
```

For standalone Explorer, `guest/Explorer-Broker.ps1` documents the working broker approach: open a new This PC window on every launch and keep that launch process alive until its new window closes. Concurrent launches serialize window discovery, and existing folder windows are neither restored nor closed. The integration installer creates its broker launcher separately; no arbitrary Windows desktop windows are closed.

The patched client is the SDL3 `sdl-freerdp` built from FreeRDP3.32.2, not a differently named system binary. RemoteApps use `/gdi:sw -decorations +dynamic-resolution`; do not silently switch to `/gdi:hw` or `/multimon`, which regressed the reference setup. FFmpeg/swscale are disabled in this build to avoid the observed distro ABI conflict; this is not an optimal multimedia-codec preset for all hosts.

A full RDP desktop/RemoteApp session can disconnect the local VM console session. Avoid RDP validation while someone is using the Windows console. Game streaming and RDP are separate latency/compatibility questions; shared GPU acceleration does not guarantee low-latency delivery through RDP.

## Launch additional apps without reconnecting

The installed wrapper exports `WINTIDE_SESSION_REUSE=1`. On Linux, the patched
SDL client reuses an existing RemoteApp connection for the same server, port,
Windows user and domain. A subsequent invocation parses its usual `/app:` options
and forwards the program, working directory and arguments as another RAIL EXEC
request. It does not start a second RDP login or recreate existing windows.

The endpoint lives in the user's private `XDG_RUNTIME_DIR`, with owner-only socket
and lock permissions, peer UID verification, and a lock to serialize simultaneous
first launches. A failed handoff fails closed rather than opening a competing
connection. The acknowledgement means the RAIL request was submitted; Windows can
still reject a program, which is recorded in the owner's client log. A rejected
additional app does not terminate the existing session.

The first connection owns display options, redirected drives, audio and the
compositor app class. Later launches reuse those resources, so individual app-class
icon grouping is not preserved and a later `/drive:` option cannot add a new drive.
Each Explorer broker launch creates a new folder window, even if Explorer is already open.
Full-desktop launches remain separate and can still replace a RemoteApp session.
After upgrading an already-running older client, reconnect once to activate reuse.
For an existing installation, set the environment variable in its launcher wrapper;
no Windows session-policy changes are required.

## Windowed application startup

The patched SDL Wayland client keeps ordinary RemoteApp HWNDs restored inside
Windows so local tiles, floating resize, and local maximization can use the same
geometry path. Remembered startup maximization is normalized through RAIL;
later native maximize requests act on the local SDL surface. There is no
Hyprland-specific float/tile rule. See [the SDL fixes](fixes.md).

The optional helper below also handles Windows-side startup policy, but is not
a substitute for the SDL fix. Its standalone manual-maximize test expectations
apply without SDL's remote-window normalization.

`guest/windowed-helper/` is a small Rust Windows program using Microsoft's
[`windows-sys` bindings from windows-rs](https://github.com/microsoft/windows-rs).
It watches top-level windows in the interactive RDP session and calls
`ShowWindowAsync(SW_RESTORE)` once for a newly shown maximized window. It does
not maximize first, send keyboard shortcuts, change FreeRDP, or reconnect RDP.

The helper watches each new window for three seconds, allowing for apps that
apply their remembered maximize state after showing. A maximize must settle
for 300 ms before restoration. Each visible-window lifecycle receives at most one restore request; hiding and showing a reused HWND rearms it, and
manual maximization afterward is allowed. An app that maximizes itself again
after that request, or more than three seconds after appearing, is not forced
back repeatedly. Maximizing manually during that initial grace period can be
treated as a startup maximize.

Fullscreen is exempt when the window covers its monitor and is either
unmaximized (such as F11) or lacks a caption (such as borderless fullscreen).
Child windows, tool windows, cloaked windows, shell surfaces, and the RemoteApp
marker are excluded. These are Windows window-state/style checks, not a promise
to recognize every game's custom fullscreen implementation. Elevated apps may
refuse a standard-user helper's restore request.

Build separately from the GPU/RDP stack on Linux (Rust and MinGW required):

```sh
rustup target add x86_64-pc-windows-gnu
./setup.sh --config local-config.json build-windowed-helper
sudo ./setup.sh --config local-config.json install-windowed-helper --windows-user USER
```

The install command uploads the locally built executable through QEMU Guest
Agent; it does not download or execute an unreviewed release. Alternatively,
build on Windows with `cargo build --locked --release` in
`guest/windowed-helper`, then run the installer in an elevated PowerShell:

```powershell
.\guest\Install-WindowedHelper.ps1 -BinaryPath .\guest\windowed-helper\target\release\winapps-windowed.exe -WindowsUser USER
```

The scheduled task runs as that user with an interactive token, without a saved
password or elevation. Logon and RDP reconnect triggers start it alongside
WinApps, including reuse of an existing RemoteApp session. A session-local mutex
prevents duplicate helpers. It stays available for subsequent app launches and
is inactive on the native console. Already visible windows are included when
the helper first starts. No per-app launchers need modification.

Installation starts it immediately if the user is signed in. Otherwise it
starts at the next RDP/WinApps logon. The task is named `WinApps-Windowed-<SID>`;
the binary is under `%ProgramData%\WinApps-Yttrium-Setup\windowed-helper`.
Diagnostics under `%LOCALAPPDATA%\WinApps\windowed-helper-<session>.log` record
only version/session and restore HWND/PID/request status, not titles, document
paths or credentials. A queued restore is not proof that the app accepted it.

Remove the task without closing apps or disconnecting Windows:

```sh
sudo ./setup.sh --config local-config.json remove-windowed-helper --windows-user USER
```

Or use `Install-WindowedHelper.ps1 -WindowsUser USER -Uninstall` in Windows.
Uninstall disables the task and stops its helper instances; the binary and
diagnostics remain for inspection. `winapps-windowed.exe --stop` can also stop
the helper in the caller's own interactive session.

For behavioral verification, run `guest/Test-WindowedHelper.ps1` in the same
interactive RDP session (not directly via SSH/QGA session 0). It opens disposable
WinForms windows and checks actual Windows maximization state for remembered
startup, delayed startup, and subsequent manual maximize; it also checks
deduplication and that fullscreen receives no helper restore request. Results
are written to `%LOCALAPPDATA%\WinApps\windowed-helper-verification.json`.
RemoteApp's Linux compositor can independently resize borderless test windows;
the fullscreen check does not claim exclusive fullscreen or game compatibility.
