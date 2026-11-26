# Shared settings for the GADAA Windows scripts.
$ErrorActionPreference = "Stop"
$AppDir  = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DataDir = [Environment]::GetEnvironmentVariable("GADAA_DATA_DIR", "User")
if (-not $DataDir) { $DataDir = "C:\GADAA\data" }
$env:GADAA_DATA_DIR = $DataDir
$Venv    = Join-Path $AppDir ".venv"
$Py      = Join-Path $Venv "Scripts\python.exe"
$Manage  = Join-Path $AppDir "manage.py"
$LogDir  = Join-Path $DataDir "logs"
$TaskName = "GADAA Office"

function Say($text)  { Write-Host "  $text" }
function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "PROBLEM: $text" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }

function Invoke-Manage {
    param([Parameter(ValueFromRemainingArguments = $true)] $Rest)
    & $Py $Manage @Rest
    if ($LASTEXITCODE -ne 0) { throw "manage.py $($Rest -join ' ') failed" }
}
