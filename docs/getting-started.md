# Set up WinTide

WinTide brings Windows RemoteApps into your Linux desktop using a guarded libvirt VM and a patched SDL FreeRDP client.

## Prerequisites and installation

The automated path starts with an **existing, bootable x86-64 Windows 11 Pro/Enterprise VM in system libvirt**, with QEMU Guest Agent running. It can use your physical Windows disk. Building that initial VM and correcting a machine-specific EFI/BCD layout is covered in [physical disk and boot preparation](physical-disk.md); the installer never guesses at boot-record repair, formats a disk, or attaches the disk containing your running Linux installation.

Use an unprivileged desktop account for the build. Root is needed only for system libvirt setup and guest-agent operations.

1. Install the [host prerequisites](requirements.md). Confirm the base VM boots and that `virsh -c qemu:///system qemu-agent-command YOUR_VM '{"execute":"guest-ping"}'` responds.
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

   Read [security and signing](security.md) first. The Yttrium release is test-signed; this changes the Windows installation. A Microsoft account PIN is not an RDP password.

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

   The password is entered interactively and stored locally with mode `0600`, read through FreeRDP askpass, never put on its command line. Existing Docker WinApps profiles/launchers are not modified. Launcher discovery uses Windows executable registrations and only generates entries for existing files; see [desktop integration](winapps.md).


## Installation paths and compatibility names

New installations use `~/.local/opt/wintide` for built components and `~/.cache/wintide` for source/build files, as shown in the example config. These paths remain configurable; existing local configs keep their explicitly selected paths.

The project was previously named `winapps-yttrium-libvirt`. Existing commands, profile directories, services and guest backup paths retain the `winapps-yttrium` name so upgrades do not abandon credentials, backups or installed launchers. The repository rename does not require reinstalling or changing your VM.
