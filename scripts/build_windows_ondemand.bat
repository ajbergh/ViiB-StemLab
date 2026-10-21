@echo off
setlocal DisableDelayedExpansion
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help
call "%~dp0build_windows.bat" -Installer OnDemand %*
exit /b %ERRORLEVEL%
:help
call "%~dp0build_windows.bat" --help
exit /b %ERRORLEVEL%
