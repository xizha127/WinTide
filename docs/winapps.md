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

For standalone Explorer, `guest/Explorer-Broker.ps1` documents the working broker approach: start/reuse a folder window, restore it, and keep the RemoteApp process alive until the folder windows close. Avoid starting competing Explorer connections on repeated clicks. The integration installer creates its broker launcher separately; no arbitrary Windows desktop windows are closed.

The patched client is the SDL3 `sdl-freerdp` built from FreeRDP3.32.2, not a differently named system binary. RemoteApps use `/gdi:sw -decorations +dynamic-resolution`; do not silently switch to `/gdi:hw` or `/multimon`, which regressed the reference setup. FFmpeg/swscale are disabled in this build to avoid the observed distro ABI conflict; this is not an optimal multimedia-codec preset for all hosts.

A full RDP desktop/RemoteApp session can disconnect the local VM console session. Avoid RDP validation while someone is using the Windows console. Game streaming and RDP are separate latency/compatibility questions; shared GPU acceleration does not guarantee low-latency delivery through RDP.
