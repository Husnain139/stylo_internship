$ErrorActionPreference = 'Stop'
$processFile = Join-Path $PSScriptRoot '.runtime\hr-desk-processes.json'
if (!(Test-Path -LiteralPath $processFile)) {
    Write-Host 'There is no recorded HR Desk process.'
    return
}

$record = Get-Content -LiteralPath $processFile -Raw | ConvertFrom-Json
foreach ($entry in @(
    @{ id = $record.api; port = 8000; command = 'uvicorn\s+app\.main:app' },
    @{ id = $record.web; port = 3000; command = 'next.*start.*--hostname\s+127\.0\.0\.1' }
)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$entry.id)"
    $socket = Get-NetTCPConnection -LocalPort $entry.port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $entry.id -and $_.LocalAddress -eq '127.0.0.1' }
    if ($process -and $socket -and $process.CommandLine -match $entry.command) {
        Stop-Process -Id $entry.id
    }
}
Remove-Item -LiteralPath $processFile
Write-Host 'HR Desk app processes stopped. PostgreSQL is still running.'
