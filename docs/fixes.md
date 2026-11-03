# Small local fixes

## SDL3 RemoteApp resizing

Upstream: [FreeRDP](https://github.com/FreeRDP/FreeRDP). Separate fork: [xizha127/FreeRDP](https://github.com/xizha127/FreeRDP/tree/winapps-wayland-resize).

`patches/freerdp-sdl-resize.patch` applies against release3.32.2 commit `97eff6ddfbbfaa8e42a126d362686bd001ff8bdc` and contains only:

1. Permit Wayland compositor sizes to supersede an in-flight geometry apply on shrink as well as growth. The growth-only condition could suppress subsequent shrinking indefinitely.
2. Treat the RAIL maximize state as authoritative. A stale SDL Wayland maximized flag after server restore could block geometry synchronization even when Windows reported the window restored.

Interactive validation: client1200x800 corresponded to Windows1216x808; client900x600 to Windows916x608; client1100x750 to Windows1116x758. Frame margins explain the differences. The user confirmed both shrinking and normal resize behavior. An attempted general “always start windowed” change regressed behavior and is **not included**.

## Venus render-server child under libvirt

Upstream: [arehnman's renderer](https://github.com/arehnman/virglrenderer), pinned in components.lock.json.

The renderer forks/execs its Venus server. Libvirt's QEMU sandbox initially blocked spawning; after allowing spawn for this VM, kernel audit recorded SIGSYS on syscall109 (`setpgid`) in the render child. The renderer called it only to avoid terminal signals. A libvirt-launched VM has no controlling terminal and its descendants are managed in its cgroup, so our patch omits that call. This permits retaining `elevateprivileges=deny` rather than disabling the whole sandbox.

The other black-screen cause was an absent GPU device allowlist: NVIDIA control/render opens returned EPERM inside the QEMU cgroup. Adding exact nodes and **restarting**, not merely reloading, virtqemud corrected it. Successful Windows sign-in plus GPU clear/readback followed. Neither change requires GPU passthrough.
