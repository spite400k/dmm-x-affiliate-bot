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
    @{ Name = "DmmXBot-Livedoor-DMM";      Job = "livedoor-dmm";      Schedule = "Daily";    Times = @("20:00") }
    @{ Name = "DmmXBot-Livedoor-FANZA";    Job = "livedoor-fanza";    Schedule = "Daily";    Times = @("20:10") }
    @{ Name = "DmmXBot-Livedoor-Mesugaki"; Job = "livedoor-mesugaki"; Schedule = "Daily";    Times = @("20:20") }
    @{ Name = "DmmXBot-Twitter";           Job = "twitter";           Schedule = "OnDemand"; Times = @() }
    # GHA seasaa-dmm.yml: UTC 03:15 / 11:15 = JST 12:15 / 20:15
    @{ Name = "DmmXBot-Seesaa-DMM"; Job = "seesaa-dmm"; Schedule = "Daily"; Times = @("12:15", "20:15"); TaskPath = "\dmm\seasaa\" }
)

function Get-TaskPath([hashtable]$Def) {
    if ($Def.TaskPath) { return $Def.TaskPath }
    return "\"
}

function Remove-RegisteredTask([string]$TaskName, [string]$TaskPath) {
    $existing = Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "remove existing: ${TaskPath}${TaskName}"
        Unregister-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath -Confirm:$false
    }
}

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
    $taskPath = Get-TaskPath $def

    # Seesaa などパス移行時: ルート直下の旧タスクを削除
    if ($taskPath -ne "\") {
        if (-not $WhatIf) {
            Remove-RegisteredTask $taskName "\"
        }
        else {
            $legacy = Get-ScheduledTask -TaskName $taskName -TaskPath "\" -ErrorAction SilentlyContinue
            if ($legacy) {
                Write-Host "would remove legacy: \${taskName}"
            }
        }
    }

    if (-not $WhatIf) {
        Remove-RegisteredTask $taskName $taskPath
    }
    else {
        $existing = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "would remove existing: ${taskPath}${taskName}"
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
        $triggers = @(
            foreach ($at in $def.Times) {
                New-ScheduledTaskTrigger -Daily -At $at
            }
        )
        $timesLabel = $def.Times -join ", "
        Write-Host ("register: {0}{1} daily {2} job={3}" -f $taskPath, $taskName, $timesLabel, $def.Job)
        if (-not $WhatIf) {
            Register-ScheduledTask `
                -TaskName $taskName `
                -TaskPath $taskPath `
                -Action $action `
                -Trigger $triggers `
                -Settings $settings `
                -Principal $principal `
                -Description ("dmm-x-affiliate-bot: {0}" -f $def.Job) `
                -Force | Out-Null
        }
    }
    else {
        Write-Host ("register: {0}{1} on-demand job={2}" -f $taskPath, $taskName, $def.Job)
        if (-not $WhatIf) {
            Register-ScheduledTask `
                -TaskName $taskName `
                -TaskPath $taskPath `
                -Action $action `
                -Settings $settings `
                -Principal $principal `
                -Description ("dmm-x-affiliate-bot (manual): {0}" -f $def.Job) `
                -Force | Out-Null
        }
    }
}

Write-Host ""
Write-Host "done. check: Get-ScheduledTask -TaskPath '\dmm\seasaa\'"
Write-Host "run now:   Start-ScheduledTask -TaskName 'DmmXBot-Seesaa-DMM' -TaskPath '\dmm\seasaa\'"
Write-Host "logs:      .\logs\<job>-yyyyMMdd-HHmmss.log"
