# Credits and licenses

The underlying virtualization, graphics and Windows integration were built by the projects below. This repository contributes integration scripts, configuration recipes, documentation, and small compatibility patches. It does not claim authorship of their implementations.

| Project / people | Contribution to this setup | License/source |
|---|---|---|
| [arehnman: Yttrium VirtIO GPU](https://github.com/arehnman/yttrium-virtio-gpu) | Windows display/Direct3D driver and packaged Mesa/Venus components | See the release and individual source licenses |
| [arehnman: Yttrium QEMU](https://github.com/arehnman/yttrium-qemu) and [QEMU contributors](https://www.qemu.org/) | GPU presentation/renderer changes, guest PAT handling, machine emulation | QEMU GPLv2 with component-specific licenses |
| [arehnman: virglrenderer fork](https://github.com/arehnman/virglrenderer) and [virglrenderer](https://gitlab.freedesktop.org/virgl/virglrenderer) | Matching patched renderer and Venus render workers | MIT; included patch context retains this license |
| [arehnman: virtio-win-mesa](https://github.com/arehnman/virtio-win-mesa), [Mesa](https://www.mesa3d.org/) and Venus contributors | Windows user-mode graphics and Vulkan virtualization underlying the driver release | Mesa/component-specific licenses |
| [WinApps contributors](https://github.com/winapps-org/winapps), original [Fmstrat](https://github.com/Fmstrat/winapps) | Windows RemoteApp launching, app definitions, integration model | Mixed: see upstream [LICENSE.md](https://github.com/winapps-org/winapps/blob/main/LICENSE.md) and per-file notices; some original app definitions are proprietary. Fetched locally, not redistributed here |
| [FreeRDP contributors](https://github.com/FreeRDP/FreeRDP), including Ibrahim Sevinc's SDL3 RAIL work | RDP/RAIL and SDL3 native-Wayland RemoteApp windows | Apache-2.0; resize patch contexts retain the upstream copyright/license |
| [SDL contributors](https://libsdl.org/) | Native Linux/Wayland client windows | zlib |
| [libvirt](https://libvirt.org/) and Linux [KVM](https://linux-kvm.org/) | VM lifecycle, device isolation, guest-agent transport, virtualization | See respective LGPL/GPL component licenses |
| [VirtIO-Win](https://github.com/virtio-win/kvm-guest-drivers-windows) | Windows VirtIO drivers and QEMU Guest Agent ecosystem | See individual driver licenses |
| [VirtioFS / virtiofsd contributors](https://virtio-fs.gitlab.io/) | Shared host filesystem exposed to Windows | virtiofsd Apache-2.0/BSD-3-Clause; see upstream |
| [WinFsp / Bill Zissimopoulos and contributors](https://github.com/winfsp/winfsp) | Windows user-mode filesystem framework used by VirtioFS | See upstream GPL/commercial licensing |
| [EDK II](https://github.com/tianocore/edk2), [SPICE](https://www.spice-space.org/), [swtpm](https://github.com/stefanberger/swtpm) | UEFI firmware, original console/agent stack and virtual TPM | See upstream component licenses |

Additional research: [UTM](https://github.com/utmapp/UTM) and [osy's Neptune driver fork](https://github.com/osy/kvm-guest-drivers-windows) were reviewed, including the supplied UTM guest-tools ISO. **The tested graphics stack here uses arehnman's Yttrium release, not Neptune.** [WICI's GPU-sharing article](https://wici.ai/article/gpu-never-learned-to-share) helped motivate the investigation; no WICI implementation or firmware is used.

Version pins are in `components.lock.json`. No Windows installation files, test certificates, signed binaries, third-party ISOs or upstream source trees are bundled. Downloads retain their upstream terms. Original integration code is MIT; see `LICENSE`. Apache-2.0 and virglrenderer MIT license texts are in `licenses/` for included patch contexts.

The optional virtiofsd permission-policy patch is based on upstream virtiofsd1.14.0 (Apache-2.0/BSD-3-Clause). Its `src/main.rs` copyright is2019 Intel Corporation; `src/passthrough/mod.rs` copyright is2019 The Chromium OS Authors. All rights reserved. Their notices and license texts remain applicable; see the upstream source and `licenses/virtiofsd-*`. The local policy patch is additional integration work, not an upstream feature.

Optional metadata candidate: [AICodo/pve-emu-realpc](https://github.com/AICodo/pve-emu-realpc) and [AICodo's EDK II adaptation](https://github.com/AICodo/pve-emu-realpc_edk2-firmware-ovmf), building on [zhaodice/qemu-anti-detection](https://github.com/zhaodice/qemu-anti-detection), motivated the selected label changes. The implementation intentionally excludes broad device-ID/protocol changes and unverified sensor tables. QEMU patch context remains GPL-2.0; firmware context retains EDK II component licenses. [VMAware contributors](https://github.com/NotRequiem/VMAware) provide the MIT-licensed diagnostic library, with a small local Clang/MinGW portability patch. License texts are in `licenses/`. No opaque Strong binaries are redistributed. See [the opt-in recipe](docs/concealment.md).
