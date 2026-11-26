. (Join-Path $PSScriptRoot "common.ps1")
New-Item -ItemType File -Force -Path (Join-Path $LogDir "stop.flag") | Out-Null
$pidFile = Join-Path $LogDir "gadaa.pids"
if (Test-Path $pidFile) {
    foreach ($id in (Get-Content $pidFile).Split(" ")) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
}
Remove-Item (Join-Path $LogDir "stop.flag") -ErrorAction SilentlyContinue
Write-Host "GADAA Office has stopped. It starts again at the next login, or with START."
