# CrimeAI one-command launcher for Windows.
#
#   .\start.cmd            install what is missing, build, start, seed demo data, open the app
#   .\start.cmd stop       stop everything (data is kept)
#   .\start.cmd status     show running services
#   .\start.cmd logs       follow API and worker logs
#   .\start.cmd reset      delete all data and start again from scratch

param(
    [ValidateSet('up', 'stop', 'status', 'logs', 'reset')]
    [string]$Command = 'up'
)

# Native commands are checked through $LASTEXITCODE; 'Stop' would turn their stderr into fatal errors on PowerShell 5.1.
$ErrorActionPreference = 'Continue'
$Root = Join-Path $PSScriptRoot 'crimeai'
$ComposeFile = Join-Path $Root 'docker-compose.dev.yml'
$CredFile = Join-Path $Root 'backend\var\demo-credentials.txt'
$AppUrl = 'http://localhost:5173'
$ApiUrl = 'http://localhost:8000'

function Say([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host "`nERROR: $Message" -ForegroundColor Red; exit 1 }

function Compose {
    & docker compose -f $ComposeFile @args
    if ($LASTEXITCODE -ne 0) { Fail "docker compose $($args -join ' ') failed (exit $LASTEXITCODE)." }
}

# Build one image at a time: three torch images unpacking at once can exhaust Docker's VM and drop the
# build engine ("failed to receive status: ... EOF"). If a build still fails, the cache is usually left
# with a broken snapshot (for example after "wsl --shutdown" mid-build), so prune it and try once more.
function Build-Images {
    $env:COMPOSE_PARALLEL_LIMIT = '1'
    & docker compose -f $ComposeFile build
    if ($LASTEXITCODE -eq 0) { return }
    Say 'Build failed; clearing the Docker build cache and retrying once...'
    & docker builder prune -f *> $null
    & docker compose -f $ComposeFile build
    if ($LASTEXITCODE -ne 0) {
        Fail "Image build failed twice. Restart Docker Desktop (or run 'wsl --shutdown' and reopen it), wait until it says 'Engine running', then run start again."
    }
}

function Test-DockerRunning {
    & docker info *> $null
    return $LASTEXITCODE -eq 0
}

function Initialize-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Say 'Docker is not installed.'
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Say 'Installing Docker Desktop with winget (Windows will ask for admin approval)...'
            winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
            Fail 'Docker Desktop is installed. Restart Windows if asked, open Docker Desktop once to finish its setup, then run this script again.'
        }
        Fail 'Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and run this script again.'
    }
    if (-not (Test-DockerRunning)) {
        $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (-not (Test-Path $desktop)) { Fail 'Docker is installed but not running. Start Docker and run this script again.' }
        Say 'Starting Docker Desktop...'
        Start-Process $desktop
        $deadline = (Get-Date).AddMinutes(3)
        while (-not (Test-DockerRunning)) {
            if ((Get-Date) -gt $deadline) { Fail 'Docker Desktop did not become ready within 3 minutes. Open it, wait until it says "running", and retry.' }
            Start-Sleep -Seconds 3
        }
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'Docker Compose v2 is required. Update Docker Desktop and retry.' }
}

# Name of a non-Docker process listening on $Port, or $null when the port is free or held by Docker.
function Get-ForeignListener([int]$Port) {
    $dockerProcesses = @('com.docker.backend', 'com.docker.proxy', 'wslrelay', 'vpnkit', 'dockerd', 'docker')
    foreach ($listener in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $name = (Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        if ($name -and $dockerProcesses -notcontains $name) { return "$name (PID $($listener.OwningProcess))" }
    }
    return $null
}

function Resolve-Ports {
    # The app's URL and API origin are fixed, so these two must be free.
    foreach ($port in 5173, 8000) {
        $owner = Get-ForeignListener $port
        if ($owner) { Fail "Port $port is already used by $owner. Close it and run this script again." }
    }
    # Database and Redis ports are only for connecting from this machine; move them if something else has them.
    foreach ($service in @(@{ Var = 'CRIMEAI_DB_PORT'; Port = 5433; Label = 'YugabyteDB' },
                           @{ Var = 'CRIMEAI_REDIS_PORT'; Port = 6379; Label = 'Redis' })) {
        $port = $service.Port
        while (Get-ForeignListener $port) { $port++ }
        if ($port -ne $service.Port) {
            Say "$($service.Label): port $($service.Port) is taken by $(Get-ForeignListener $service.Port); using $port instead."
        }
        Set-Item -Path "Env:$($service.Var)" -Value $port
    }
}

function Wait-Http([string]$Url, [string]$Label, [int]$Minutes) {
    $deadline = (Get-Date).AddMinutes($Minutes)
    Write-Host "    waiting for $Label" -NoNewline
    while ($true) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { Write-Host ' ready'; return }
        } catch { }
        if ((Get-Date) -gt $deadline) {
            Write-Host ''
            Fail "$Label did not come up within $Minutes minutes. See: .\start.cmd logs"
        }
        Write-Host '.' -NoNewline
        Start-Sleep -Seconds 5
    }
}

function New-DemoPassword {
    $chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $bytes = New-Object byte[] 14
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return (-join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })) + 'aA1'
}

function Initialize-DemoData {
    $users = (& docker compose -f $ComposeFile exec -T db bash -c 'bin/ysqlsh -h $(hostname) -U crimeai -d crimeai -tAc "SELECT count(*) FROM users"' 2>$null | Out-String).Trim()
    if ($users -and $users -ne '0') {
        Say 'Demo data already loaded.'
        return
    }
    $password = New-DemoPassword
    Say 'Loading demo data (3,000 cases, FIRs in several Indian languages, a planted crime series)...'
    Compose exec -T -e "SEED_PASSWORD=$password" -e LOG_LEVEL=WARNING api python scripts/seed_data.py
    New-Item -ItemType Directory -Force -Path (Split-Path $CredFile) | Out-Null
    @(
        'CrimeAI local demo users (all share one password)',
        '',
        'admin@crimeai.example     (Admin)',
        'analyst@crimeai.example   (Analyst)',
        'police@crimeai.example    (Police / SHO)',
        'readonly@crimeai.example  (Read-only)',
        'officer01..05@crimeai.example (Police)',
        '',
        "password: $password"
    ) | Set-Content -Path $CredFile -Encoding utf8
    Say 'Training models and building intelligence (a few minutes on first run)...'
    Compose exec -T -e LOG_LEVEL=WARNING worker python scripts/bootstrap_demo.py
}

# Meko shared memory: datapacks, SOPs and partner-agency history. Idempotent; skipped without MEKO_API_KEY.
function Initialize-Meko {
    $envFile = Join-Path $Root 'backend\.env'
    if (-not ((Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^MEKO_API_KEY=\S+' -Quiet))) {
        Say 'Meko is off (add MEKO_API_KEY=mko_tkn_... to crimeai\backend\.env and run start again to turn it on).'
        return
    }
    Say 'Setting up Meko shared memory (datapacks, SOPs, partner agencies)...'
    & docker compose -f $ComposeFile exec -T -e LOG_LEVEL=WARNING api python scripts/meko_setup.py
    if ($LASTEXITCODE -ne 0) { Say 'Meko setup did not finish; the app still runs. Retry: .\start.cmd' }
}

function Show-Summary {
    $password = '(see crimeai\backend\var\demo-credentials.txt)'
    if (Test-Path $CredFile) {
        $line = Select-String -Path $CredFile -Pattern '^password:\s*(\S+)' | Select-Object -First 1
        if ($line) { $password = $line.Matches[0].Groups[1].Value }
    }
    Write-Host ''
    Write-Host '  CrimeAI is running' -ForegroundColor Green
    Write-Host '  ------------------------------------------------------------'
    Write-Host "  App        $AppUrl" -ForegroundColor Yellow
    Write-Host "  API docs   $ApiUrl/docs"
    Write-Host '  Login      admin@crimeai.example   (sees every screen; also analyst@ / police@ / readonly@)'
    Write-Host "  Password   $password"
    Write-Host '  ------------------------------------------------------------'
    Write-Host '  Stop: .\start.cmd stop    Logs: .\start.cmd logs    Fresh start: .\start.cmd reset'
    Write-Host ''
}

switch ($Command) {
    'stop' {
        Initialize-Docker
        Compose stop
        Say 'Stopped. Your data is kept; run .\start.cmd to start again.'
    }
    'status' {
        Initialize-Docker
        Compose ps
    }
    'logs' {
        Initialize-Docker
        & docker compose -f $ComposeFile logs -f --tail 100 api worker
    }
    'reset' {
        Initialize-Docker
        $answer = Read-Host 'This deletes all CrimeAI data (cases, FIRs, users, uploads). Type YES to continue'
        if ($answer -ne 'YES') { Fail 'Cancelled.' }
        Compose down -v
        if (Test-Path $CredFile) { Remove-Item $CredFile }
        Say 'All data removed. Run .\start.cmd to start fresh.'
    }
    'up' {
        Initialize-Docker
        Resolve-Ports
        Say 'Building and starting CrimeAI (the first run downloads about 3 GB and can take 10-20 minutes)...'
        Build-Images
        Compose up -d
        Wait-Http "$ApiUrl/health" 'API' 15
        Initialize-DemoData
        Initialize-Meko
        Wait-Http $AppUrl 'web app' 15
        Show-Summary
        Start-Process $AppUrl
    }
}
