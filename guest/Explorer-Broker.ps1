# SPDX-License-Identifier: MIT
# Keep the RemoteApp session alive while an Explorer folder window is open.
$ErrorActionPreference='Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ExplorerRestore {
 [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr window,int command);
}
'@
$shell=New-Object -ComObject Shell.Application
$windows=@($shell.Windows() | Where-Object {$_.FullName -match '\\explorer\.exe$'})
if (!$windows.Count) {Start-Process explorer.exe}
for($i=0;$i -lt 40;$i++) {
 Start-Sleep -Milliseconds 500
 $windows=@($shell.Windows() | Where-Object {$_.FullName -match '\\explorer\.exe$'})
 if ($windows.Count) {break}
}
foreach($window in $windows) {[ExplorerRestore]::ShowWindowAsync([IntPtr]$window.HWND,9) | Out-Null}
while (@($shell.Windows() | Where-Object {$_.FullName -match '\\explorer\.exe$'}).Count) {Start-Sleep -Milliseconds 500}
