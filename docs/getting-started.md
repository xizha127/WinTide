# Set up WinTide

WinTide brings Windows RemoteApps into your Linux desktop using a guarded libvirt VM and a patched SDL FreeRDP client.

## Prerequisites and installation

The automated path starts with an **existing, bootable x86-64 Windows 11 Pro/Enterprise physical-disk VM in system libvirt**, with QEMU Guest Agent running. The config loader currently requires a nonempty `physical_disks` list of existing block devices; an image-only VM is not an automated install path. Building that initial VM and correcting a machine-specific EFI/BCD layout is covered in [physical disk and boot preparation](physical-disk.md); the installer never guesses at boot-record repair, formats a disk, or attaches the disk containing your running Linux installation.

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

4. Shut Windows down cleanly and unmount all partitions on every raw disk attached to the VM. `apply-host` checks that they are already unmounted; automatic unmounting is part of the later installed `start` command. Generate and inspect the plan before applying:

   ```sh
   ./setup.sh --config local-config.json plan
   # Review local-plan/domain.wintide.xml and local-plan/config.json.
   sudo ./setup.sh --config local-config.json apply-host
   sudo ./setup.sh --config local-config.json start
   ```

   Existing CPU, storage, network and firmware are retained. A running VM is never force-stopped. Existing custom QEMU command-line arguments or passthrough devices require manual review; the installer refuses to silently replace them. The operation installs namespaced files and records rollback copies.

5. Confirm Windows boots and the guest agent responds, then install the isolated Linux client profile:

   ```sh
   ./setup.sh --config local-config.json install-client --windows-user YOUR_LOCAL_WINDOWS_USER
   wintide manual 'C:\Windows\System32\notepad.exe'
   sudo ./setup.sh --config local-config.json discover
   ./setup.sh --config local-config.json launchers
   ```

   The password is entered interactively and stored locally with mode `0600`, read through FreeRDP askpass, never put on its command line. Existing Docker WinApps profiles/launchers are not modified. Launcher discovery uses Windows executable registrations and only generates entries for existing files; see [desktop integration](winapps.md).

## Installation paths

| Purpose | Path / name |
|---|---|
| Built components / build cache | `~/.local/opt/wintide` / `~/.cache/wintide` (configurable) |
| Launcher | `~/.local/bin/wintide` |
| Profile / app data | `~/.config/wintide/` / `~/.local/share/wintide/` |
| Installed host runtime | `/etc/wintide/DOMAIN/` |
| Host rollback backups | `/var/lib/wintide/DOMAIN/` |
| Transient mount state | `/run/wintide/DOMAIN/` |
| Optional share service | `wintide-DOMAIN-share.service` |
| Windows setup / rollback state | `C:\ProgramData\wintide` |
| Windows startup backups | `C:\ProgramData\wintide\startup-TIMESTAMP` |

Upstream-owned paths, such as the Windows VirtIO drivers, WinFsp, OpenSSH and
libvirt hooks directory, retain the names their tools require. Source checkout
keys and upstream repository URLs retain the actual project names.
Legacy names occur only in detection checks that protect existing installations;
they are never used as destinations for a new installation.

An older installed deployment is not migrated by changing this checkout. The
installer refuses detected legacy setup state rather than creating a competing
profile or taking new rollback snapshots of an already-modified installation.
Keep that deployment's original checkout and backups for rollback. Migrate host
hooks, services, guest tasks, credentials and backup state together during a
planned shutdown; do not simply rename a directory while Windows or its services are
running. An automatic migration command is not provided.

## Daily use

Run these from the checkout with your existing local configuration:

```sh
sudo ./setup.sh --config local-config.json start
wintide manual 'C:\Windows\System32\notepad.exe'
# Optional, only when a VirtioFS directory is configured and mounted:
sudo ./setup.sh --config local-config.json share
# After saving and closing Windows work:
sudo ./setup.sh --config local-config.json stop
```

`start` prepares guarded raw disks and starts the VM if it is shut off. `stop`
requests a clean shutdown and then restores eligible saved host mounts; it does
not force-stop Windows. Desktop mounts without an fstab entry stay unmounted.
A managed-save state blocks remounting until Windows has resumed and shut down.
See [storage ownership](sharing.md) and [rollback](rollback.md).

The generated launcher assumes the VM is available; it does not replace the
root-owned physical-disk preparation command. Start through the guarded command
before using desktop app entries.

## Existing installations

This is not an unattended upgrade script. `apply-host` refuses to overwrite an
installed host integration, and `install-client` preserves an existing profile by
refusing to replace it. Keep your local config, credentials and rollback state.
A source tree patched with an older patch may also require a separate build
checkout; the builder rejects unreviewed source changes.

The current client needs the current FreeRDP patch, `WINTIDE_SESSION_REUSE=1` in
the launcher environment, and the current Explorer broker for new windows per
click. Reconnect an old running client once after installing an updated binary;
subsequent app launches then reuse that connection. See [launcher integration](winapps.md).
