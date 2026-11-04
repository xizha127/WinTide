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
These checks do not substitute for a fresh Windows installation test.

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
