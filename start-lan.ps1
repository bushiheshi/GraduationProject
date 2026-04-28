$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $root '.venv\Scripts\python.exe'
$backendPort = 18080
$backendOut = Join-Path $backend 'uvicorn-lan.out.log'
$backendErr = Join-Path $backend 'uvicorn-lan.err.log'

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-LanIpAddresses {
    $configs = Get-NetIPConfiguration |
        Where-Object { $_.IPv4Address -and $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' }

    return $configs |
        ForEach-Object { $_.IPv4Address.IPAddress } |
        Where-Object { $_ -and $_ -notlike '127.*' } |
        Select-Object -Unique
}

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
}

Write-Host 'Initializing database...'
Push-Location $backend
try {
    & $python 'scripts/init_db.py'
}
finally {
    Pop-Location
}

Write-Host 'Building teacher frontend...'
Push-Location $frontend
try {
    & 'npm.cmd' 'run' 'build:teacher'
}
finally {
    Pop-Location
}

if (-not (Get-NetFirewallRule -DisplayName 'AIGC Classroom LAN 18080' -ErrorAction SilentlyContinue)) {
    try {
        New-NetFirewallRule `
            -DisplayName 'AIGC Classroom LAN 18080' `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $backendPort `
            -Action Allow `
            -ErrorAction Stop | Out-Null
    }
    catch {
        Write-Warning 'Firewall rule was not created automatically. Run PowerShell as administrator if LAN access is blocked.'
    }
}

if (-not (Test-PortListening $backendPort)) {
    Write-Host 'Starting backend service...'
    Start-Process `
        -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', $backendPort) `
        -WorkingDirectory $backend `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden
}
else {
    Write-Host "Backend port $backendPort is already listening. Reusing existing process."
}

Start-Sleep -Seconds 3

$lanIps = Get-LanIpAddresses

Write-Host ''
Write-Host 'LAN deployment is running.'
Write-Host "Local:  http://127.0.0.1:$backendPort/"
foreach ($ip in $lanIps) {
    Write-Host "LAN:    http://$ip`:$backendPort/"
}
Write-Host "Health: http://127.0.0.1:$backendPort/health"
