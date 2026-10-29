@echo off
title AttendTrax Enterprise Launcher
color 0b
echo ============================================================
echo   AttendTrax Enterprise - 1-Click Local Demo Launcher
echo   Dual-Engine: Supabase PostgreSQL + Google Sheets Live
echo ============================================================
echo.

echo [1/2] Starting FastAPI Backend on port 8000...
start "AttendTrax Backend" cmd /k "cd /d "%~dp0backend" && .\venv\Scripts\activate && uvicorn main:app --reload --port 8000"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Frontend Web Server on port 5500...
start "AttendTrax Frontend" cmd /k "cd /d "%~dp0frontend" && python -m http.server 5500"

timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo   AttendTrax is LIVE!
echo   Frontend: http://localhost:5500
echo   Backend:  http://127.0.0.1:8000/docs
echo ============================================================
start http://localhost:5500
pause

