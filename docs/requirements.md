# Requirements

The tested automated path is Arch/CachyOS, x86-64 KVM, system libvirt with systemd, GTK3/Wayland, a separate raw Windows disk, Windows 11 Pro, and NVIDIA Vulkan. Other distributions require adapting package names/paths; the script does not automatically change package repositories.

Suggested Arch packages (review availability on your distribution):

```sh
sudo pacman -S --needed base-devel git python meson ninja cmake pkgconf rustup libcap-ng libseccomp \
  libvirt virt-manager qemu-full edk2-ovmf swtpm virtiofsd dosfstools libdrm pixman \
  gtk3 libepoxy spice spice-protocol libslirp libpulse \
  vulkan-tools vulkan-headers vulkan-icd-loader \
  sdl3 sdl3_image sdl3_ttf openssl cups alsa-lib fuse3 \
  libxkbcommon wayland wayland-protocols nasm mingw-w64-gcc
```

Your distro's QEMU package may already pull most build libraries. QEMU's configure and FreeRDP's CMake checks identify missing development dependencies. Keep the existing distro GPU driver; this project does not install/unbind it. `vulkaninfo --summary` must show the intended GPU. Node access must permit the configured desktop UID read/write access; the installer refuses to silently chmod devices.

Start/configure libvirt's default NAT network and ensure the Windows VM can reach the internet before guest downloads. Preserve your firewall policy and authorize only forwarding through the libvirt bridge. Do not flush or disable your firewall. The host-address example assumes libvirt's conventional `192.168.122.1` gateway; configure the actual value.

Secure Boot must be disabled **for the VM** before test-signing. Use a private VM EFI image/BCD store for physical Windows, as described in [physical disk preparation](physical-disk.md). QEMU Guest Agent must already be installed in Windows and connected through `org.qemu.guest_agent.0`; the initial base VM needs this channel too.

The native build uses host shared libraries, so source pins are reproducible while a byte-for-byte build is not guaranteed across distro library updates. Record package versions locally when reproducing a failure.

Optional guarded VirtioFS builds require a configured Rust toolchain (`rustup default stable` if none is installed) and the pinned Cargo.lock dependencies. The source pin is in components.lock.json.

The physical-disk config must list the raw Windows disks by stable by-id paths.
Do not use placeholder disks to bypass validation for an image-only VM.

The Linux SDL launch broker needs the desktop session's `XDG_RUNTIME_DIR`, owned
by that user with no group/other access. Launch from the desktop user's session;
a root shell is not an equivalent client environment. The optional Windows
helper additionally needs the Rust Windows target and MinGW, as described in
[its guide](windowed-helper.md). The default setup does not build that helper.
