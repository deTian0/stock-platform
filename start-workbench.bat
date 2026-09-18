@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing .venv\Scripts\python.exe
  echo Create the venv and install deps first.
  pause
  exit /b 1
)

rem Load repo-root .env (workbench does not read dotenv). Skip blanks and # comments.
if exist ".env" (
  echo [INFO] Loading .env
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

rem Free port 3018 if already listening
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":3018 .*LISTENING"') do (
  echo [INFO] Freeing port 3018 PID %%p
  taskkill /F /PID %%p >nul 2>&1
)

echo [INFO] PRESET=%STOCK_PLATFORM_PROVIDER_PRESET%
echo [INFO] BRIEF_FALLBACK=%STOCK_PLATFORM_BRIEF_FALLBACK%
echo [INFO] Starting Workbench http://127.0.0.1:3018/
echo [INFO] Press Ctrl+C to stop
echo.

".venv\Scripts\python.exe" -m stock_platform_workbench
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo [ERROR] Exit code %EC%
  pause
)
exit /b %EC%