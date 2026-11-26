# One-step install for the office computer. Safe to run again.
. (Join-Path $PSScriptRoot "common.ps1")

Write-Host "GADAA Office - install" -ForegroundColor Green
Say "App folder:  $AppDir"
Say "Data folder: $DataDir"

Step "1/6 Checking Python"
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
$basePy = $null
if ($pyLauncher) {
    foreach ($v in "3.13", "3.12", "3.11") {
        & py "-$v" -c "print(1)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $basePy = @("py", "-$v"); break }
    }
}
if (-not $basePy) {
    Say "Python is not installed. Installing Python 3.12 (free, from Microsoft's winget)..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { Fail "Please install Python 3.12 from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run INSTALL again." }
    winget install --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    $basePy = @("py", "-3.12")
}
Say "Using $($basePy -join ' ')"

Step "2/6 Preparing the app's own Python folder"
if (-not (Test-Path $Py)) { & $basePy[0] $basePy[1] -m venv $Venv }
& $Py -m pip install --quiet --upgrade pip
& $Py -m pip install --quiet -r (Join-Path $AppDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "Could not install the app's parts. Check the internet connection and run INSTALL again." }

Step "3/6 Settings file and keys"
[Environment]::SetEnvironmentVariable("GADAA_DATA_DIR", $DataDir, "User")
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
& $Py -m gadaa.bootstrap
Push-Location $AppDir
try {
    Step "4/6 Database"
    Invoke-Manage setup_database

    Step "5/6 First login"
    $count = & $Py $Manage shell --no-imports -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.count())"
    if ([int]$count -eq 0) {
        $name = Read-Host "Choose your username (for example matyas)"
        Invoke-Manage add_user $name --role Admin
    } else { Say "Logins already exist." }
} finally { Pop-Location }

Step "6/6 Start automatically when you log in to Windows"
$start = Join-Path $AppDir "scripts\windows\start.ps1"
$action = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`""
schtasks /Create /F /SC ONLOGON /TN $TaskName /TR $action /RL LIMITED | Out-Null
Say "Done: the app starts by itself after every restart and login."

Write-Host ""
Write-Host "IMPORTANT: copy this file to a USB stick and keep it somewhere safe:" -ForegroundColor Yellow
Write-Host "   $DataDir\gadaa.env" -ForegroundColor Yellow
Write-Host "Without it, backups and passport numbers cannot be read." -ForegroundColor Yellow
Write-Host ""
schtasks /Run /TN $TaskName | Out-Null
Start-Sleep -Seconds 6
Start-Process "https://localhost:8443"
Say "The browser will warn about the certificate the first time. That is expected on an office network: choose 'Advanced' then 'Continue'."
Read-Host "Install finished. Press Enter to close"
