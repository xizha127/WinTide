# An existing physical Windows installation

The automated installer deliberately starts after the VM boots successfully. Physical Windows boot repair depends on its partition GUIDs, storage driver, BitLocker state and where the machine's Windows boot files actually live. A blind universal BCD script would be unsafe.

1. Identify the Windows disk using `lsblk -f`, `ls -l /dev/disk/by-id/`, and your firmware boot entries. Keep a verified backup and any BitLocker recovery material outside this repository. Disable Windows hibernation/Fast Startup before using its disk from Linux. Suspend/decrypt BitLocker as appropriate before virtual hardware changes; do not assume it will unlock against a new virtual TPM.
2. Identify **the EFI partition containing `EFI/Microsoft/Boot/BCD`**. It may be on the disk hosting Linux even if Windows itself is on another disk. Merely attaching the Windows OS disk can therefore produce BCD/recovery errors. Never pass the whole running Linux disk to the VM.
3. Make a private EFI filesystem image from the Windows EFI files. `tools/copy-efi.py` creates a new FAT image, copies only Microsoft boot files, and supplies the fallback boot path. It reads the chosen mounted source and does not rewrite it. Keep this generated image outside Git, e.g. `/var/lib/libvirt/images/windows-private-efi.img`.
4. In virt-manager create an imported Windows 11 x86-64 Q35 VM, initially with QXL/SPICE or another known-working console. Use non-Secure-Boot OVMF and a persistent virtual TPM. Attach the Windows physical disk as a raw block device through its stable by-id path, and the private EFI image as a separate SATA disk. Attach a Windows recovery ISO only when boot repair is necessary. Use a guest CPU model that boots this Windows installation; do not copy this project's reference CPU affinity onto other hardware.
5. Unmount **all partitions on the physical Windows disk** before starting the VM. Never leave an ext4 data partition on that same raw disk mounted either. Do not boot native Windows while the VM runs. The installer later installs a libvirt pre-start guard and an automount inhibitor; this initial bootstrap needs the same discipline.
6. If BCD still points to an unavailable volume, use Windows recovery's command prompt. Identify volumes using `diskpart`/`list volume` and assign `W:` to the actual Windows volume and `S:` to the **private EFI image**. Confirm `W:\Windows` exists and `S:` is the new private image. Only then run:

   ```bat
   bcdboot W:\Windows /s S: /f UEFI
   ```

   This targets the private VM EFI files. Do not select the native EFI partition. Windows recovery drive letters are not stable. Never paste a disk/partition number from somebody else's guide.

7. Confirm boot and sign-in, then install official VirtIO-Win QEMU Guest Agent and check `guest-ping` from Linux. Configure network access, then follow the README installer path.

Reference observation: host-passthrough CPU repeatedly failed to boot this installation while a custom `Skylake-Client-IBRS` CPU worked. This is a machine-specific result, not a universal recommendation. The installer preserves the existing working CPU definition. P-core affinity improved latency on the tested hybrid CPU; inspect your own topology with `lscpu -e` before pinning.

Sources: [libvirt disk XML](https://libvirt.org/formatdomain.html#hard-drives-floppy-disks-cdroms), [Microsoft BCDBoot](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/bcdboot-command-line-options-techref-di), [Microsoft hibernation](https://learn.microsoft.com/en-us/troubleshoot/windows-client/setup-upgrade-and-drivers/disable-and-re-enable-hibernation).
