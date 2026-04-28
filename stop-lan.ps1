$ErrorActionPreference = 'SilentlyContinue'

$backendPort = 18080

$processIds = Get-NetTCPConnection -LocalPort $backendPort -State Listen |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force
}

Write-Host 'LAN deployment stopped.'
