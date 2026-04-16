$ErrorActionPreference = 'SilentlyContinue'

$ports = 18080, 15173
$processIds = Get-NetTCPConnection -LocalPort $ports -State Listen |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $processIds) {
    Stop-Process -Id $processId -Force
}

Write-Host 'Project stopped.'
