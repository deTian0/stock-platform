@echo off
rem ---------------------------------------------------------------------------
rem WorkBuddy mode (double-click): refresh the westock cache, then run daily.
rem
rem   Step 1  stock-platform-workbuddy-bridge  -> westock CLI -> JSON cache
rem   Step 2  stock-platform-daily             -> workbuddy provider reads it
rem
rem Defaults: dataset=daily, limit=120, symbols from the engine market.db
rem (top 50 by recent amount). Edit SYMBOLS below or pass args to override:
rem
rem   start-workbuddy.bat sh600519,sz000001 daily,realtime
rem
rem Requires the westock CLI. If it is missing, install it once with:
rem   node "%USERPROFILE%\.workbuddy\plugins\cache\cb_teams_marketplace\finance-data\1.6.0\skills\westock-data\scripts\setup.cjs" -d "%USERPROFILE%\.local\bin" -y
rem ---------------------------------------------------------------------------
setlocal EnableExtensions
cd /d "%~dp0"

rem Args (positional): %1 = symbols (comma-separated, optional), %2 = datasets.
set "WB_SYMBOLS=%~1"
set "WB_DATASETS=%~2"
if "%WB_DATASETS%"=="" set "WB_DATASETS=daily"

set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"

echo [INFO] WorkBuddy mode: symbols="%WB_SYMBOLS%" datasets="%WB_DATASETS%"
echo.

%PS% -NoProfile -ExecutionPolicy Bypass -File "scripts\ops\Invoke-WorkbuddyBridge.ps1" -Datasets "%WB_DATASETS%" -Symbols "%WB_SYMBOLS%" %3 %4 %5
set "EC=%ERRORLEVEL%"

echo.
if not "%EC%"=="0" (
  echo [ERROR] WorkBuddy mode exited %EC%
) else (
  echo [OK] WorkBuddy mode finished.
)
pause
exit /b %EC%
