# Runs the web app and the background worker, and restarts either if it stops.
. (Join-Path $PSScriptRoot "common.ps1")
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
Set-Location $AppDir
$pidFile = Join-Path $LogDir "gadaa.pids"

function Start-Part($name, $cmd) {
    $out = Join-Path $LogDir "$name.log"
    $err = Join-Path $LogDir "$name-errors.log"
    $argList = @("`"$Manage`"") + $cmd
    return Start-Process -FilePath $Py -ArgumentList $argList -WorkingDirectory $AppDir `
        -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
}

$web = Start-Part "web" @("serve")
$worker = Start-Part "worker" @("worker")
"$PID $($web.Id) $($worker.Id)" | Set-Content $pidFile
while ($true) {
    Start-Sleep -Seconds 10
    if (Test-Path (Join-Path $LogDir "stop.flag")) { break }
    if ($web.HasExited)    { Add-Content (Join-Path $LogDir "restarts.log") "$(Get-Date -Format s) web stopped, restarting";    $web = Start-Part "web" @("serve") }
    if ($worker.HasExited) { Add-Content (Join-Path $LogDir "restarts.log") "$(Get-Date -Format s) worker stopped, restarting"; $worker = Start-Part "worker" @("worker") }
    "$PID $($web.Id) $($worker.Id)" | Set-Content $pidFile
}
foreach ($p in @($web, $worker)) { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
Remove-Item (Join-Path $LogDir "stop.flag") -ErrorAction SilentlyContinue
