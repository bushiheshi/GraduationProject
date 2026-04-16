$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $root '.venv\Scripts\python.exe'
$backendPort = 18080
$teacherPort = 15173
$backendOut = Join-Path $backend 'uvicorn-hidden.out.log'
$backendErr = Join-Path $backend 'uvicorn-hidden.err.log'
$frontendOut = Join-Path $frontend 'vite-hidden.out.log'
$frontendErr = Join-Path $frontend 'vite-hidden.err.log'

function Test-PortListening {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
}

if (-not (Test-PortListening $backendPort)) {
    Start-Process `
        -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', $backendPort, '--reload') `
        -WorkingDirectory $backend `
        -RedirectStandardOutput $backendOut `
        -RedirectStandardError $backendErr `
        -WindowStyle Hidden
}

if (-not (Test-PortListening $teacherPort)) {
    Start-Process `
        -FilePath 'npm.cmd' `
        -ArgumentList @('run', 'dev:teacher', '--', '--host', '0.0.0.0', '--port', $teacherPort) `
        -WorkingDirectory $frontend `
        -RedirectStandardOutput $frontendOut `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden
}

Start-Sleep -Seconds 3

Write-Host 'Project started.'
Write-Host "Backend: http://127.0.0.1:$backendPort/"
Write-Host "Teacher dev: http://127.0.0.1:$teacherPort/frontend/teacher/"
