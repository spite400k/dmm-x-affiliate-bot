#Requires -Version 5.1
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$names = @(
    @{ Name = "DmmXBot-Livedoor-DMM";      TaskPath = "\" }
    @{ Name = "DmmXBot-Livedoor-FANZA";    TaskPath = "\" }
    @{ Name = "DmmXBot-Livedoor-Mesugaki"; TaskPath = "\" }
    @{ Name = "DmmXBot-Twitter";           TaskPath = "\" }
    @{ Name = "DmmXBot-Seesaa-DMM";        TaskPath = "\dmm\seasaa\" }
    @{ Name = "DmmXBot-Seesaa-DMM";        TaskPath = "\" }  # legacy location
)

foreach ($entry in $names) {
    $name = $entry.Name
    $taskPath = $entry.TaskPath
    $t = Get-ScheduledTask -TaskName $name -TaskPath $taskPath -ErrorAction SilentlyContinue
    if ($t) {
        Write-Host "remove: ${taskPath}${name}"
        if (-not $WhatIf) {
            Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false
        }
    }
    else {
        Write-Host "not found: ${taskPath}${name}"
    }
}
