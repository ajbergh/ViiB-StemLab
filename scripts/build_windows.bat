@echo off
setlocal DisableDelayedExpansion

rem Keep paths independent of the caller's working directory.
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
exit /b %ERRORLEVEL%

:help
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" -Help
exit /b %ERRORLEVEL%
