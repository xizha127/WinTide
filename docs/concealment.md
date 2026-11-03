# Optional metadata candidate

This source-built candidate adapts [AICodo's work](https://github.com/AICodo/pve-emu-realpc) while preserving Yttrium graphics and existing disk/device drivers. Pins are in `components.lock.json`. It reduces selected virtual hardware labels; it does not guarantee game/anti-cheat compatibility. Test signing remains required for the experimental Yttrium driver.

QEMU changes cosmetic input/display/storage defaults and ACPI OEM labels. It omits OS-visible fw_cfg discovery while retaining firmware access and protocol signatures. It preserves VirtIO/USB IDs and explicit disk identities, adds no fabricated sensor/cache tables, and does not modify the host kernel. Firmware changes module labels and vendor text, preserving GUIDs, interfaces and security behavior. Modules with generated name-dependent string symbols retain their names.

## Build and stage

Install the existing Yttrium build prerequisites plus NASM, ACPICA and normal EDK II BaseTools prerequisites. As your desktop user, choose a NEW installation prefix:

```sh
./setup.sh concealment build --work "$HOME/Projects/yttrium-candidate" \
  --prefix "$HOME/.local/opt/yttrium-candidate" \
  --renderer-prefix "$HOME/.local/opt/yttrium-host" --jobs 6
./setup.sh concealment stage --domain WINDOWS_VM \
  --prefix "$HOME/.local/opt/yttrium-candidate" \
  --out "$HOME/.local/state/yttrium-metadata-plan"
```

The build reuses the working patched renderer, including its libvirt seccomp workaround and disabled NVIDIA Vulkan preloading. Existing source modifications must exactly match the expected patch. Firmware uses 3,653,632-byte code plus 540,672-byte variables. Compiling Secure Boot support does not enable it or enroll keys in the VM.

Test firmware/QEMU in a diskless scratch VM first. Staging validates XML without redefining the VM. It preserves CPU, storage, networking, guest integration and GPU arguments. SMBIOS labels use host manufacturer/product/board names, never host UUID/serial numbers. Existing custom SMBIOS or passthrough configurations require review.

Default profile `metadata` retains CPU flags and Hyper-V performance features. The separate `--profile cpu-hidden` adds KVM hiding, replaces the Hyper-V vendor label, and disables the hypervisor CPU flag; it preserves the working CPU model and Hyper-V settings and needs separate boot/performance verification. Roll back to the baseline before staging another profile; existing generated SMBIOS settings are deliberately not overwritten.

## Activate and roll back

Save Windows work and use the existing disk-guarded stop command, flushing/unmounting reverse SMB before shutdown. Then:

```sh
sudo ./setup.sh concealment activate --out "$HOME/.local/state/yttrium-metadata-plan"
```

Activation requires the VM off and its configuration unchanged since staging. It backs up and copies powered-off NVRAM, installs a separate wrapper and defines the candidate. Original emulator, firmware and NVRAM remain available. Start using the existing disk-guarded command. Never mount passed-through raw filesystems from Linux while Windows owns them.

Verify boot/sign-in, Device Manager, Yttrium D3D11 rendering/readback, windowed/fullscreen input, RemoteApp resizing, direct disk I/O and reverse SMB. Compare performance with the baseline. Roll back after a guarded shutdown:

```sh
sudo ./setup.sh concealment rollback --out "$HOME/.local/state/yttrium-metadata-plan"
```

Rollback restores the saved definition and original untouched firmware/NVRAM, refuses unrelated/newer configurations, and does not revert Windows/game files. Keep staging directories private and outside Git.

## Management and diagnostics

`guest/Configure-SSH.ps1` configures an installed Windows OpenSSH Server for an existing local administrator, Ed25519 key authentication and a host-only firewall rule. Pin the server host key through trusted QGA before connecting. Use SSH for routine commands; retain QGA for bootstrap/recovery. The SSH transport shell is cmd; invoke `pwsh -NoProfile -NonInteractive` (or Windows PowerShell) explicitly for scripts. This avoids interactive profile jobs and prompt hooks delaying automation.

`guest/retry-update.ps1 -KB KB_NUMBER` retries only that offered update, saves durable status under ProgramData and never reboots. `NotOffered` does not prove an earlier update failure was repaired.

The VMAware harness runs five read-only checks, not the full experimental CLI. Apply `patches/vmaware-mingw-clang.patch` to its pinned checkout. This adapts MinGW struct padding, the older power-capability field name, and CPUID calls without removing checks. Build:

```sh
clang++ --target=x86_64-w64-windows-gnu -fms-extensions -include cpuid.h \
  -std=c++20 -O2 -static -I PATH_TO_VMAWARE/src tools/vmaware-selected.cpp \
  -o vmaware-selected.exe -lwbemuuid -lole32 -loleaut32 -liphlpapi \
  -lsetupapi -ladvapi32 -lpsapi -lshlwapi -lntdll -lwintrust -lcrypt32 \
  -lws2_32 -lgdi32 -Wl,--start-group -lstdc++ -lwinpthread -Wl,--end-group
```

Record individual checks and functional results. A diagnostic score cannot establish anti-cheat acceptance.
