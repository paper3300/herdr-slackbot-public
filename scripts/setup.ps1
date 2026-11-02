# herdr-slackbot setup (Windows): venv + dependencies, then `python -m herdr_slackbot setup`
# (.env skeleton without overwriting values + Slack app manifest; on the Herdr app also the
# Slack bridge bar mod in ~\.config\herdr-app\mods\herdr-slackbot).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 [-Backend auto|herdr|hc]
#       [-SlashCommand /herdr-me] [-DisplayName "Herdr (me)"] [-ConfigDir <dir>] [-SkipConfig] [-Wizard]
#
# -Backend: hc = Herdr desktop app (config in %APPDATA%\herdr-slackbot), herdr = old Herdr CLI
# (plugin config dir). Default auto: the Herdr app when `hc` is installed, else the old CLI.
# Also the old Herdr plugin's [[build]] step (herdr plugin install runs it non-interactively).
# -Wizard runs the interactive setup wizard instead (`python -m herdr_slackbot wizard`: Slack app,
# tokens, bridge start, pairing); it needs a terminal.
param(
    [ValidateSet("auto", "herdr", "hc")][string]$Backend = "auto",
    [string]$SlashCommand,
    [string]$DisplayName,
    [string]$ConfigDir,
    [switch]$SkipConfig,
    [switch]$Wizard
)

# Native tools write progress to stderr; don't let PowerShell 5.1 turn that into errors.
$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"

function Find-BasePython {
    $candidates = @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3"), @("python"), @("python3"))
    foreach ($c in $candidates) {
        $exe = $c[0]
        $pre = @($c | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $ok = & $exe @pre -c "import sys; print(int(sys.version_info >= (3, 11)))" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$ok".Trim() -eq "1") { return , $c }
    }
    return $null
}

if (-not (Test-Path $py)) {
    $base = Find-BasePython
    if (-not $base) {
        Write-Error "herdr-slackbot setup: Python 3.11+ not found (install it from python.org or 'winget install Python.Python.3.12')."
        exit 1
    }
    Write-Host "creating venv: $venv (python: $($base -join ' '))"
    $exe = $base[0]
    $pre = @($base | Select-Object -Skip 1)
    & $exe @pre -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $py)) {
        Write-Error "herdr-slackbot setup: creating the venv failed"
        exit 1
    }
}

Write-Host "installing dependencies into $venv"
& $py -m pip install --disable-pip-version-check --quiet --editable $root
if ($LASTEXITCODE -ne 0) {
    Write-Error "herdr-slackbot setup: pip install failed (exit $LASTEXITCODE)"
    exit 1
}

if ($SkipConfig) { exit 0 }

$setupArgs = @("-m", "herdr_slackbot", $(if ($Wizard) { "wizard" } else { "setup" }), "--backend", $Backend)
if ($ConfigDir) { $setupArgs += @("--config-dir", $ConfigDir) }
if ($SlashCommand) { $setupArgs += @("--slash-command", $SlashCommand) }
if ($DisplayName) { $setupArgs += @("--display-name", $DisplayName) }
Push-Location $root
try {
    & $py @setupArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
