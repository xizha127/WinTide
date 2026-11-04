# Small local fixes

## SDL3 RemoteApp resizing

Upstream: [FreeRDP](https://github.com/FreeRDP/FreeRDP). Separate fork: [xizha127/FreeRDP](https://github.com/xizha127/FreeRDP/tree/winapps-wayland-resize).

`patches/freerdp-sdl-resize.patch` applies against release3.32.2 commit `97eff6ddfbbfaa8e42a126d362686bd001ff8bdc` and contains:

1. Permit Wayland compositor sizes to supersede an in-flight geometry apply on shrink as well as growth. The growth-only condition could suppress subsequent shrinking indefinitely.
2. Treat the RAIL maximize state as authoritative. A stale SDL Wayland maximized flag after server restore could block geometry synchronization even when Windows reported the window restored.

3. Start the requested app after the RAIL handshake, with a per-connection guard against duplicate execution. The observed Windows session did not send the desktop ARC-completed notification used by the previous startup path, leaving the client on the login image without executing the app. Both handshake variants now launch once, following the Windows client startup approach.

4. Separate Wayland compositor maximization from Windows `WS_MAXIMIZE`. Ordinary tiled surfaces can receive SDL maximized events; these synchronize geometry instead of sending `SC_MAXIMIZE`. Server maximize requests are restored remotely so `ClientWindowMove` continues working. A later native maximize-button request toggles the local SDL surface; requests within three seconds of mapping are treated as startup state. Popup/fullscreen surfaces retain their separate path.
5. Leave the maximum size of resizable Wayland application surfaces unconstrained. Windows max-track sizes and a locally imposed usable-area cap advertised a maximum smaller than the compositor's tile. Hyprland's layout consequently floated those windows. This is an SDL size-hint correction, with no compositor rules.
6. Coalesce state while hidden and distinguish queued SDL acknowledgements from new local state changes using a per-window timestamp barrier.

Interactive validation: earlier floating sizes of client1200x800, 900x600 and1100x750 matched the Windows client plus frame margins. With the current patch, Settings and Explorer both opened tiled without floating rules. Settings's local844x1380 allocation matched its restored native858x1387 rectangle. Native maximize followed by restore returned to a responsive tile; the user confirmed both tiling and maximization were fixed. Checks used the actual patched process, then installed that identical executable. Other compositors, applications, DPI configurations and extended stability remain unverified.

## Venus render-server child under libvirt

Upstream: [arehnman's renderer](https://github.com/arehnman/virglrenderer), pinned in components.lock.json.

The renderer forks/execs its Venus server. Libvirt's QEMU sandbox initially blocked spawning; after allowing spawn for this VM, kernel audit recorded SIGSYS on syscall109 (`setpgid`) in the render child. The renderer called it only to avoid terminal signals. A libvirt-launched VM has no controlling terminal and its descendants are managed in its cgroup, so our patch omits that call. This permits retaining `elevateprivileges=deny` rather than disabling the whole sandbox.

The other black-screen cause was an absent GPU device allowlist: NVIDIA control/render opens returned EPERM inside the QEMU cgroup. Adding exact nodes and **restarting**, not merely reloading, virtqemud corrected it. Successful Windows sign-in plus GPU clear/readback followed. Neither change requires GPU passthrough.
