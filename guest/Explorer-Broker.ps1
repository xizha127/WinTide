# SPDX-License-Identifier: MIT
# Open a NEW This PC window per launch; keep its RemoteApp process alive.
$ErrorActionPreference='Stop'
$shell=New-Object -ComObject Shell.Application
# Serialize discovery so concurrent clicks each associate with their own HWND.
$mutex=New-Object Threading.Mutex($false,'Local\WinTide-Explorer-Launch')
$locked=$false
$opened=@()
function ExplorerWindows {
 @($shell.Windows() | Where-Object {$_.FullName -match '\\explorer\.exe$'})
}
try {
 try {$locked=$mutex.WaitOne(30000)} catch [Threading.AbandonedMutexException] {$locked=$true}
 if (!$locked) {throw 'Explorer launch is busy; try again.'}
 $before=@(ExplorerWindows | ForEach-Object {[long]$_.HWND})
 Start-Process explorer.exe -ArgumentList '/n,::{20D04FE0-3AEA-1069-A2D8-08002B30309D}'
 for($i=0;$i -lt 100;$i++) {
  Start-Sleep -Milliseconds 200
  $opened=@(ExplorerWindows | Where-Object {$before -notcontains [long]$_.HWND} | ForEach-Object {[long]$_.HWND})
  if ($opened.Count) {break}
 }
 if (!$opened.Count) {throw 'Explorer did not create a new window.'}
} finally {
 if ($locked) {$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
# Do not restore, close or otherwise manipulate any pre-existing folder windows.
while (@(ExplorerWindows | Where-Object {$opened -contains [long]$_.HWND}).Count) {
 Start-Sleep -Milliseconds 500
}
