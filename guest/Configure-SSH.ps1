param(
    [Parameter(Mandatory=$true)][string]$PublicKey,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9._-]+$')][string]$UserName,
    [Parameter(Mandatory=$true)][ipaddress]$HostAddress,
    [switch]$InstallServer
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($PublicKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/]+={0,2}( .*)?$') { throw 'Expected an Ed25519 public key' }
if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    if (!$InstallServer) { throw 'Install OpenSSH Server first, or use -InstallServer' }
    $result = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
    if ($result.RestartNeeded) { throw 'OpenSSH installation requires a restart. Restart Windows normally, then resume setup.' }
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) { throw 'OpenSSH Server service is still missing' }
}
$user = Get-LocalUser $UserName
if (-not $user.Enabled) { throw 'User is disabled' }
$administrators = Get-LocalGroupMember -SID 'S-1-5-32-544'
if ($administrators.SID.Value -notcontains $user.SID.Value) { throw 'This recipe requires the existing administrator account' }
$root = Join-Path $env:ProgramData 'ssh'
New-Item -ItemType Directory -Path $root -Force | Out-Null
$config = Join-Path $root 'sshd_config'
if (-not (Test-Path $config)) {
    Copy-Item "$env:WINDIR\System32\OpenSSH\sshd_config_default" $config
}
$backup = "$config.pre-wintide"
$text = Get-Content $config -Raw
if ((Test-Path "$config.pre-winapps") -or $text -match '(?m)^# BEGIN WINAPPS\r?$') {
    throw 'Legacy SSH setup detected. Migrate its original backup and managed configuration block before running WinTide setup.'
}
if (-not (Test-Path $backup)) { Copy-Item $config $backup }
$text = [regex]::Replace($text, '(?ms)^# BEGIN WINTIDE\r?\n.*?^# END WINTIDE\r?\n', '')
$block = @"
# BEGIN WINTIDE
PubkeyAuthentication yes
PasswordAuthentication no
AuthenticationMethods publickey
AllowUsers $UserName
# END WINTIDE
"@
[IO.File]::WriteAllText($config, $block + "`r`n" + $text, (New-Object Text.UTF8Encoding $false))
$keys = Join-Path $root 'administrators_authorized_keys'
$existing = if (Test-Path $keys) { [IO.File]::ReadAllText($keys) } else { '' }
if ($existing.Split("`n").Trim() -notcontains $PublicKey.Trim()) {
    [IO.File]::WriteAllText($keys, $existing.TrimEnd() + "`r`n" + $PublicKey.Trim() + "`r`n", (New-Object Text.UTF8Encoding $false))
}
# Use SIDs to work on non-English Windows installations as well.
& icacls.exe $keys /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect administrator authorized keys' }
& "$env:WINDIR\System32\OpenSSH\ssh-keygen.exe" -A
& "$env:WINDIR\System32\OpenSSH\sshd.exe" -t
if ($LASTEXITCODE -ne 0) { Copy-Item $backup $config -Force; throw 'sshd config validation failed; restored backup' }
$rule = Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue
if ($rule) {
    $rule | Set-NetFirewallRule -Enabled True -Profile Any -RemoteAddress $HostAddress.IPAddressToString
} else {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH from virtualization host' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort 22 -RemoteAddress $HostAddress.IPAddressToString | Out-Null
}
New-Item -Path HKLM:\SOFTWARE\OpenSSH -Force | Out-Null
# Use cmd as the transport shell. Invoke pwsh/powershell -NoProfile explicitly
# for scripts so interactive profile jobs cannot hold an SSH session open.
$shell = "$env:WINDIR\System32\cmd.exe"
New-ItemProperty -Path HKLM:\SOFTWARE\OpenSSH -Name DefaultShell -Value $shell -PropertyType String -Force | Out-Null
Set-Service sshd -StartupType Automatic
Restart-Service sshd
Get-Content (Join-Path $root 'ssh_host_ed25519_key.pub')
