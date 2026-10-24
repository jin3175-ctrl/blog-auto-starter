# Aside CLI installer (official steps from docs.aside.com/help/developers, 2026-10-24).
# Downloads the signed installer, checks the publisher signature, then runs it.
# ASCII only on purpose: Windows PowerShell 5.1 misreads UTF-8 files without BOM.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
  if (Get-Command aside -ErrorAction SilentlyContinue) { Write-Host '     Aside CLI already installed'; exit 0 }
  $installer = Join-Path $env:TEMP 'aside-install.ps1'
  $publisher = 'CN=AT YOUR SIDE INC, O=AT YOUR SIDE INC, L=San Francisco, S=California, C=US'
  Invoke-WebRequest -UseBasicParsing -Uri https://releases.aside.com/install.ps1 -OutFile $installer
  $signature = Get-AuthenticodeSignature -LiteralPath $installer
  if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -ne $publisher -or $null -eq $signature.TimeStamperCertificate) {
    throw "Aside CLI installer signature verification failed ($($signature.Status): $($signature.StatusMessage))."
  }
  & $installer
  Write-Host '     Aside CLI OK'
  exit 0
} catch {
  Write-Host ('     [!] Aside CLI: ' + $_.Exception.Message)
  exit 1
}
