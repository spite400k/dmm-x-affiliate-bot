#Requires -Version 5.1
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $ProjectRoot "scripts\run-gha-job.ps1"
$HiddenVbs = Join-Path $ProjectRoot "scripts\run-gha-job-hidden.vbs"
$Wscript = Join-Path $env:SystemRoot "System32\wscript.exe"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "runner not found: $Runner"
}
if (-not (Test-Path -LiteralPath $HiddenVbs)) {
    throw "hidden launcher not found: $HiddenVbs"
}

$tasks = @(
    @{ Name = "DmmXBot-Livedoor-DMM";      Job = "livedoor-dmm";      Schedule = "Daily";    Time = "20:00" }
    @{ Name = "DmmXBot-Livedoor-FANZA";    Job = "livedoor-fanza";    Schedule = "Daily";    Time = "20:10" }
    @{ Name = "DmmXBot-Livedoor-Mesugaki"; Job = "livedoor-mesugaki"; Schedule = "Daily";    Time = "20:20" }
    @{ Name = "DmmXBot-Twitter";           Job = "twitter";           Schedule = "OnDemand"; Time = $null }
    @{ Name = "DmmXBot-Seesaa-DMM";        Job = "seesaa-dmm";        Schedule = "OnDemand"; Time = $null }
)

function New-JobAction([string]$JobName) {
    # wscript + VBS Run(..., 0, True): create process with no console window
    $arg = "//nologo `"$HiddenVbs`" $JobName"
    return New-ScheduledTaskAction -Execute $Wscript -Argument $arg -WorkingDirectory $ProjectRoot
}

Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "Launcher:    $HiddenVbs"
Write-Host ""

foreach ($def in $tasks) {
    $taskName = $def.Name
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "remove existing: $taskName"
        if (-not $WhatIf) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
    }

    $action = New-JobAction $def.Job
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    if ($def.Schedule -eq "Daily") {
        $trigger = New-ScheduledTaskTrigger -Daily -At $def.Time
        Write-Host ("register: {0} daily {1} job={2}" -f $taskName, $def.Time, $def.Job)
        if (-not $WhatIf) {
            Register-ScheduledTask `
                -TaskName $taskName `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -Principal $principal `
                -Description ("dmm-x-affiliate-bot: {0}" -f $def.Job) `
                -Force | Out-Null
        }
    }
    else {
        Write-Host ("register: {0} on-demand job={1}" -f $taskName, $def.Job)
        if (-not $WhatIf) {
            Register-ScheduledTask `
                -TaskName $taskName `
                -Action $action `
                -Settings $settings `
                -Principal $principal `
                -Description ("dmm-x-affiliate-bot (manual): {0}" -f $def.Job) `
                -Force | Out-Null
        }
    }
}

Write-Host ""
Write-Host "done. check: Get-ScheduledTask -TaskName 'DmmXBot-*'"
Write-Host "run now:   Start-ScheduledTask -TaskName 'DmmXBot-Livedoor-DMM'"
Write-Host "logs:      .\logs\<job>-yyyyMMdd-HHmmss.log"
