#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "livedoor-dmm",
        "livedoor-fanza",
        "livedoor-mesugaki",
        "twitter",
        "seesaa-dmm"
    )]
    [string]$Job
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "venv python not found: $Python"
}

$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path -LiteralPath $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogsDir ("{0}-{1}.log" -f $Job, $stamp)
$stdoutFile = Join-Path $LogsDir ("{0}-{1}.stdout.tmp" -f $Job, $stamp)
$stderrFile = Join-Path $LogsDir ("{0}-{1}.stderr.tmp" -f $Job, $stamp)

$jobDefs = @{
    "livedoor-dmm"      = @("main_livedoor_atompub.py", "--account", "1", "--all-targets")
    "livedoor-fanza"    = @("main_livedoor_atompub.py", "--account", "2", "--all-targets")
    "livedoor-mesugaki" = @("main_livedoor_atompub.py", "--account", "6", "--all-targets")
    # GHA main.yml uses main.py; repo has main_x.py
    "twitter"           = @("main_x.py")
    "seesaa-dmm"        = @("main_seesaa_blog.py", "--account", "1", "--all-targets")
}

$argv = $jobDefs[$Job]
$prevUa = $env:SEESAA_XMLRPC_USER_AGENT
if ($Job -eq "seesaa-dmm") {
    $env:SEESAA_XMLRPC_USER_AGENT = "Mozilla/5.0 (compatible; dmm-x-affiliate-bot/1.0)"
}

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "o"), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

Write-Log ("START job={0} python={1} args={2}" -f $Job, $Python, ($argv -join " "))
Write-Log ("cwd={0} log={1}" -f $ProjectRoot, $logFile)

# Start-Process + file redirect: avoid PS treating Python logging (stderr) as terminating errors
$argLine = ($argv | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join " "

$exitCode = 0
try {
    $proc = Start-Process `
        -FilePath $Python `
        -ArgumentList $argLine `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile `
        -NoNewWindow `
        -PassThru `
        -Wait
    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode) { $exitCode = 0 }

    foreach ($tmp in @($stdoutFile, $stderrFile)) {
        if (Test-Path -LiteralPath $tmp) {
            Get-Content -LiteralPath $tmp -Encoding UTF8 -ErrorAction SilentlyContinue |
                Add-Content -LiteralPath $logFile -Encoding UTF8
        }
    }
}
catch {
    Write-Log ("ERROR: {0}" -f $_)
    $exitCode = 1
}
finally {
    Remove-Item -LiteralPath $stdoutFile, $stderrFile -ErrorAction SilentlyContinue
    if ($Job -eq "seesaa-dmm") {
        if ($null -eq $prevUa) {
            Remove-Item Env:SEESAA_XMLRPC_USER_AGENT -ErrorAction SilentlyContinue
        }
        else {
            $env:SEESAA_XMLRPC_USER_AGENT = $prevUa
        }
    }
}

Write-Log ("END job={0} exit={1}" -f $Job, $exitCode)
exit $exitCode
