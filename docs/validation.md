# WinTide validation and limits

The reference system's components were tested live before packaging: raw physical Windows boot, WinApps app launch and floating resize, Yttrium hardware D3D11 create/clear/readback, NVIDIA allocations for corresponding virgl workers, and Windows/Linux shared-drive read/write with correct host ownership. These are observations from the reference system, not a fresh-machine installer certification.

Repository checks include Python unit tests for the disk guard, safe XML transformation, ACL preservation/idempotence, refusal paths and optional sharing; Python syntax; shell syntax; patch application against pinned sources; reconstructed patched SDL source equality to the working client; and publication checks. The generalized host installer is not applied to the working VM just to test packaging, because that would disrupt or replace a verified setup. Full Windows guest configuration is parsed without executing its changes on the working installation.

The optional windowed helper has four Rust policy tests and a Windows cross-build
with Clippy warnings denied. Its interactive RDP smoke test passed on the reference
VM: remembered and delayed maximized startup restored to normal, later manual
maximize remained possible, duplicate startup kept one helper, and a borderless
fullscreen fixture received no helper restore request. These tests use actual
Win32 maximization state and were run before SDL's separate windowed policy.
The current SDL patch was additionally tested with actual Settings and Explorer:
both opened tiled, Settings stayed restored inside Windows while its native
rectangle followed the tile, and the user confirmed the maximize cycle worked.
See `docs/fixes.md` for the cause and measured dimensions. The helper fixture's
manual-native-maximize assertions are not appropriate while SDL's windowed policy
is active: local maximization deliberately leaves the remote HWND restored.

Run local checks:

```sh
python3 -m unittest discover -s tests -v
python3 tools/check-publication.py
bash -n setup.sh
```

Build the GPU smoke test with MinGW:

```sh
x86_64-w64-mingw32-gcc -O2 tools/gpu-smoke.c -o gpu-smoke.exe -ld3d11 -ldxgi -ldxguid
```

Copy it into the guest and run it. It requests `D3D_DRIVER_TYPE_HARDWARE`, identifies the DXGI adapter, creates a GPU render target, clears red, copies to a staging texture, and checks exact RGBA255,0,0,255. `PASS` is stronger evidence than a device appearing in Task Manager. Match guest activity to host renderer worker processes with `nvidia-smi`. The executable is generated locally and ignored by Git.

Not established: D3D12 capability, any specific game's performance, anti-cheat compatibility, DirectStorage behavior, loading-time parity, extended stability, automatic attachment after a real VM restart on a second machine, or support for other GPU vendors. Do not market those as verified features.

## RemoteApp connection reuse

Repeated launches of the installed Explorer broker and a manual Notepad launch
were acknowledged over a single connection: one RDP handshake, one persistent
client PID, and unchanged existing window identities. Existing windows remained
tiled. A deliberately nonexistent executable returned a Windows RAIL error
without disconnecting the session; a subsequent Explorer launch still succeeded. `tests/rail-launch.cpp` covers concurrent launch forwarding, exact quoted
Unicode arguments, Windows-account separation, owner cleanup and rejection of an
insecure runtime directory. On Linux with FreeRDP development headers, compile it
against the patched source:

```sh
c++ -std=c++17 -Wall -Wextra -Werror -Wno-deprecated-declarations \
  -I /path/to/patched-freerdp/client/SDL/SDL3 \
  $(pkg-config --cflags freerdp-client3) tests/rail-launch.cpp \
  -o /tmp/wintide-rail-launch-test $(pkg-config --libs freerdp-client3)
/tmp/wintide-rail-launch-test
```

The launch socket is opt-in and Linux-only. Full-desktop session switching and
per-app redirection changes are not part of this behavior.
