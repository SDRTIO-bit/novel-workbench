$ErrorActionPreference = "Stop"

$apiDir = Join-Path $PSScriptRoot "..\apps\api"
Set-Location $apiDir
$env:PYTHONPATH = "."
Write-Host "Running backend tests..." -ForegroundColor Cyan
& python -m pytest tests/ -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$webDir = Join-Path $PSScriptRoot "..\apps\web"
Set-Location $webDir
Write-Host "Running frontend tests..." -ForegroundColor Cyan
& npx vitest run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "All tests passed." -ForegroundColor Green
