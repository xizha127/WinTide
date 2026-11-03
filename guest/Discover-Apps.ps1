# SPDX-License-Identifier: MIT
# Query executable registrations without executing them. Outputs JSON, never shell code.
$ErrorActionPreference='Stop'
$roots=@('Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths','Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths')
foreach($sid in Get-ChildItem Registry::HKEY_USERS) {
 if ($sid.PSChildName -match '^S-1-5-21-\d+-\d+-\d+-\d+$') {$roots+="Registry::HKEY_USERS\$($sid.PSChildName)\Software\Microsoft\Windows\CurrentVersion\App Paths"}
}
$paths=@("$env:WINDIR\System32\notepad.exe")
foreach($root in $roots) {
 foreach($key in Get-ChildItem $root -ErrorAction SilentlyContinue) {
  $path=$key.GetValue('')
  if ($path -is [string]) {$paths+=[Environment]::ExpandEnvironmentVariables($path.Trim('"'))}
 }
}
$apps=@()
foreach($path in $paths | Sort-Object -Unique) {
 if ([IO.Path]::GetExtension($path) -ne '.exe' -or !(Test-Path -LiteralPath $path -PathType Leaf)) {continue}
 if ([IO.Path]::GetFileName($path) -match '(?i)unins|setup|update|crash|helper') {continue}
 $file=Get-Item -LiteralPath $path
 $name=$file.VersionInfo.FileDescription
 if (!$name) {$name=$file.VersionInfo.ProductName}
 if (!$name) {$name=$file.BaseName}
 $apps+=[pscustomobject]@{name=$name;exe=$file.FullName}
}
ConvertTo-Json -InputObject $apps -Compress
