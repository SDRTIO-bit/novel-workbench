Write-Host "Starting Novel Workbench..." -ForegroundColor Cyan

$apiDir = Join-Path $PSScriptRoot "..\apps\api"
$webDir = Join-Path $PSScriptRoot "..\apps\web"

$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:apiDir
    $env:PYTHONPATH = "."
    & python -m uvicorn app.main:app --host 127.0.0.1 --port 8766 --reload
}

Write-Host "Backend starting on http://localhost:8766 ..." -ForegroundColor Green

Set-Location $webDir
Write-Host "Frontend starting on http://localhost:8765 ..." -ForegroundColor Green
& npx vite --port 8765

if ($apiJob.State -eq 'Running') {
    Stop-Job $apiJob
    Remove-Job $apiJob
}
