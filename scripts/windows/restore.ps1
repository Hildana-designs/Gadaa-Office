# Restore a backup. Stops the app, makes a safety copy, restores, starts again.
. (Join-Path $PSScriptRoot "common.ps1")
Add-Type -AssemblyName System.Windows.Forms
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.InitialDirectory = Join-Path $DataDir "backups"
$dlg.Filter = "GADAA backups (*.gadaabak)|*.gadaabak"
$dlg.Title = "Choose the backup to restore"
if ($dlg.ShowDialog() -ne "OK") { exit 0 }
& (Join-Path $PSScriptRoot "stop.ps1")
Set-Location $AppDir
& $Py $Manage restore $dlg.FileName
$ok = $LASTEXITCODE -eq 0
schtasks /Run /TN $TaskName | Out-Null
if ($ok) { Write-Host "Restore finished and the app is starting again." -ForegroundColor Green } else { Write-Host "Restore did not run. Your data was not changed." -ForegroundColor Red }
Read-Host "Press Enter to close"
