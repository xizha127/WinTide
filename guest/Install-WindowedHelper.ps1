# SPDX-License-Identifier: MIT
[CmdletBinding()]
param(
 [string]$BinaryPath,
 [Parameter(Mandatory=$true)][string]$WindowsUser,
 [switch]$Uninstall
)
$ErrorActionPreference='Stop'
$account=New-Object Security.Principal.NTAccount($WindowsUser)
$sid=$account.Translate([Security.Principal.SecurityIdentifier]).Value
$taskName='WinTide-Windowed-'+$sid
$directory=Join-Path $env:ProgramData 'wintide\windowed-helper'
$destination=Join-Path $directory 'wintide-windowed.exe'

if ($Uninstall) {
 $task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
 if ($task) {
  # The task action is only our helper, never an app or the RDP session itself.
  Stop-ScheduledTask -TaskName $taskName
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
 }
 Write-Output 'Windowed helper disabled. Application windows and RDP connections were not closed.'
 return
}
# Do not run both generations of the helper: they use different session mutexes.
if ((Test-Path -LiteralPath (Join-Path $env:ProgramData 'WinApps-Yttrium-Setup')) -or
    (Get-ScheduledTask -TaskName ('WinApps-Windowed-'+$sid) -ErrorAction SilentlyContinue) -or
    (Get-Process -Name 'winapps-windowed' -ErrorAction SilentlyContinue)) {
 throw 'Legacy helper/setup detected. Uninstall the previous helper and migrate its setup state first; see docs/getting-started.md.'
}
if (!$BinaryPath -or !(Test-Path -LiteralPath $BinaryPath -PathType Leaf)) {
 throw 'Supply -BinaryPath pointing to the locally built wintide-windowed.exe.'
}
$binary=(Resolve-Path -LiteralPath $BinaryPath).Path
$stream=[IO.File]::OpenRead($binary)
try {$isExecutable=$stream.ReadByte() -eq 77 -and $stream.ReadByte() -eq 90} finally {$stream.Dispose()}
if (!$isExecutable) {
 throw 'The supplied helper is not a Windows executable.'
}
$previous=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$copy=$binary -ne $destination
if ($copy -and (Test-Path -LiteralPath $destination)) {
 $copy=(Get-FileHash -LiteralPath $binary).Hash -ne (Get-FileHash -LiteralPath $destination).Hash
}
if ($copy) {
 if ($previous) {Stop-ScheduledTask -TaskName $taskName}
 # Task termination is asynchronous. Wait for Windows to release the image;
 # never kill an app/session or leave a stopped previous version on failure.
 try {
  for($attempt=0;$attempt -lt 30;$attempt++) {
   try {Copy-Item -LiteralPath $binary -Destination $destination -Force;break}
   catch [IO.IOException] {
    if ($attempt -eq 29) {throw}
    Start-Sleep -Milliseconds 100
   }
  }
 } catch {
  if ($previous) {Start-ScheduledTask -TaskName $taskName}
  throw
 }
}

# InteractiveToken is essential: an SSH/QGA/SYSTEM service cannot see user windows.
# A RemoteConnect trigger also covers an existing session reused by WinApps.
# Parallel instances permit different sessions; a session-local mutex deduplicates
# repeated launches in the same session without signing out or reconnecting RDP.
$service=New-Object -ComObject Schedule.Service
$service.Connect()
$definition=$service.NewTask(0)
$definition.RegistrationInfo.Description='Restore newly opened maximized WinApps windows once; preserve fullscreen and later manual maximize.'
$definition.Principal.UserId=$sid
$definition.Principal.LogonType=3 # TASK_LOGON_INTERACTIVE_TOKEN; no stored password.
$definition.Principal.RunLevel=0 # Standard user, no UAC bypass or elevated task.
$definition.Settings.Enabled=$true
$definition.Settings.AllowDemandStart=$true
$definition.Settings.DisallowStartIfOnBatteries=$false
$definition.Settings.StopIfGoingOnBatteries=$false
$definition.Settings.ExecutionTimeLimit='PT0S'
$definition.Settings.MultipleInstances=0 # TASK_INSTANCES_PARALLEL
foreach($state in 3,1) { # RemoteConnect, ConsoleConnect (helper is inactive on console).
 $trigger=$definition.Triggers.Create(11)
 $trigger.UserId=$sid
 $trigger.StateChange=$state
}
$trigger=$definition.Triggers.Create(9) # At logon, including the first RemoteApp logon.
$trigger.UserId=$sid
$action=$definition.Actions.Create(0)
$action.Path=$destination
$folder=$service.GetFolder('\')
$registered=$folder.RegisterTaskDefinition($taskName,$definition,6,$sid,$null,3,$null)
try {$null=$registered.Run($null)} catch {
 Write-Warning 'No interactive user session is available yet. The helper will start on the next WinApps/RDP connection.'
}
Write-Output ('Installed task '+$taskName)
Write-Output ('Helper SHA256: '+(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash)
Write-Output 'Only RemoteApp/RDP desktops are managed. No app launchers, RDP clients, or GPU settings were modified.'
