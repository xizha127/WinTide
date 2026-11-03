# Optional shared game drive

Install official [VirtIO-Win VioFS](https://github.com/virtio-win/kvm-guest-drivers-windows) and [WinFsp](https://winfsp.dev/). The reference machine already had both, so the installer configures those existing components and stages their installed driver. It does not silently run an entire guest-tools bundle that might replace the graphics driver.

Set `shared_directory` to the actual mounted root, `shared_uuid` to its `findmnt -M /path -o UUID` value, and optionally change `share_letter` and `share_tag` in local configuration. Prepare Windows with `guest --guest-mode share` before applying the host setup. A mountpoint UUID check prevents exposing an empty host directory when the external disk is absent.

The host runtime attaches VirtioFS live when the VM starts or the configured systemd mount appears. The directory is not a mandatory device in the persistent domain XML, so unplugged optional storage does not prevent Windows from booting. Windows service startup is demand-driven through QGA. Cache mode is the daemon's default `auto`; `always` is deliberately not forced because the host also accesses these files. Recent Rust virtiofsd has different command-line locking options from older C implementations; this recipe leaves those options at daemon defaults.

Linux alone mounts ext4. Windows receives file operations through VirtioFS/WinFsp. This avoids two independent operating systems writing raw ext4 metadata, but does not prevent two applications overwriting the same file. Allow only one Steam installation/mod manager to install, verify or update a given game/library at a time. Do not run native and Proton builds against the same installation unless the game supports it.

**Do not unplug the drive while either side is using it.** For a predictable disconnect, close Windows/Linux applications and shut down the VM before unmounting/ejecting the drive. Removing/reconnecting a disk beneath a running virtiofsd mount namespace is not a supported recovery workflow here; restart the VM/share after a clean disconnect. Read/write was verified, but game loading/streaming and launcher compatibility require per-game testing.

Official references: [libvirt VirtioFS](https://libvirt.org/kbase/virtiofs.html), [Windows installation](https://virtio-fs.gitlab.io/howto-windows.html).
