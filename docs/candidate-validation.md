# Candidate validation, 2026-11-03

The metadata and CPU-hidden profiles were built and boot-tested on an existing physical-disk Windows 11 installation using shared NVIDIA graphics through Yttrium. The original QEMU, firmware and NVRAM were retained. A metadata-profile rollback was exercised before activating the CPU-hidden profile.

| Check | Baseline | Metadata | CPU-hidden |
|---|---|---|---|
| Windows HypervisorPresent | true | true | false |
| Hardware D3D11 device, texture clear/readback | pass | pass | pass |
| CPU hash smoke, median milliseconds | 271.0 | 283.1 | 272.5 |
| Direct Windows disk write-through, MiB/s | 586 | 605 | 635 |

These are short regression checks, not game benchmarks or statistically established speed improvements. Buffered-read results were excluded because they can measure Windows cache. The graphics adapter and driver stayed unchanged. No new Device Manager errors appeared; a pre-existing Hyper-V bus-provider error remained.

The absolute tablet stayed selected. A physical-profile WinApps launch succeeded; the user reported resizing generally working and deferred app-specific quirks. Reverse Windows-to-Linux SMB read/write/rename passed after the configured one-second cache interval. Immediate Linux reads could briefly see stale data; the native Windows game drive is independent of that cache.

Windows OpenSSH Server installation completed successfully. Key-authenticated commands were tested with a host key obtained through QGA and a firewall rule restricted to the virtualization host. An interactive PowerShell profile caused startup delays, so scripted SSH uses cmd as its transport and invokes PowerShell explicitly with `-NoProfile`.

The old failed preview update was no longer offered when retried. Its installation is **not** verified. Application Guard removal completed and subsequent OpenSSH capability servicing succeeded. The helper records update status and never reboots automatically.

Verification included 26 unit tests, Python/shell syntax checks, guest PowerShell parsing, a diskless firmware boot, matching 4 MiB firmware layout, and staged-patch applicability against pinned source blobs. The publication scanner checked the intended Git index. A fresh-host full installation has not been exercised end-to-end.

The CPU-hidden profile still exposes synthetic Hyper-V CPUID leaves, detected by the selected VMAware harness. VirtIO devices, guest integration and required test signing also remain. This is **not** an undetectable VM, and no anti-cheat acceptance is claimed. No host-kernel timing patches or GPU passthrough were used.
