param([ValidatePattern('^[D-Z]$')][string]$DriveLetter = 'H')
$ErrorActionPreference = 'Stop'
$buffer = New-Object byte[] (4MB)
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
$sha = [Security.Cryptography.SHA256]::Create()
$samples = @()
try {
    for ($trial = 0; $trial -lt 5; $trial++) {
        $clock = [Diagnostics.Stopwatch]::StartNew()
        for ($i = 0; $i -lt 32; $i++) { [void]$sha.ComputeHash($buffer) }
        $clock.Stop()
        $samples += $clock.Elapsed.TotalMilliseconds
    }
} finally { $sha.Dispose() }
$path = "${DriveLetter}:\winapps-candidate-$([guid]::NewGuid().ToString('N')).bin"
if (-not (Test-Path "${DriveLetter}:\")) { throw 'Benchmark drive is absent' }
$created = $false
try {
    $stream = [IO.FileStream]::new($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write,
        [IO.FileShare]::None, 1MB, [IO.FileOptions]::WriteThrough)
    $created = $true
    try {
        $clock = [Diagnostics.Stopwatch]::StartNew()
        for ($i = 0; $i -lt 64; $i++) { $stream.Write($buffer, 0, $buffer.Length) }
        $stream.Flush($true)
        $clock.Stop()
        $writeMBps = 256 / $clock.Elapsed.TotalSeconds
    } finally { $stream.Dispose() }
    $stream = [IO.FileStream]::new($path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::Read, 1MB, [IO.FileOptions]::SequentialScan)
    try {
        $clock.Restart()
        while ($stream.Read($buffer, 0, $buffer.Length) -gt 0) { }
        $clock.Stop()
        $readMBps = 256 / $clock.Elapsed.TotalSeconds
    } finally { $stream.Dispose() }
    [pscustomobject]@{
        Hash128MiBMedianMs = @($samples | Sort-Object)[2]
        WriteThrough256MiBMBps = $writeMBps
        BufferedRead256MiBMBps = $readMBps
    } | ConvertTo-Json
} finally {
    if ($created) { Remove-Item -LiteralPath $path -Force }
}
# Buffered reads can hit Windows cache; this is a regression smoke test, not a
# physical-disk maximum-throughput measurement. No existing files are modified.
