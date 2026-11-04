# Linux launcher integration

`install-client` fetches no account data from the existing host setup. It takes the pinned upstream WinApps core already fetched by `build`, preserves its source copyright notices, and generates an isolated copy locally. It changes only profile/app-data/source paths and the debug helper's return status. That generated third-party core is not committed or redistributed in this repository.

The profile lives in `~/.config/wintide/`; app data lives in `~/.local/share/wintide/`; the command is `~/.local/bin/wintide`. Existing Docker configuration, auto-start policy, app data, and desktop files are left unchanged. If old and new launchers coexist, disable the old entries manually after making a backup. Stopping a Docker VM is not part of this installer.

After installing the client profile:

```sh
sudo ./setup.sh --config local-config.json discover
./setup.sh --config local-config.json launchers
```

Discovery queries HKLM/loaded-user App Paths registrations plus Notepad, checks that executables exist, and returns JSON through QGA. It never evaluates Windows-produced Bash. Generated metadata uses shell quoting, and desktop entry IDs use normalized names plus a path hash. UWP apps, unregistered portable apps and programs only registered for an unloaded user hive may need manual configuration. Entries are named `(Windows VM)` to distinguish them from existing launchers.

For a manual app:

```sh
wintide manual 'C:\Windows\System32\notepad.exe'
```

Fresh installations include Explorer and Settings broker entries; other registered
executables are discovered by `wintide apps refresh`. Portable applications can be
added with `wintide apps add`; see [command reference](command.md).

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
still reject a program, which the SDL client reports through its own logging. The generated WinApps core normally redirects client output to `/dev/null`, so WinApps `DEBUG` alone does not capture that RAIL error. A rejected
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

Window-state handling runs in the SDL client; no separate Windows startup helper
is required. The former helper has been retired.

## Diagnose a launch without resetting the setup

- All participating launchers must use the patched binary and export
  `WINTIDE_SESSION_REUSE=1`. An old wrapper or a client started before the upgrade
  can still create a separate connection.
- Use the same server address, port, Windows username and domain for shared
  launches. Different address spellings are separate connection keys.
- `DEBUG=true` in the profile logs WinApps wrapper activity to its app-data
  directory. Detailed RAIL errors require capturing the SDL client's output
  separately; logs can contain paths and account information, so keep them local.
- Start the VM with the guarded setup command before launching apps. A local
  console or full-desktop RDP login can still switch the Windows session.
- Discovery is not universal: Settings has a built-in broker, but other UWP apps
  and unregistered portable programs can need manual definitions.
