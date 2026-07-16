@echo off
chcp 65001 >nul
title Novel Workbench

echo ========================================
echo   Novel Workbench - Starting...
echo ========================================

set ROOT=%~dp0

:: Backend
cd /d "%ROOT%apps\api"
if not defined DATA_DIR set DATA_DIR=%ROOT%data
echo [backend] DATA_DIR=%DATA_DIR%
start "Novel Workbench - API" cmd /c "cd /d "%ROOT%apps\api" && set DATA_DIR=%ROOT%data && python -m uvicorn app.main:app --host 127.0.0.1 --port 8766 --reload"
echo [backend] Starting on http://localhost:8766 ...

:: Frontend
cd /d "%ROOT%apps\web"
start "Novel Workbench - Web" cmd /c "cd /d "%ROOT%apps\web" && npm run dev"
echo [frontend] Starting on http://localhost:8765 ...

echo.
echo All started. Close both terminal windows to stop.
echo Press any key to open http://localhost:8765 ...
pause >nul
start http://localhost:8765
