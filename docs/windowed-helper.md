# Optional Windows windowed-startup helper

The current SDL patch implements WinTide's cross-desktop resize/maximize behavior.
This helper is a separate Windows-side startup policy, not a prerequisite for the
main setup. Its standalone test expects Windows-native manual maximization;
those assertions conflict with the SDL policy that deliberately keeps the remote
HWND restored. Do not run that fixture through the current patched RemoteApp
connection as a pass/fail test of WinTide. See [current validation](validation.md).

`guest/windowed-helper/` is a small Rust Windows program using Microsoft's
[`windows-sys` bindings from windows-rs](https://github.com/microsoft/windows-rs).
It watches top-level windows in the interactive RDP session and calls
`ShowWindowAsync(SW_RESTORE)` once for a newly shown maximized window. It does
not maximize first, send keyboard shortcuts, change FreeRDP, or reconnect RDP.

The helper watches each new window for three seconds, allowing for apps that
apply their remembered maximize state after showing. A maximize must settle
for 300 ms before restoration. Each visible-window lifecycle receives at most one restore request; hiding and showing a reused HWND rearms it, and
manual maximization afterward is allowed. An app that maximizes itself again
after that request, or more than three seconds after appearing, is not forced
back repeatedly. Maximizing manually during that initial grace period can be
treated as a startup maximize.

Fullscreen is exempt when the window covers its monitor and is either
unmaximized (such as F11) or lacks a caption (such as borderless fullscreen).
Child windows, tool windows, cloaked windows, shell surfaces, and the RemoteApp
marker are excluded. These are Windows window-state/style checks, not a promise
to recognize every game's custom fullscreen implementation. Elevated apps may
refuse a standard-user helper's restore request.

Build separately from the GPU/RDP stack on Linux (Rust and MinGW required):

```sh
rustup target add x86_64-pc-windows-gnu
./setup.sh --config local-config.json build-windowed-helper
sudo ./setup.sh --config local-config.json install-windowed-helper --windows-user USER
```

The install command uploads the locally built executable through QEMU Guest
Agent; it does not download or execute an unreviewed release. Alternatively,
build on Windows with `cargo build --locked --release` in
`guest/windowed-helper`, then run the installer in an elevated PowerShell:

```powershell
.\guest\Install-WindowedHelper.ps1 -BinaryPath .\guest\windowed-helper\target\release\wintide-windowed.exe -WindowsUser USER
```

The scheduled task runs as that user with an interactive token, without a saved
password or elevation. Logon and RDP reconnect triggers start it alongside
WinApps, including reuse of an existing RemoteApp session. A session-local mutex
prevents duplicate helpers. It stays available for subsequent app launches and
is inactive on the native console. Already visible windows are included when
the helper first starts. No per-app launchers need modification.

Installation starts it immediately if the user is signed in. Otherwise it
starts at the next RDP/WinApps logon. The task is named `WinTide-Windowed-<SID>`;
the binary is under `%ProgramData%\wintide\windowed-helper`.
Diagnostics under `%LOCALAPPDATA%\wintide\windowed-helper-<session>.log` record
only version/session and restore HWND/PID/request status, not titles, document
paths or credentials. A queued restore is not proof that the app accepted it.

Remove the task without closing apps or disconnecting Windows:

```sh
sudo ./setup.sh --config local-config.json remove-windowed-helper --windows-user USER
```

Or use `Install-WindowedHelper.ps1 -WindowsUser USER -Uninstall` in Windows.
Uninstall disables the task and stops its helper instances; the binary and
diagnostics remain for inspection. `wintide-windowed.exe --stop` can also stop
the helper in the caller's own interactive session.

For behavioral verification, run `guest/Test-WindowedHelper.ps1` in the same
interactive RDP session (not directly via SSH/QGA session 0). It opens disposable
WinForms windows and checks actual Windows maximization state for remembered
startup, delayed startup, and subsequent manual maximize; it also checks
deduplication and that fullscreen receives no helper restore request. Results
are written to `%LOCALAPPDATA%\wintide\windowed-helper-verification.json`.
RemoteApp's Linux compositor can independently resize borderless test windows;
the fullscreen check does not claim exclusive fullscreen or game compatibility.
