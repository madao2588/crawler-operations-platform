@echo off
setlocal
cd /d "%~dp0"
title New Drug Intelligence Platform

if not exist "%~dp0_system\start-system.ps1" (
  echo Required system files are missing. Extract the complete ZIP before starting.
  pause >nul
  exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0_system\start-system.ps1"
set "START_EXIT_CODE=%ERRORLEVEL%"

if not "%START_EXIT_CODE%"=="0" (
  echo.
  echo Startup failed. The exact error is shown above.
  echo Press any key to close this window after recording the error.
  pause >nul
  exit /b %START_EXIT_CODE%
)

echo.
echo The system is running. This window will close automatically.
powershell.exe -NoLogo -NoProfile -Command "Start-Sleep -Seconds 3"
exit /b 0
