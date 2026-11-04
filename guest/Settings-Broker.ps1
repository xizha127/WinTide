# SPDX-License-Identifier: MIT
# Keep the RemoteApp launch alive for Windows Settings, which uses URI activation.
$ErrorActionPreference='Stop'
$session=(Get-Process -Id $PID).SessionId
Start-Process 'ms-settings:'
function SettingsWindow {
 @(Get-Process SystemSettings -ErrorAction SilentlyContinue | Where-Object {$_.SessionId -eq $session -and $_.MainWindowHandle -ne 0})
}
for($i=0;$i -lt 60;$i++) {
 if((SettingsWindow).Count) {break}
 Start-Sleep -Milliseconds 500
}
while((SettingsWindow).Count) {Start-Sleep -Milliseconds 500}
