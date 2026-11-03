# WinApps + Yttrium + libvirt

Run an existing Windows installation under Linux, expose Windows apps in the Linux launcher, share the host GPU through Yttrium, and optionally share a Linux game drive through VirtioFS.

This repository assembles other people's substantial work. **Yttrium by [arehnman](https://github.com/arehnman) provides the shared GPU stack; [WinApps](https://github.com/winapps-org/winapps) and [FreeRDP](https://github.com/FreeRDP/FreeRDP) provide the application integration.** See [all credits and licenses](THIRD_PARTY.md).

It includes the known-working source pins, two SDL/Wayland resize fixes, a small libvirt renderer compatibility patch, a shared-drive permission safeguard, a setup script, physical-disk mount protection, guest configuration, optional drive sharing, and a Direct3D hardware smoke test. Upstream sources and Windows binaries are fetched from their projects, not republished here.

## What has actually worked

Tested on an Intel hybrid-core laptop, an RTX 4070 Laptop GPU with NVIDIA's proprietary Linux driver, CachyOS/Hyprland, and an existing Windows 11 Pro installation on a separate physical NVMe disk:

- Raw-disk Windows boot under libvirt, while preserving native boot as an option.
- Windows apps launched through WinApps and the patched SDL3 FreeRDP client.
- Floating-window growth/shrink and maximized-state resize fixes, confirmed interactively.
- Linux continuing to use the GPU while Windows renders through Yttrium/Venus.
- Hardware D3D11 device creation **and an actual GPU clear/readback**, not just adapter enumeration.
- An ext4 USB game drive accessible from Windows as `H:` and Linux simultaneously; read/write verified.

Actual games, DirectX 12, sustained performance, all hardware combinations, and a clean-machine end-to-end installation have **not** been validated. The installer is a reproducible implementation of the working steps, not a claim of universal compatibility. See [validation](docs/validation.md).

## How the pieces connect

```text
Linux launcher -> WinApps -> patched SDL3 FreeRDP -> Windows RemoteApps
Linux libvirt -> Yttrium QEMU -> physical Windows disk (unmounted on Linux)
Windows Yttrium driver -> Venus -> patched virglrenderer -> Linux GPU driver
Windows H: -> VirtioFS/WinFsp -> Linux-mounted ext4 game directory
```

The physical Windows boot disk and the shared game drive use different access models. The former is exclusively owned by Windows while the VM runs. The latter is shared at the file level through Linux's filesystem.

## Replicate on an existing installation

The automated path starts with an **existing, bootable x86-64 Windows 11 Pro/Enterprise VM in system libvirt**, with QEMU Guest Agent running. It can use your physical Windows disk. Building that initial VM and correcting a machine-specific EFI/BCD layout is covered in [physical disk and boot preparation](docs/physical-disk.md); the installer never guesses at boot-record repair, formats a disk, or attaches the disk containing your running Linux installation.

Use an unprivileged desktop account for the build. Root is needed only for system libvirt setup and guest-agent operations.

1. Install the [host prerequisites](docs/requirements.md). Confirm the base VM boots and that `virsh -c qemu:///system qemu-agent-command YOUR_VM '{"execute":"guest-ping"}'` responds.
2. Create a local configuration:

   ```sh
   cp examples/config.example.json local-config.json
   chmod 600 local-config.json
   # Edit domain, desktop_user, physical_disks and display values.
   # Optional: set shared_directory and shared_uuid for a Linux-mounted drive.
   ./setup.sh --config local-config.json doctor
   ./setup.sh --config local-config.json build
   ```

3. While Windows is running with its original console graphics, prepare RemoteApps and the verified driver:

   ```sh
   sudo ./setup.sh --config local-config.json guest --guest-mode rdp --windows-user YOUR_LOCAL_WINDOWS_USER
   sudo ./setup.sh --config local-config.json guest --guest-mode yttrium --enable-test-signing --disable-hibernation
   # If sharing a drive, first install VirtIO-Win VioFS + WinFsp; then:
   sudo ./setup.sh --config local-config.json guest --guest-mode share
   ```

   Read [security and signing](docs/security.md) first. The Yttrium release is test-signed; this changes the Windows installation. A Microsoft account PIN is not an RDP password.

4. Shut Windows down cleanly. Generate and inspect the plan before applying:

   ```sh
   ./setup.sh --config local-config.json plan
   # Review local-plan/domain.yttrium.xml and local-plan/config.json.
   sudo ./setup.sh --config local-config.json apply-host
   sudo ./setup.sh --config local-config.json start
   ```

   Existing CPU, storage, network and firmware are retained. A running VM is never force-stopped. Existing custom QEMU command-line arguments or passthrough devices require manual review; the installer refuses to silently replace them. The operation installs namespaced files and records rollback copies.

5. Sign in, then install the isolated Linux client profile:

   ```sh
   ./setup.sh --config local-config.json install-client --windows-user YOUR_LOCAL_WINDOWS_USER
   winapps-yttrium manual 'C:\Windows\System32\notepad.exe'
   sudo ./setup.sh --config local-config.json discover
   ./setup.sh --config local-config.json launchers
   ```

   The password is entered interactively and stored locally with mode `0600`, read through FreeRDP askpass, never put on its command line. Existing Docker WinApps profiles/launchers are not modified. Launcher discovery uses Windows executable registrations and only generates entries for existing files; see [desktop integration](docs/winapps.md).

## Daily use

```sh
sudo ./setup.sh --config local-config.json start
sudo ./setup.sh --config local-config.json share   # attach configured drive if mounted
sudo ./setup.sh --config local-config.json stop    # graceful shutdown, then restore previous Linux mounts
```

Optional sharing attaches on VM startup or the configured mount appearing. An absent game drive does not prevent VM startup. Stop applications before disconnecting USB storage; do not have two Steam installations update the same game/library metadata at once. More in [sharing](docs/sharing.md).

## Recovery and contributing

See [rollback](docs/rollback.md), [known fixes](docs/fixes.md), and [privacy](docs/privacy.md). Do not attach configs, BCD exports, VM XML, logs, recovery keys or disk images to issues without sanitizing them.

The FreeRDP fixes are also maintained separately in [xizha127/FreeRDP, `winapps-wayland-resize`](https://github.com/xizha127/FreeRDP/tree/winapps-wayland-resize). This is an integration project, not an official release or endorsement from any upstream project.
