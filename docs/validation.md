# Validation and limits

## Current desktop integration

The reference desktop is CachyOS/Hyprland with Windows 11 Pro under system libvirt,
a physical Windows boot disk, and the pinned Yttrium graphics stack. These checks
validate the working components, not a fresh-machine end-to-end installation.

| Behavior | Evidence |
|---|---|
| Tiling and resize | Settings and Explorer opened tiled. Settings's local 844×1380 allocation matched a restored Windows outer rectangle of 858×1387, including frame margins. The user confirmed resize behavior. |
| Maximize / restore | Windows remained restored while local maximization changed the compositor allocation; returning to a tile remained resizable. Confirmed interactively. |
| Additional app launches | Explorer and Notepad launches used one persistent SDL process and one RDP handshake. Existing window identities were retained. |
| New Explorer windows | Two consecutive launcher invocations increased the Explorer count from one to two to three while retaining the original window and connection. Confirmed by the user. |
| Failed app launch | A nonexistent executable returned a RAIL error without disconnecting open apps; a subsequent Explorer launch succeeded. |
| Launch broker | The C++ regression test covers concurrent handoff, quoted Unicode arguments, account separation, owner cleanup and insecure-runtime-directory refusal. |

The source patch was applied to the pinned FreeRDP revision and all eight modified
or added files compared exactly with the tested build source. The running and
installed executables were also compared. These checks do not guarantee behavior
for every app, compositor, DPI configuration or reconnect scenario.

The Windows startup helper was disabled and its process stopped on 2026-11-04.
A fresh Explorer launch opened tiled through the patched SDL client, and the user
confirmed the behavior still worked without the helper. It has been retired;
window-state handling is provided by the SDL patch. This retirement check was
interactive, not a new automated geometry/maximize regression run.

## Other component checks

- **Physical boot:** Windows booted and accepted sign-in from its existing raw
  installation. Runtime tests cover mounted-disk refusal, read-only disk refusal,
  saved-memory remount refusal and eligible host-mount restoration.
- **Shared graphics:** hardware D3D11 device creation, GPU clear/readback and host
  GPU activity were verified with Yttrium. This is not a game benchmark.
- **Storage:** optional VirtioFS read/write and the permission guard passed live
  checks. Steam compatibility did not; the current game disk is Windows-owned
  NTFS. See [storage observations](sharing.md).

## Command and guided setup checks

The installed `wintide` command was adopted into the working deployment without
replacing its driver, credentials or launcher core. Live checks on 2026-11-04:

- `wintide --test` reached RDP and authenticated through SSH without opening a
  graphical connection.
- `wintide --ssh` ran commands and parsed the guest PowerShell scripts; the
  existing SDL process remained unchanged.
- A temporary app created through `wintide apps add` launched one additional tiled
  Explorer window from its desktop entry, retaining the existing SDL connection.
  Its temporary launcher and metadata were subsequently removed.
- Animated progress was exercised in a terminal; plain output and failed-stage
  checkpoints were checked separately. Progress measures completed stages.
- Desktop argument quoting was round-tripped through Gio with spaces, quotes,
  backslashes and literal shell metacharacters.

The Python suite also checks SSH/RDP route separation, guarded-start failure,
preservation of imported app metadata, private logs and named-profile isolation.
The separate fresh Windows test below exercises installation as well.

## Fresh Windows guest validation

On 2026-11-04, [Quickemu](https://github.com/quickemu-project/quickemu)
4.9.9 (`6d386de2c957c60bb8fce0c225a23fdd7df3994e`) was installed from
upstream and used to install a disposable Windows 11 Enterprise Evaluation guest
(build 26300). It used a standalone 64 GiB image, four vCPUs and 6 GiB RAM.
After a clean shutdown, its image and UEFI variable store were imported into
system libvirt, with QEMU Guest Agent working. This is the existing, bootable
Windows VM prerequisite; Quickemu is validation tooling, not a WinTide dependency.

The test used a separate prefix, named client profile and VM. The working physical
Windows installation was not reconfigured. All pinned host components were built
afresh, then the guided setup configured RemoteApps, key-only SSH, guarded host
integration, guest graphics, app discovery and desktop entries.

The run exposed and corrected:

- Passwordless sudo policies where `sudo -v` still prompts for a password.
- Certificate import failing under the guest agent's LocalSystem account; the
  installer now uses `certutil` and checks its exit status.
- A retained SPICE audio backend after changing the VM display; its existing
  audio ID is preserved and the backend changed to host PulseAudio.
- Driver staging leaving the display-only driver selected. Setup now explicitly
  activates the matching Yttrium driver, restarts Windows, and checks its INF,
  version and device status before reporting success.
- Guest-agent readiness retries and clearer errors when a guest command result
  is lost, so an unknown result does not silently cause command replay.

Verified in the fresh guest:

- Yttrium `100.2026.11.1` bound to the expected VirtIO GPU with device error zero.
- Hardware Direct3D 11 device creation selected Yttrium; render-target clear and
  readback returned RGBA `(255, 0, 0, 255)`, with process exit status zero.
- Two Explorer launches produced separate tiled windows, preserving the first
  window and SDL process; Settings opened tiled in that same process.
- SSH authentication and commands worked without opening another graphical
  connection. RDP and SSH connection checks passed.

**Full-desktop rendering did not pass on this fresh build.** Bare
`wintide-validation` started the VM, authenticated and created an active RDP
session, but displayed black. Windows recorded repeated `dwm.exe` failures in
`dwmcore.dll` with exception `0x889800c5`. This also occurred after a clean boot;
it was not only a RemoteApp-to-desktop transition. Waking the host displays and
trying the RDP8 graphics pipeline did not resolve it. The test profile was
returned to its generated settings. The precise driver/OS cause remains
unresolved; connectivity checks and a healthy GPU device alone do not establish
a usable full desktop. No speculative graphics policy was applied to the working
physical Windows installation.

This was an iterative validation run: code fixes required reviewed checkpoint
updates, and a partially applied host stage was inspected and completed manually
while preserving its original rollback files. It was **not** an uninterrupted
first-run success or a clean Linux host test. The final driver activation,
restart and verification stages were subsequently exercised through the wizard.
Physical disk ownership guards, optional VirtioFS and other GPU vendors were not
retested in this image-backed guest.

Quickget's automated Windows download was unavailable during testing, so an
[official Microsoft evaluation ISO](https://www.microsoft.com/en-us/evalcenter/download-windows-11-enterprise)
was used. Quickemu's disposable auto-login was disabled before RDP testing;
an active console session can otherwise trigger a connection takeover prompt.
WinTide does not change an existing installation's auto-login preferences.

## Repository checks

From the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 tools/check-publication.py
bash -n setup.sh
```

The publication checker examines the Git index, so stage the intended changes
before using it as a pre-push check. It does not scan ignored local files.
The Python suite checks XML preservation/refusals, disk lifecycle, generated
launchers and permission policy. CI also parses guest PowerShell. Passing these checks
is not evidence that the complete installer has run on another machine.

For the Linux launch broker, use FreeRDP development headers and the patched
source (the broker header is added by `patches/freerdp-sdl-resize.patch`):

```sh
c++ -std=c++17 -Wall -Wextra -Werror -Wno-deprecated-declarations \
  -I /path/to/patched-freerdp/client/SDL/SDL3 \
  $(pkg-config --cflags freerdp-client3) tests/rail-launch.cpp \
  -o /tmp/wintide-rail-launch-test $(pkg-config --libs freerdp-client3)
/tmp/wintide-rail-launch-test
```

The GPU smoke test is a manual diagnostic for checking graphics after driver or
renderer changes. Setup does not build or run it. Build it separately:

```sh
x86_64-w64-mingw32-gcc -O2 tools/gpu-smoke.c -o gpu-smoke.exe -ld3d11 -ldxgi -ldxguid
```

Run it inside the Windows desktop session. It requests `D3D_DRIVER_TYPE_HARDWARE`,
identifies the adapter, clears a GPU render target red, copies it to a staging
texture and checks RGBA `(255, 0, 0, 255)`. The generated executable stays outside Git.

## Not established

DirectX 12, game/anti-cheat compatibility, DirectStorage, native-equivalent latency,
other GPU vendors, other compositors, long-term stability and a clean-machine
installer run remain unverified. Image-backed mode requires a standalone disk image; backing chains are not
supported. Full-desktop RDP and console logins can still switch
the Windows session; the shared launch broker handles RemoteApps only.
