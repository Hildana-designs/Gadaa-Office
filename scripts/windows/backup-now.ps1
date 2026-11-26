. (Join-Path $PSScriptRoot "common.ps1")
Set-Location $AppDir
& $Py $Manage backup
Read-Host "Press Enter to close"
