# WinTide implementation fixes

## SDL3 RemoteApp integration

`patches/freerdp-sdl-resize.patch` applies to FreeRDP 3.32.2 commit
`97eff6ddfbbfaa8e42a126d362686bd001ff8bdc`. It extends upstream SDL3 RAIL work.
The separate [FreeRDP fork](https://github.com/xizha127/FreeRDP/tree/winapps-wayland-resize)
contains earlier resize work; the patch in this repository is authoritative for
the current WinTide build.

| Problem | Current implementation |
|---|---|
| Shrinking stalls after a resize | Permit compositor geometry to supersede an in-flight apply on shrink as well as growth. |
| Windows and local maximize state disagree | Keep ordinary Wayland RemoteApp HWNDs restored so `ClientWindowMove` works; let SDL/the compositor own local maximization. Ignore stale SDL maximized flags when deciding whether remote geometry is pinned. |
| Ordinary tiled windows send maximize notifications | Synchronize geometry rather than translate those notifications into Windows `SC_MAXIMIZE`. |
| Apps start floating despite being resizable | Remove the finite maximum-size hints derived from the remote work area. Those could be smaller than a local tile and cause the compositor to float it. No compositor-specific rule is installed. |
| Queued maximize/restore events bounce between systems | Coalesce state while hidden and identify acknowledgements of SDL state operations with a per-window timestamp barrier. |
| RemoteApp launch stalls on a login image | Submit the initial app once after the RAIL handshake rather than depend solely on a desktop ARC-completed notification. |
| Every app launch reconnects all existing windows | With `WINTIDE_SESSION_REUSE=1`, forward additional launches through a private same-user local socket to the existing RAIL connection. |
| One invalid app closes other apps | Retain an already-active connection when Windows rejects an additional EXEC request. |

For the window-state policy, maximize requests within three seconds of mapping
are treated as startup state. Later native maximize-button requests toggle the
local SDL surface. Popup/fullscreen surfaces retain their separate handling;
this is not a universal guarantee for every custom fullscreen application.

The launch broker reuses the first connection's redirections and compositor app
class. It does not merge full-desktop sessions. See [launcher behavior and limits](winapps.md)
and [live validation](validation.md).

## Explorer launcher

`guest/Explorer-Broker.ps1` opens a new This PC window per invocation. It serializes
new-window discovery, tracks the new HWND and keeps that invocation alive until
its window closes. It does not close, restore or repurpose existing Explorer
windows. The VBS launcher is generated from this script by `install-client`.

## Venus renderer under libvirt

`patches/renderer-libvirt-seccomp.patch` applies to the pinned
[arehnman virglrenderer fork](https://github.com/arehnman/virglrenderer).
The renderer starts a Venus child process; the installed QEMU wrapper permits
sandboxed process spawning, and the patch omits the child's terminal-oriented
`setpgid` call that triggered SIGSYS under the tested libvirt sandbox. Privilege
restrictions remain enabled.

The host integration also adds the configured GPU device nodes to libvirt's
allowlist and restarts the relevant libvirt daemon while the VM is shut off.
Missing device permissions previously caused black screens. These changes do
not unbind the host GPU or configure PCI passthrough.

## Optional shared-file permission policy

`patches/virtiofsd-preserve-host-permissions.patch` protects Linux ownership/modes
and permission-bearing xattrs from guest ACL translation while allowing ordinary
content writes. It is enabled only for a configured guarded VirtioFS share.
It does not implement Windows ACL persistence or solve Steam library behavior.
See [sharing](sharing.md) for the tested scope and activation requirements.
