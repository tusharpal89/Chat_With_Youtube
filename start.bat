@echo off
REM ===== ClipMind launcher =====
REM Double-click this file to start ClipMind.
REM It opens the backend and frontend in their own windows,
REM then opens the app in your browser.

cd /d "%~dp0"

echo Starting ClipMind backend (http://localhost:8000) ...
start "ClipMind Backend" cmd /k "venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo Starting ClipMind frontend (http://localhost:5173) ...
start "ClipMind Frontend" cmd /k "cd frontend && npm run dev"

echo Waiting for the servers to warm up ...
timeout /t 10 /nobreak >nul

start "" http://localhost:5173

echo.
echo ================================================================
echo  ClipMind is starting - it will open in your browser shortly.
echo  Keep the two new windows ("ClipMind Backend" / "Frontend") open
echo  while you use the app. Close them to stop ClipMind.
echo ================================================================
echo.
pause
