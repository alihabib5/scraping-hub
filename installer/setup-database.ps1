# Sets up Scraping Hub's own PostgreSQL on this PC. Run by the setup wizard (as admin).
#
#   - database files:  C:\ProgramData\Scraping Hub\pgdata
#   - Windows service: ScrapingHubDB (starts with Windows), port 5433, this PC only
#   - writes DATABASE_URL (with a random password made here) to C:\ProgramData\Scraping Hub\.env
#
# Safe to run again (an upgrade/repair): an existing database is kept as it is.
# Everything it does and every reply from PostgreSQL goes to logs\setup-database.log.
param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [string]$DataDir = (Join-Path $env:ProgramData "Scraping Hub"),
    [int]$Port = 5433
)
$ErrorActionPreference = "Stop"
$Service = "ScrapingHubDB"
$Bin = Join-Path $InstallDir "pgsql\bin"
$PgData = Join-Path $DataDir "pgdata"
$EnvFile = Join-Path $DataDir ".env"
$Log = Join-Path $DataDir "logs\setup-database.log"

New-Item -ItemType Directory -Force (Split-Path $Log) | Out-Null
Start-Transcript -Path $Log -Append | Out-Null

function Step([string]$Text) { Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Text) }

# Run a program, show its output in the log, return its exit code. Native stderr
# must not become a PowerShell error here (it would under ErrorActionPreference=Stop).
function Run([string]$Exe, [string[]]$Arguments) {
    Step ("> " + (Split-Path $Exe -Leaf) + " " + ($Arguments -join " "))
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object { Write-Host ("    " + $_) }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = "Stop"
    }
}

# What PostgreSQL itself logged, for when the service will not start.
function Show-PostgresLog {
    $dir = Join-Path $PgData "log"
    if (Test-Path $dir) {
        Get-ChildItem $dir -Filter *.log | Sort-Object LastWriteTime | Select-Object -Last 1 | ForEach-Object {
            Step "PostgreSQL log ($($_.Name)):"
            Get-Content $_.FullName -Tail 40 | ForEach-Object { Write-Host ("    " + $_) }
        }
    }
    Step "Windows event log entries for $Service / PostgreSQL:"
    Get-WinEvent -FilterHashtable @{LogName = "Application"; StartTime = (Get-Date).AddMinutes(-10)} -ErrorAction SilentlyContinue |
        Where-Object { $_.ProviderName -match "PostgreSQL|$Service" } | Select-Object -First 10 |
        ForEach-Object { Write-Host ("    " + $_.TimeCreated + " " + $_.Message) }
}

try {
    Step "Scraping Hub database setup. Install dir: $InstallDir. Data dir: $DataDir. Port: $Port."
    Step ("Windows " + [Environment]::OSVersion.Version + ", " + $env:PROCESSOR_ARCHITECTURE +
          $(if ($env:PROCESSOR_ARCHITEW6432) { " (emulated on $env:PROCESSOR_ARCHITEW6432)" } else { "" }) +
          ", running as " + [Security.Principal.WindowsIdentity]::GetCurrent().Name)
    foreach ($exe in "initdb.exe", "pg_ctl.exe", "pg_isready.exe", "createdb.exe", "postgres.exe") {
        if (-not (Test-Path (Join-Path $Bin $exe))) { throw "missing $Bin\$exe (the install is incomplete)" }
    }
    $code = Run (Join-Path $Bin "postgres.exe") @("--version")
    if ($code -ne 0) { throw "postgres.exe cannot run on this PC (exit $code). Is the Visual C++ runtime installed?" }

    if (-not (Test-Path (Join-Path $PgData "PG_VERSION"))) {
        Step "No database yet: creating one"
        New-Item -ItemType Directory -Force $PgData | Out-Null
        # initdb refuses to run with admin rights and re-launches itself with a
        # restricted token (no Administrators group). That restricted process must
        # still be able to write here, so Users get Modify on the folder explicitly
        # rather than relying on what the folder inherited.
        Run "icacls.exe" @($PgData, "/grant", "*S-1-5-32-545:(OI)(CI)M", "/Q") | Out-Null

        $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $password = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
        # The password file must be readable by the restricted initdb process too.
        $pwFile = Join-Path $DataDir "pw.tmp"
        [System.IO.File]::WriteAllText($pwFile, $password, (New-Object System.Text.ASCIIEncoding))
        try {
            $code = Run (Join-Path $Bin "initdb.exe") @("-D", $PgData, "-U", "postgres", "-E", "UTF8", "--locale=C",
                                                        "-A", "scram-sha-256", "--pwfile=$pwFile")
        } finally {
            Remove-Item $pwFile -Force -ErrorAction SilentlyContinue
        }
        if ($code -ne 0 -or -not (Test-Path (Join-Path $PgData "PG_VERSION"))) { throw "initdb failed (exit $code); see its output above" }

        Add-Content (Join-Path $PgData "postgresql.conf") @"

# Scraping Hub
port = $Port
listen_addresses = 'localhost'
logging_collector = on
log_directory = 'log'
"@
        # Only the app, on this PC: the URL is the one thing a user-level process needs.
        # No byte-order mark (Windows PowerShell's utf8 adds one): it would corrupt the first key.
        [System.IO.File]::WriteAllText($EnvFile, "DATABASE_URL=postgresql+psycopg2://postgres:$password@localhost:$Port/scraping-hub`r`n", (New-Object System.Text.UTF8Encoding $false))
        $newCluster = $true
    } else {
        Step "Existing database kept: $PgData"
        $newCluster = $false
    }

    # The service runs as Network Service, which must own its data folder.
    Step "Granting the service account access to the data folder"
    $code = Run "icacls.exe" @($PgData, "/grant", "*S-1-5-20:(OI)(CI)F", "/T", "/Q")
    if ($code -ne 0) { throw "icacls failed (exit $code)" }

    if (-not (Get-Service $Service -ErrorAction SilentlyContinue)) {
        $code = Run (Join-Path $Bin "pg_ctl.exe") @("register", "-N", $Service, "-D", $PgData, "-S", "auto", "-U", "NT AUTHORITY\NetworkService")
        if ($code -ne 0) { throw "registering the $Service service failed (exit $code)" }
    } else {
        Step "Service $Service already registered"
    }

    Step "Starting the $Service service"
    try {
        Start-Service $Service
    } catch {
        Show-PostgresLog
        throw "the $Service service would not start: $($_.Exception.Message)"
    }
    $ready = $false
    foreach ($i in 1..60) {
        $null = Run (Join-Path $Bin "pg_isready.exe") @("-h", "localhost", "-p", $Port, "-q")
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { Show-PostgresLog; throw "the database did not answer on port $Port within 60 s" }

    if ($newCluster) {
        $env:PGPASSWORD = $password
        try {
            $code = Run (Join-Path $Bin "createdb.exe") @("-h", "localhost", "-p", $Port, "-U", "postgres", "scraping-hub")
        } finally {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        }
        if ($code -ne 0) { throw "createdb failed (exit $code)" }
    }
    Step "Database ready on port $Port"
} catch {
    Step ("FAILED: " + $_.Exception.Message)
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
exit 0
