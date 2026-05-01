# RuleC — start Postgres (pgvector), run migrations, API + frontend (Docker Compose).
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed or not on PATH. Install Docker Desktop, then rerun this script."
}

$envExample = Join-Path $RepoRoot ".env.example"
$envFile = Join-Path $RepoRoot ".env"
if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) {
        Write-Error "Missing .env.example in repo root."
    }
    Copy-Item $envExample $envFile
    Write-Host ""
    Write-Host "Created .env from .env.example" -ForegroundColor Green
    Write-Host "Edit .env and set ANTHROPIC_API_KEY and VOYAGE_API_KEY to use comparisons and catalog ingest." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Building and starting RuleC (db + migrations + backend + frontend)..." -ForegroundColor Cyan
docker compose up --build -d

$healthUrl = "http://127.0.0.1:8000/healthz"
Write-Host ""
Write-Host "Waiting for API at $healthUrl ..." -ForegroundColor Cyan
$deadline = (Get-Date).AddMinutes(5)
$apiReady = $false
while ((-not $apiReady) -and ((Get-Date) -lt $deadline)) {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            $apiReady = $true
            Write-Host "API is up." -ForegroundColor Green
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $apiReady) {
    Write-Host "Timed out waiting for API. Try: docker compose logs -f backend" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Frontend   http://localhost:3000" -ForegroundColor White
Write-Host "  API        http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Health     $healthUrl" -ForegroundColor White
Write-Host ""
Write-Host "Stop with: docker compose down  (from repo root)" -ForegroundColor DarkGray
