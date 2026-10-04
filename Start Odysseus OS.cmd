@echo off
rem Double-click to start Odysseus in its own window and open http://localhost:7000/os.
rem Starting it from here (not from inside another tool's background shell) keeps it alive when memory runs low.
rem Extra arguments are passed on, e.g.  "Start Odysseus OS.cmd" -Port 7001  (see launch-windows.ps1 -Quick).
rem launch-windows.ps1 explains any problem itself and waits for Enter before this window closes.
setlocal
title Odysseus
where powershell >nul 2>nul
if errorlevel 1 (
  echo Windows PowerShell was not found, so Odysseus cannot be started from here.
  pause
  exit /b 1
)
pushd "%~dp0" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-windows.ps1" -Quick %*
set "EXITCODE=%ERRORLEVEL%"
popd >nul
exit /b %EXITCODE%
