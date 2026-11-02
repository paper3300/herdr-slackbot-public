# Plugin hook / action entry point: runs `python -m herdr_slackbot <command>` with the plugin venv.
#   launch   (startup hook) start the bridge (old Herdr: a fresh tab in workspace herdr-slack;
#            Herdr app: the hc terminal herdr-slackbot)
#   restart  stop the running bridge (addressed stop request) and start it again
#   stop     stop the running bridge
#   status   print bridge status (with -Notify: also as a Herdr notification)
#   open-wizard  (setup action) open a tab running the setup wizard
# -Backend auto|herdr|hc picks the Herdr backend (default: detected; see scripts\setup.ps1).
# The venv is created on first use when missing (e.g. after `herdr plugin link`).
param(
    [Parameter(Position = 0)][ValidateSet("launch", "restart", "stop", "status", "open-wizard")][string]$Command = "status",
    [switch]$Notify,
    [ValidateSet("auto", "herdr", "hc")][string]$Backend = "auto"
)

$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "herdr-slackbot: venv missing, running scripts\setup.ps1 first"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup.ps1")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $py)) {
        Write-Error "herdr-slackbot: setup failed; run scripts\setup.ps1 manually"
        exit 1
    }
}

$pyArgs = @("-m", "herdr_slackbot", $Command, "--backend", $Backend)
if ($Notify) { $pyArgs += "--notify" }
Push-Location $root
try {
    & $py @pyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
