#Requires -Version 5.1
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$names = @(
    "DmmXBot-Livedoor-DMM",
    "DmmXBot-Livedoor-FANZA",
    "DmmXBot-Livedoor-Mesugaki",
    "DmmXBot-Twitter",
    "DmmXBot-Seesaa-DMM"
)

foreach ($name in $names) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($t) {
        Write-Host "remove: $name"
        if (-not $WhatIf) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
        }
    }
    else {
        Write-Host "not found: $name"
    }
}
