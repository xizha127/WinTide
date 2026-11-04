# SPDX-License-Identifier: MIT
# Run in the same interactive RDP session as the helper, never directly via SSH.
[CmdletBinding()]
param([string]$ReportPath=(Join-Path $env:LOCALAPPDATA 'wintide\windowed-helper-verification.json'))
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class WindowedCheck {
 [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr window);
 [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
}
'@
if ([WindowedCheck]::GetSystemMetrics(0x1000) -eq 0) {throw 'Run this test in an RDP/RemoteApp session.'}
$results=New-Object 'Collections.Generic.List[object]'
function Check([string]$name,[bool]$pass) {$results.Add([pscustomobject]@{name=$name;pass=$pass})}
function Pump([int]$milliseconds) {
 $until=[DateTime]::UtcNow.AddMilliseconds($milliseconds)
 while([DateTime]::UtcNow -lt $until) {[Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 20}
}
function New-CheckWindow {
 $window=New-Object Windows.Forms.Form
 $window.Text='WinTide windowed helper verification'
 $window.Size=New-Object Drawing.Size(800,500)
 return $window
}
$f=$null
try {
 $session=(Get-Process -Id $PID).SessionId
 $helpers=@(Get-Process wintide-windowed | Where-Object SessionId -eq $session)
 Check 'helper is in this interactive session' ($helpers.Count -eq 1)
 if ($helpers.Count -eq 1) {
  Start-Process -FilePath $helpers[0].Path
  Pump 400
  Check 'repeated launch does not create a second helper' (@(Get-Process wintide-windowed | Where-Object SessionId -eq $session).Count -eq 1)
 }
 $f=New-CheckWindow
 $f.WindowState='Maximized'
 $f.Show();Pump 1500
 Check 'remembered maximized startup becomes windowed' (![WindowedCheck]::IsZoomed($f.Handle))
 $f.WindowState='Maximized';Pump 700
 Check 'manual maximize after restore is preserved' ([WindowedCheck]::IsZoomed($f.Handle))
 $f.Close();$f.Dispose()

 $f=New-CheckWindow
 $f.Show();Pump 600
 $f.WindowState='Maximized';Pump 1200
 Check 'delayed startup maximize becomes windowed' (![WindowedCheck]::IsZoomed($f.Handle))
 $f.Close();$f.Dispose()

 $f=New-CheckWindow
 $f.Show();Pump 3400
 $f.WindowState='Maximized';Pump 700
 Check 'manual maximize after startup grace is preserved' ([WindowedCheck]::IsZoomed($f.Handle))
 $sameHandle=$f.Handle
 $f.Hide();Pump 400
 $f.WindowState='Maximized'
 $f.Show();Pump 1200
 Check 'hidden app reusing its HWND starts windowed again' ($f.Handle -eq $sameHandle -and ![WindowedCheck]::IsZoomed($f.Handle))
 $f.WindowState='Maximized';Pump 700
 Check 'manual maximize after reused-window restore is preserved' ([WindowedCheck]::IsZoomed($f.Handle))
 $f.Close();$f.Dispose()

 $f=New-CheckWindow
 $f.FormBorderStyle='None'
 $monitor=[Windows.Forms.Screen]::PrimaryScreen.Bounds
 $f.Bounds=$monitor
 $logPath=Join-Path $env:LOCALAPPDATA "wintide\windowed-helper-$session.log"
 $logLines=@(Get-Content $logPath).Count
 $f.Show()
 $fullscreenHandle=$f.Handle.ToInt64()
 Pump 1200
 # In RemoteApp, the Linux compositor may resize even a borderless window.
 # Check that this helper never sends SW_RESTORE to the fullscreen HWND.
 $log=@(Get-Content $logPath) | Select-Object -Skip $logLines
 Check 'fullscreen receives no helper restore request' (!($log -match "restore hwnd=$fullscreenHandle pid=$PID "))
 Check 'borderless fullscreen keeps its border style' ($f.FormBorderStyle -eq 'None')
 $f.Close();$f.Dispose()
} catch {
 $results.Add([pscustomobject]@{name='test execution';pass=$false;error=$_.Exception.Message})
} finally {
 if ($f -and !$f.IsDisposed) {$f.Close();$f.Dispose()}
 $results | ConvertTo-Json | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}
if (@($results | Where-Object {!$_.pass}).Count) {exit 1}
