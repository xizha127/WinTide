# SPDX-License-Identifier: MIT
# Optional; never run automatically by setup.sh. Preview is the default.
[CmdletBinding()]
param([ValidateSet('Preview','Apply','Restore')][string]$Mode='Preview',[string]$WindowsUser,[string]$Backup)
$ErrorActionPreference='Stop'
if ($Mode -eq 'Restore') {
 if (!$Backup -or !(Test-Path "$Backup\run.xml")) {throw 'Supply the exact backup directory.'}
 foreach($entry in Import-Clixml "$Backup\run.xml") {New-Item $entry.Key -Force | Out-Null;New-ItemProperty $entry.Key -Name $entry.Name -Value $entry.Value -PropertyType $entry.Kind -Force | Out-Null}
 foreach($entry in Import-Clixml "$Backup\files.xml") {if (Test-Path $entry.Original) {throw "Restore target already exists: $($entry.Original)"};Move-Item $entry.Saved $entry.Original}
 foreach($entry in Import-Clixml "$Backup\tasks.xml") {Enable-ScheduledTask -TaskName $entry.TaskName -TaskPath $entry.TaskPath | Out-Null}
 Write-Output 'Startup entries restored; services were not changed.';return
}
if (!$WindowsUser) {throw 'Specify the local Windows username.'}
$sid=(Get-LocalUser $WindowsUser).SID.Value
$profile=(Get-CimInstance Win32_UserProfile | Where-Object SID -eq $sid).LocalPath
if (!$profile -or !(Test-Path "Registry::HKEY_USERS\$sid")) {throw 'Sign in to that user before inspecting startup entries.'}
$keep='(?i)qemu|spice|virtio|blnsvr|SecurityHealth|Windows Defender'
$entries=@();$files=@();$tasks=@()
foreach($key in @('Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Run','Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',"Registry::HKEY_USERS\$sid\SOFTWARE\Microsoft\Windows\CurrentVersion\Run")) {
 if (!(Test-Path $key)) {continue}
 $item=Get-Item $key
 foreach($name in $item.GetValueNames()) {
  $value=$item.GetValue($name,$null,'DoNotExpandEnvironmentNames')
  if ("$name $value" -notmatch $keep) {$entries+=[pscustomobject]@{Key=$key;Name=$name;Value=$value;Kind=$item.GetValueKind($name).ToString()}}
 }
}
foreach($folder in @("$profile\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup",'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup')) {
 $files+=@(Get-ChildItem $folder -Force -File -ErrorAction SilentlyContinue | Where-Object {$_.Name -ne 'desktop.ini' -and $_.Name -notmatch $keep})
}
$tasks=@(Get-ScheduledTask | Where-Object {$_.Settings.Enabled -and $_.TaskPath -notlike '\Microsoft\*' -and $_.Triggers.CimClass.CimClassName -match 'Logon|Boot' -and (($_.Actions.Execute -join ';') -notmatch ($keep+'|MicrosoftEdgeUpdate'))})
[pscustomobject]@{RunEntries=$entries.Name;StartupFiles=$files.FullName;ScheduledTasks=$tasks.TaskName} | Format-List
if ($Mode -eq 'Preview') {Write-Output 'Preview only; no changes made.';return}
$Backup='C:\ProgramData\WinApps-Yttrium-Setup\startup-'+(Get-Date -Format yyyyMMdd-HHmmss)
New-Item -ItemType Directory $Backup | Out-Null
Export-Clixml -InputObject @($entries) "$Backup\run.xml"
$records=@();$taskRecords=@();$i=0
foreach($file in $files) {$records+=[pscustomobject]@{Original=$file.FullName;Saved="$Backup\startup-$i"};$i++}
Export-Clixml -InputObject @($records) "$Backup\files.xml"
foreach($task in $tasks) {$taskRecords+=[pscustomobject]@{TaskName=$task.TaskName;TaskPath=$task.TaskPath};Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Set-Content "$Backup\task-$i.xml";$i++}
Export-Clixml -InputObject @($taskRecords) "$Backup\tasks.xml"
foreach($entry in $entries) {Remove-ItemProperty $entry.Key -Name $entry.Name}
foreach($entry in $records) {Move-Item $entry.Original $entry.Saved}
foreach($task in $tasks) {Disable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null}
Write-Output "Startup apps disabled with backup: $Backup. Running processes and services unchanged."
