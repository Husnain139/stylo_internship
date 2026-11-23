param([switch]$Detach, [switch]$SkipBuild, [switch]$Initialize, [switch]$SampleEmployees)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$env:HR_DESK_PUBLIC_ORIGIN = 'http://localhost:3000'
$env:HR_DESK_DATA_ROOT = Join-Path $runtime 'local-hr-desk-data'
$env:DATABASE_URL = 'postgresql://hr_desk:hr_desk@127.0.0.1:5433/hr_desk'
$env:HR_DESK_API_TARGET = 'http://127.0.0.1:8000'
$tessdata = Join-Path $runtime 'tessdata'
if (!$env:TESSDATA_PREFIX -and (Test-Path -LiteralPath (Join-Path $tessdata 'eng.traineddata'))) {
    $env:TESSDATA_PREFIX = $tessdata
}

if ((Get-NetTCPConnection -State Listen -LocalPort 8000,3000 -ErrorAction SilentlyContinue)) {
    throw 'Ports 8000 and 3000 must be free. Stop the running HR Desk processes first.'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
docker compose -f (Join-Path $root 'docker-compose.yml') up -d --wait db
if ($LASTEXITCODE -ne 0) { throw 'Could not start the HR Desk database.' }

Push-Location (Join-Path $root 'backend')
try {
    $python = Join-Path $PWD '.venv\Scripts\python.exe'
    if (!(Test-Path $python)) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    }
    & $python -c "import fastapi, uvicorn, pymupdf, docx, openai, psycopg, pgvector"
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Could not install the Python dependencies.' }
    }
    if ($Initialize -or $SampleEmployees) {
        $env:HR_DESK_MIGRATION_DATABASE_URL = $env:DATABASE_URL
        & $python -m app.migrate
        if ($LASTEXITCODE -ne 0) { throw 'HR Desk schema migration failed.' }
        $seedOptions = @()
        if ($SampleEmployees) { $seedOptions += '--sample-employees' }
        & $python -m app.bootstrap_local @seedOptions
        if ($LASTEXITCODE -ne 0) { throw 'HR Desk library setup failed. Check the database and OpenAI settings.' }
    }
}
finally {
    Pop-Location
}

Push-Location (Join-Path $root 'web')
try {
    if (!(Test-Path 'node_modules\next')) {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
    }
    if (!$SkipBuild -or !(Test-Path '.next\BUILD_ID')) {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Could not build the frontend.' }
    }
}
finally {
    Pop-Location
}

$api = Start-Process $python -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' `
    -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtime 'api.log') -RedirectStandardError (Join-Path $runtime 'api-error.log')
$next = Join-Path $root 'web\node_modules\next\dist\bin\next'
$web = Start-Process node.exe -ArgumentList ('"' + $next + '"'),'start','--hostname','127.0.0.1','--port','3000' `
    -WorkingDirectory (Join-Path $root 'web') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $runtime 'web.log') -RedirectStandardError (Join-Path $runtime 'web-error.log')

$ready = $false
try {
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($api.HasExited -or $web.HasExited) { break }
        $response = & curl.exe -4 -fs --max-time 2 'http://127.0.0.1:3000/api/health'
        if ($LASTEXITCODE -eq 0 -and $response -match '"ok":true') {
            $ready = $true
            $apiPort = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 8000
            $webPort = Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 3000
            @{ api = $apiPort.OwningProcess; web = $webPort.OwningProcess } | ConvertTo-Json |
                Set-Content -LiteralPath (Join-Path $runtime 'hr-desk-processes.json')
            Write-Host 'HR Desk is ready at http://localhost:3000'
            if ($Detach) { return }
            Write-Host 'Press Ctrl+C in this terminal when you finish.'
            while (!$api.HasExited -and !$web.HasExited) { Start-Sleep -Seconds 1 }
            break
        }
        Start-Sleep -Seconds 1
    }
    throw 'HR Desk stopped or did not start. See .runtime logs. For a new local database, run with -Initialize.'
}
finally {
    if (!$Detach -or !$ready) {
        foreach ($process in @($web, $api)) {
            if (!$process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
        }
    }
}
