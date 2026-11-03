# SPDX-License-Identifier: MIT
# Run elevated after restoring the old libvirt XML and booting with its old graphics.
$ErrorActionPreference='Stop'
$base='C:\ProgramData\WinApps-Yttrium-Setup'
if (!(Test-Path "$base\before.bcd")) {throw 'Original setup backup not found; refusing to guess.'}
$devices=Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Where-Object FriendlyName -like '*Yttrium*'
foreach($device in $devices) {Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction SilentlyContinue}
$drivers=Get-WindowsDriver -Online | Where-Object {$_.OriginalFileName -match '\\viogpu3d\.inf$'}
foreach($driver in $drivers) {
 pnputil.exe /delete-driver $driver.Driver /uninstall /force
 if ($LASTEXITCODE -notin 0,3010) {throw 'Yttrium driver removal failed; inspect output.'}
}
foreach($inf in Get-ChildItem "$base\display-drivers-before" -Filter *.inf -Recurse) {pnputil.exe /add-driver $inf.FullName /install}
# Do not overwrite the entire live boot store; restore only the setting we changed.
$before=Get-Content "$base\bcd-current-before.txt" -Raw
if ($before -notmatch '(?m)^testsigning\s+') {bcdedit.exe /deletevalue '{current}' testsigning}
else {Write-Warning 'Test-signing existed before setup; retained. Review bcd-current-before.txt.'}
$cert=Import-Clixml "$base\certificate-before.xml"
if (!$cert.RootAlreadyPresent) {Remove-Item "Cert:\LocalMachine\Root\$($cert.Thumbprint)" -ErrorAction SilentlyContinue}
if (!$cert.PublisherAlreadyPresent) {Remove-Item "Cert:\LocalMachine\TrustedPublisher\$($cert.Thumbprint)" -ErrorAction SilentlyContinue}
foreach($sys in 'System32','SysWOW64') {sfc.exe "/scanfile=$env:WINDIR\$sys\opengl32.dll"}
Write-Output 'Graphics rollback applied. Restart Windows. Hibernation was intentionally not reenabled for physical-disk safety.'
