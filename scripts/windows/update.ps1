# Install a new version: back up first, then update the parts and the database.
. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $AppDir
Step "1/4 Backup before updating"
& $Py $Manage backup
if ($LASTEXITCODE -ne 0) { Fail "The backup failed, so nothing was updated." }
Step "2/4 Stopping the app"
& (Join-Path $PSScriptRoot "stop.ps1")
Step "3/4 Getting the new version"
if (Test-Path (Join-Path $AppDir ".git")) { git -C $AppDir pull --ff-only } else { Say "Not a Git folder: copy the new files over this folder first, then run UPDATE." }
& $Py -m pip install --quiet -r (Join-Path $AppDir "requirements.txt")
& $Py $Manage setup_database
Step "4/4 Starting again"
schtasks /Run /TN $TaskName | Out-Null
Read-Host "Update finished. Press Enter to close"
