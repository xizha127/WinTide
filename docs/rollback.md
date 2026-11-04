# Rollback

Close apps and shut Windows down cleanly. The installer never force-stops a running installation. Restore the original domain:

```sh
sudo ./setup.sh --config local-config.json rollback-host
```

This defines the saved `/var/lib/wintide/DOMAIN/domain.before.xml`, retaining the original disk, CPU, graphics, TPM and firmware configuration. Boot with that console and run `guest/Restore-Graphics.ps1` elevated inside Windows. It discovers the installed Yttrium OEM driver dynamically; no machine-specific oemNNN.inf number is embedded. Reboot after restoration. Native Windows files/certificates were changed by driver installation too; the host XML rollback alone is not sufficient to undo those changes.

The optional Windows startup helper is separate from graphics rollback. Remove
it with `remove-windowed-helper --windows-user USER` while the guest agent is
available; see [helper removal](windowed-helper.md). Host XML rollback does not
remove generated launchers or revert all RDP policy changes.

To remove host integration after recovery, stop the per-domain share service and remove only this installation's files:

- `/etc/libvirt/hooks/qemu.d/90-wintide-DOMAIN`
- `/etc/udev/rules.d/90-wintide-DOMAIN.rules`
- `/etc/systemd/system/wintide-DOMAIN-share.service`
- the `wintide-DOMAIN.conf` file under your mount unit's `.d/` directory
- `/etc/wintide/DOMAIN/` after restoring previously saved Linux mounts

The share service and mount-unit drop-in exist only if optional VirtioFS was configured.
While Windows is fully shut off, use `sudo ./setup.sh --config local-config.json restore-mounts`
before removing the installed runtime. Managed-save state blocks remounting.

Run `systemctl daemon-reload` and `udevadm control --reload`. Existing unrelated hooks/configuration are not replaced by installation. Leave the backups until native and virtual Windows boots have been checked.

The host `qemu.conf` backup is `qemu.conf.before` in the backup directory. Do **not** blindly restore it after other VMs or tools have changed it. Remove only the GPU ACL additions that are no longer needed, or restore the whole file only if no intervening changes exist. Restart the relevant libvirt daemon afterward. The setup script deliberately leaves this shared host setting in place during XML rollback.

Windows backups are under `C:\ProgramData\wintide`. RDP exports and the prior VirtioFS service configuration are retained there; restore them only after reviewing the differences. If a registry key did not exist originally, an export cannot represent that absence; do not assume importing a .reg file is a complete policy rollback. No automatic whole-BCD import is attempted.

Per-user client/profile files can be removed separately after backing up credentials. Never delete the physical Windows disk, shared game files or a private EFI image as part of a routine configuration rollback.
