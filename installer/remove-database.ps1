# Stops and removes the ScrapingHubDB service. Run by the uninstaller (as admin).
# The database files in C:\ProgramData\Scraping Hub are kept unless -DeleteData:
# reinstalling then picks up every past run and bid.
param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [switch]$DeleteData,
    [string]$DataDir = (Join-Path $env:ProgramData "Scraping Hub")
)
$Service = "ScrapingHubDB"
if (Get-Service $Service -ErrorAction SilentlyContinue) {
    Stop-Service $Service -Force -ErrorAction SilentlyContinue
    & (Join-Path $InstallDir "pgsql\bin\pg_ctl.exe") unregister -N $Service
}
if ($DeleteData -and (Test-Path $DataDir)) {
    Remove-Item -Recurse -Force $DataDir
}
