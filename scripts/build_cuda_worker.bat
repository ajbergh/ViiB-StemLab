@echo off
setlocal DisableDelayedExpansion
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" -CudaWorker %*
exit /b %ERRORLEVEL%
:help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" -Help
exit /b %ERRORLEVEL%
