# Performance observations

The physical Windows installation initially felt much slower than the previous Docker VM. Inspection found a third-party desktop bar consuming a full CPU core, many native-Windows startup applications, and an unhelpful CPU placement on the hybrid host. Stopping the busy application, disabling unnecessary startup entries with backups, and pinning VM work to the host's performance-core threads made the reference VM feel snappy. No measured storage-latency bottleneck was found; there was no hidden universal Docker optimization preset to copy.

The installer preserves CPU topology, model and affinity. On a hybrid CPU, inspect `lscpu -e` and test `virsh vcpupin`, `emulatorpin` and `iothreadpin` before persisting values. Do not assume CPUs0-15 are performance cores on another machine. Keep adequate cores/RAM for Linux. Preserve a CPU model that actually boots the existing Windows installation.

`guest/Optimize-Startup.ps1` is an optional preview/apply/restore tool. It preserves QEMU/SPICE/VirtIO/security entries and Microsoft scheduled tasks, backs up registry Run entries, Startup files and third-party logon/boot tasks, and never changes services, Defender or Windows Update. Run Preview first under an elevated Windows session, specify the correct local user, and review application-specific consequences. It is not part of the default installer.

GPU rendering, disk loading and remote display transport are separate bottlenecks. A successful Yttrium D3D11 test does not benchmark a game or prove RDP latency is suitable for it. Benchmark with a known workload after the base setup works; avoid simultaneous Steam updates on a shared library.
