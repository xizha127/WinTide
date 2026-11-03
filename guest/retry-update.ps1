param([Parameter(Mandatory=$true)][ValidatePattern('^KB[0-9]+$')][string]$KB)
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:ProgramData 'WinApps-Maintenance'
New-Item -ItemType Directory -Path $root -Force | Out-Null
$status = Join-Path $root "$KB-status.json"
function Save-State($phase, $details) {
    @{ Phase=$phase; Time=(Get-Date).ToString('o'); Details=$details } |
        ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $status
}
try {
    if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') {
        throw 'Complete pending restart before retrying an update.'
    }
    Save-State 'Searching' $KB
    $session = New-Object -ComObject Microsoft.Update.Session
    $search = $session.CreateUpdateSearcher().Search("IsInstalled=0 and Type='Software' and IsHidden=0")
    $updates = New-Object -ComObject Microsoft.Update.UpdateColl
    foreach ($update in $search.Updates) {
        if ($update.KBArticleIDs -contains $KB.Substring(2)) {
            if (-not $update.EulaAccepted) { $update.AcceptEula() }
            [void]$updates.Add($update)
        }
    }
    if ($updates.Count -eq 0) { Save-State 'NotOffered' $KB; exit 0 }
    Save-State 'Downloading' @($updates | ForEach-Object { $_.Title })
    $downloader = $session.CreateUpdateDownloader()
    $downloader.Updates = $updates
    $download = $downloader.Download()
    if ([int]$download.ResultCode -ne 2) { throw "Download result $($download.ResultCode), HRESULT $($download.HResult)" }
    Save-State 'Installing' $KB
    $installer = $session.CreateUpdateInstaller()
    $installer.Updates = $updates
    $result = $installer.Install()
    Save-State 'Finished' @{ ResultCode=[int]$result.ResultCode; HResult=$result.HResult; RebootRequired=$result.RebootRequired }
    if ([int]$result.ResultCode -ne 2) { exit 1 }
} catch {
    Save-State 'Failed' $_.Exception.Message
    exit 1
}
# Deliberately never reboots: the host must coordinate physical disk ownership.
