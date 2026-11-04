# Optional file sharing and game storage

## Choose the storage model first

| Model | Ownership | Observed result / setup scope |
|---|---|---|
| VirtioFS shared directory | Linux mounts the filesystem; Windows uses file operations | Read/write and the permission guard are verified. Included as an optional installer path. Steam validation, allocation and library reporting remained problematic. |
| Direct Windows game disk | Windows alone mounts NTFS while the VM runs | The reference system's Steam storage operations became fast after switching. Manual libvirt provisioning; not automated here. |
| Windows-to-Linux network share | Windows owns the disk; Linux accesses exported files | Reverse SMB read/write/rename was tested separately. Not provisioned by this installer; caching can delay visibility. |

For a Windows-owned disk, Linux must not also mount its raw filesystem. Access it from Linux through a file-sharing service, or shut down Windows and detach the disk before mounting it locally. The permission policy below applies only to VirtioFS; it is not an NTFS mount policy.

## Configure optional VirtioFS

This is an optional file-sharing path, not the current reference game-drive setup.

Install official [VirtIO-Win VioFS](https://github.com/virtio-win/kvm-guest-drivers-windows) and [WinFsp](https://winfsp.dev/). The reference machine already had both, so the installer configures those existing components and stages their installed driver. It does not silently run an entire guest-tools bundle that might replace the graphics driver.

Set `shared_directory` to the actual mounted root, `shared_uuid` to its `findmnt -M /path -o UUID` value, and optionally change `share_letter` and `share_tag` in local configuration. Prepare Windows with `guest --guest-mode share` before applying the host setup. A mountpoint UUID check prevents exposing an empty host directory when the external disk is absent.

The host runtime attaches VirtioFS live when the VM starts or the configured systemd mount appears. The directory is not a mandatory device in the persistent domain XML, so unplugged optional storage does not prevent Windows from booting. Windows service startup is demand-driven through QGA. Cache mode is the daemon's default `auto`; `always` is deliberately not forced because the host also accesses these files. Recent Rust virtiofsd has different command-line locking options from older C implementations; this recipe leaves those options at daemon defaults.

For the tested ext4 share, Linux alone mounts the filesystem. Windows receives file operations through VirtioFS/WinFsp. This avoids two independent operating systems writing raw ext4 metadata, but does not prevent two applications overwriting the same file. Allow only one Steam installation/mod manager to install, verify or update a given game/library at a time. Do not run native and Proton builds against the same installation unless the game supports it.

**Do not unplug the drive while either side is using it.** For a predictable disconnect, close Windows/Linux applications and shut down the VM before unmounting/ejecting the drive. Removing/reconnecting a disk beneath a running virtiofsd mount namespace is not a supported recovery workflow here; restart the VM/share after a clean disconnect. Read/write was verified, but game loading/streaming and launcher compatibility require per-game testing.

Official references: [libvirt VirtioFS](https://libvirt.org/kbase/virtiofs.html), [Windows installation](https://virtio-fs.gitlab.io/howto-windows.html).

## Preserve Linux permissions (default for new shared-drive installations)

Windows ACL translation in VirtioFS can reduce real POSIX permissions to mode `000`. The reproduced failure used `SetFileSecurity` with an empty DACL on a disposable file; it became unreadable. The stock backend does not offer a chmod-ignore option.

`share_permission_guard` defaults to true when a share is configured. The build script compiles pinned virtiofsd 1.14.0 with `patches/virtiofsd-preserve-host-permissions.patch`. The opt-in `--preserve-host-permissions` backend policy ignores guest MODE/UID/GID updates, blocks writes/removals of permission-bearing ACL/capability xattrs, and gives newly created files/directories minimum owner access (rw/rwx). Existing host modes and ownership stay unchanged; size/timestamp changes and ordinary content writes continue normally. A root-owned per-domain wrapper enables the policy only for this share. No extra FUSE layer is added.

The live regression test repeated the same Windows empty-DACL operation: it reported success, but the underlying file stayed at mode `0640` and remained readable. Windows write/append/rename/delete tests passed. The patched backend's 46 library tests passed, including a real-filesystem test combining mode `000` and ownership changes with a successful truncate. This deliberately does not provide persistent Windows ACL semantics: Windows ACL edits can appear successful without taking effect. It is an accidental-permission-change safeguard, not isolation against a guest already authorized to write/delete/replace the shared contents. Existing damaged permissions require separate, selective repair; the installer does not chmod the whole library.

Activating/changing the backend requires stopping applications using the drive, stopping the Windows VirtioFS service, and detaching/reattaching the filesystem. This interrupts Steam verification or downloads. Do not replace a live daemon underneath an active library operation.

## Steam limitation

Earlier sequential copies reached roughly 300–600 MB/s on the reference shared
storage, but Steam validation and space reservation could still be slow and a
library could appear as 0 B. The permission guard did not establish a fix for
those behaviors. They involve more than sequential throughput; no single cause
or cluster-size mismatch was proven.

The reference setup subsequently moved the game disk to direct Windows ownership.
Keep the optional VirtioFS path for use cases whose behavior you have tested;
do not describe it as a validated Steam-library solution. The installer does
not configure the direct-disk or reverse-SMB alternatives in the table above.
