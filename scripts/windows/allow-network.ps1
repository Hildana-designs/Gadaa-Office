# Optional: let other computers in the office open the app (port 8443, private networks only).
# Needs "Run as administrator". Not needed while only this computer uses the app.
$ErrorActionPreference = "Stop"
New-NetFirewallRule -DisplayName "GADAA Office (office network only)" -Direction Inbound -Protocol TCP -LocalPort 8443 -Profile Private -Action Allow
Write-Host "Done. Other office computers can open https://$env:COMPUTERNAME:8443"
Read-Host "Press Enter to close"
