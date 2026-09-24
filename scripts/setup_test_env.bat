@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   ViiB-StemLab: Setting up test environment
echo ===================================================

cd /d "%~dp0\.."

where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Detected 'uv' package manager.
    echo Synchronizing virtual environment with dev dependencies...
    uv sync --extra dev
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] 'uv sync --extra dev' failed.
        exit /b %ERRORLEVEL%
    )
) else (
    echo [INFO] 'uv' not found in PATH, checking Python...
    where python >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Neither 'uv' nor 'python' was found in PATH.
        exit /b 1
    )
    if not exist ".venv\Scripts\python.exe" (
        echo Creating virtual environment at .venv...
        python -m venv .venv
        if %ERRORLEVEL% neq 0 (
            echo [ERROR] Failed to create virtual environment.
            exit /b %ERRORLEVEL%
        )
    )
    echo Installing editable package with [dev] dependencies...
    call .venv\Scripts\python.exe -m pip install -e ".[dev]"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install dependencies.
        exit /b %ERRORLEVEL%
    )
)

echo.
echo ===================================================
echo   Running diagnostic doctor and test suite
echo ===================================================
echo.

if exist ".venv\Scripts\viib-stemlab.exe" (
    call .venv\Scripts\viib-stemlab.exe doctor
) else (
    where uv >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        uv run viib-stemlab doctor
    )
)

echo.
echo Running pytest...
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    uv run pytest
) else (
    call .venv\Scripts\pytest.exe
)

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Some tests failed.
    exit /b %ERRORLEVEL%
)

echo.
echo ===================================================
echo   [SUCCESS] Test environment is ready!
echo ===================================================
echo.
echo To activate the virtual environment in Command Prompt:
echo   call .venv\Scripts\activate.bat
echo.
echo To activate in PowerShell:
echo   .venv\Scripts\Activate.ps1
echo.
