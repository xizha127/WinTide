# Performance

Treat Windows responsiveness, storage, GPU rendering and RDP transport as separate
measurements. A fast sequential copy or a passing D3D11 smoke test does not measure
Steam validation, game frame rates or input latency.

## Windows responsiveness

The reference installation became noticeably more responsive after reducing
unnecessary startup work and placing VM threads on suitable performance cores.
Those changes were machine-specific; the installer preserves the existing CPU
model, topology and affinity. Inspect your own topology with `lscpu -e` before
experimenting with libvirt CPU pinning, and leave resources for Linux.

`guest/Optimize-Startup.ps1` is optional and defaults to Preview. It lists registry
Run entries, Startup files and non-Microsoft logon/boot tasks; Apply backs them up
and disables selected entries. Its exclusions are name/path patterns, not a
complete inventory of essential software. Review custom tasks before applying
it. It does not change services or stop
running processes. This tool is not part of the normal installer.

## Storage

The current reference game drive is NTFS owned directly by Windows. Steam storage
operations improved after moving away from the earlier VirtioFS setup. VirtioFS
read/write and permission protection were verified, but Steam validation, space
reservation and size reporting remained problematic. See [storage choices](sharing.md).
There is no established universal speedup percentage or game-loading benchmark.

## Graphics and display transport

The pinned Yttrium stack passed hardware D3D11 creation and GPU clear/readback.
RemoteApp rendering uses the patched SDL3 client with `/gdi:sw`; that client-side
choice does not establish which GPU an individual Windows app uses.

The current client fixes window geometry and connection reuse. They are not
codec/streaming optimizations. RDP game latency, DirectX 12 and application-specific
performance remain unverified. Use a representative workload after the base
setup works, rather than changing CPU, graphics and storage together.
