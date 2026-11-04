# SPDX-License-Identifier: MIT
[CmdletBinding()]
param(
 [ValidateSet('rdp','yttrium','share')][string]$Mode,
 [string]$WindowsUser,
 [string]$HostAddress='192.168.122.1',
 [ValidatePattern('^[A-Za-z0-9_-]{1,36}$')][string]$ShareTag='host-games',
 [ValidatePattern('^[D-Z]$')][string]$DriveLetter='H',
 [ValidatePattern('^\d+:\d+$')][string]$Owner='1000:1000',
 [switch]$EnableTestSigning,
 [switch]$DisableHibernation
)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {throw 'Run elevated inside the VM.'}
$base='C:\ProgramData\WinApps-Yttrium-Setup'
New-Item -ItemType Directory -Path $base -Force | Out-Null
function Native-OK([string]$Label) {if ($LASTEXITCODE -notin 0,3010) {throw "$Label failed: $LASTEXITCODE"}}
if ($Mode -eq 'rdp') {
 if (!$WindowsUser) {throw '-WindowsUser is required (a local account with a password, not PIN).'}
 $user=Get-LocalUser -Name $WindowsUser
 # These exports preserve original settings, once, before applying RDP changes.
 foreach($entry in @(
  @('HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server','terminal-server'),
  @('HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList','remoteapps'),
  @('HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services','rdp-policy')
 )) {
  if (!(Test-Path "$base\$($entry[1]).reg")) {reg.exe export $entry[0] "$base\$($entry[1]).reg" /y 2>$null | Out-Null}
 }
 Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server' -Name fDenyTSConnections -Value 0
 Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name UserAuthentication -Value 1
 foreach($pair in @(
  @('HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList','fDisabledAllowList'),
  @('HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services','fAllowUnlistedRemotePrograms')
 )) {New-Item $pair[0] -Force | Out-Null; New-ItemProperty $pair[0] -Name $pair[1] -PropertyType DWord -Value 1 -Force | Out-Null}
 $group=Get-LocalGroup -SID 'S-1-5-32-555'
 if (!(Get-LocalGroupMember $group -ErrorAction SilentlyContinue | Where-Object SID -eq $user.SID)) {Add-LocalGroupMember $group -Member $user}
 foreach($name in 'RemoteDesktop-UserMode-In-TCP','RemoteDesktop-UserMode-In-UDP') {
  $rule=Get-NetFirewallRule -Name $name
  if (!(Test-Path "$base\$name.xml")) {$rule | Get-NetFirewallAddressFilter | Export-Clixml "$base\$name.xml"}
  $rule | Set-NetFirewallRule -Enabled True -RemoteAddress $HostAddress
 }
 Set-Service TermService -StartupType Automatic;Start-Service TermService
 Write-Output 'RDP/RemoteApps enabled with NLA; firewall restricted to the configured host address. Account/password unchanged.'
}
elseif ($Mode -eq 'yttrium') {
 if (!$EnableTestSigning) {throw 'Test-signing opt-in is required.'}
 $secure=$false
 try {$secure=Confirm-SecureBootUEFI} catch {
  # Non-Secure-Boot OVMF may omit the variable entirely rather than return false.
  if ($_.Exception.Message -notmatch 'not supported|Variable is currently undefined: 0xC0000100') {throw}
 }
 if ($secure) {throw 'Disable Secure Boot for this VM first; native firmware is not modified by this script.'}
 $driver="$base\driver"
 $zip="$base\yttrium-2026-11-02.zip"
 $url='https://github.com/arehnman/yttrium-virtio-gpu/releases/download/yttrium-experimental-2026-11-02/yttrium-viogpu3d-experimental-2026-11-02.zip'
 $sha='d740f749215de5eb15f055b0f2238c4800b2385960dda450521b9577b35ddc87'
 if (!(Test-Path $zip)) {Invoke-WebRequest -UseBasicParsing $url -OutFile $zip}
 if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha) {throw 'Driver archive checksum mismatch.'}
 if (!(Test-Path $driver)) {Expand-Archive $zip $driver}
 if (!(Test-Path "$base\before.bcd")) {
  bcdedit.exe /export "$base\before.bcd";Native-OK 'BCD backup'
  bcdedit.exe /enum '{current}' | Set-Content "$base\bcd-current-before.txt"
  Get-CimInstance Win32_VideoController | Export-Clixml "$base\display-before.xml"
  New-Item -ItemType Directory "$base\display-drivers-before" -Force | Out-Null
  foreach($d in Get-CimInstance Win32_PnPSignedDriver | Where-Object DeviceClass -eq 'DISPLAY') {
   if ($d.InfName -like 'oem*.inf') {pnputil.exe /export-driver $d.InfName "$base\display-drivers-before" | Out-Null;Native-OK 'Display driver backup'}
  }
 }
 $inf="$driver\Install_Debug\Win11\amd64\viogpu3d.inf"
 if (!(Test-Path $inf)) {throw 'Expected Win11 amd64 driver layout missing.'}
 $section=''
 foreach($line in Get-Content $inf) {
  if ($line -match '^\[(.+)\]') {$section=$Matches[1];continue}
  $sys=if ($section -in @('VioGpu3D_Files.Usermode','VioGpu3D_Files.Vulkan')) {'System32'} elseif ($section -in @('VioGpu3D_Files.Wow64','VioGpu3D_Files.VulkanWow64')) {'SysWOW64'} else {$null}
  if (!$sys -or $line -notmatch '^([^;,\s]+)') {continue}
  $name=$Matches[1];$target="$base\system-file-backup\$sys\$name";$source="$env:WINDIR\$sys\$name"
  if ((Test-Path $source) -and !(Test-Path $target)) {New-Item -ItemType Directory (Split-Path $target) -Force | Out-Null;Copy-Item $source $target}
 }
 $cert="$driver\Install_Debug\VirtIOTestCert.cer"
 $certificate=New-Object Security.Cryptography.X509Certificates.X509Certificate2($cert);$thumb=$certificate.Thumbprint
 if (!(Test-Path "$base\certificate-before.xml")) {
  [pscustomobject]@{Thumbprint=$thumb;RootAlreadyPresent=(Test-Path "Cert:\LocalMachine\Root\$thumb");PublisherAlreadyPresent=(Test-Path "Cert:\LocalMachine\TrustedPublisher\$thumb")} | Export-Clixml "$base\certificate-before.xml"
 }
 Import-Certificate $cert -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
 Import-Certificate $cert -CertStoreLocation Cert:\LocalMachine\TrustedPublisher | Out-Null
 bcdedit.exe /set '{current}' testsigning on;Native-OK 'Enable test signing'
 if ($DisableHibernation) {powercfg.exe /hibernate off;Native-OK 'Disable hibernation'}
 pnputil.exe /add-driver $inf;Native-OK 'Stage Yttrium driver'
 Write-Output 'Driver verified, backed up and staged. Shut Windows down cleanly, apply host setup, then start it. No reboot or forced shutdown performed.'
}
elseif ($Mode -eq 'share') {
 $svc=Get-CimInstance Win32_Service | Where-Object Name -eq 'VirtioFsSvc'
 if (!$svc -or !(Get-Service WinFsp.Launcher -ErrorAction SilentlyContinue)) {throw 'Install official VirtIO-Win VioFS and WinFsp first; see docs/sharing.md.'}
 $existing=Get-PSDrive $DriveLetter -ErrorAction SilentlyContinue
 if ($existing -and $svc.State -ne 'Running') {throw 'Requested drive letter is already occupied.'}
 if (!(Test-Path "$base\virtiofs-before.xml")) {$svc | Select-Object Name,PathName,StartMode | Export-Clixml "$base\virtiofs-before.xml"}
 pnputil.exe /add-driver 'C:\Program Files\Virtio-Win\VioFS\viofs.inf' /install;Native-OK 'VirtioFS driver'
 $path='"C:\Program Files\Virtio-Win\VioFS\virtiofs.exe" -t '+$ShareTag+' -m '+$DriveLetter+': -o '+$Owner+' -i'
 $r=Invoke-CimMethod -InputObject $svc -MethodName Change -Arguments @{PathName=$path;StartMode='Manual'}
 if ($r.ReturnValue -ne 0) {throw "Service configuration failed: $($r.ReturnValue)"}
 Write-Output 'Optional shared-drive service configured. Host share helper starts it after attachment.'
}
