@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   ViiB-StemLab: Setting up CUDA + Demucs Environment
echo ===================================================

cd /d "%~dp0\.."

where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Detected 'uv'.
    echo Step 1/2: Installing dependencies with dev and demucs extras...
    uv sync --extra dev --extra demucs
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] 'uv sync' failed.
        exit /b %ERRORLEVEL%
    )

    echo Step 2/2: Ensuring CUDA 12.4 PyTorch wheels are installed...
    uv pip install --reinstall "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu124
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install CUDA torch wheels.
        exit /b %ERRORLEVEL%
    )
) else (
    echo [INFO] Using pip in .venv...
    if not exist ".venv\Scripts\python.exe" (
        python -m venv .venv
    )
    call .venv\Scripts\python.exe -m pip install -e ".[dev,demucs]"
    call .venv\Scripts\python.exe -m pip install --force-reinstall "torch==2.6.0" "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu124
)

echo.
echo ===================================================
echo   Verifying CUDA runtime with doctor
echo ===================================================
echo.
call .venv\Scripts\viib-stemlab.exe doctor

echo.
echo Running pytest...
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    uv run pytest
) else (
    call .venv\Scripts\pytest.exe
)

echo.
echo ===================================================
echo   [SUCCESS] CUDA and Demucs setup complete!
echo ===================================================
