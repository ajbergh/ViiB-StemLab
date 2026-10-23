"""Exercise Windows runtime cleanup with actual exclusive file handles."""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows file-sharing semantics")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_windows.ps1"


def run_helper(root: Path, body: str):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    assert shell
    setup = f"""
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath('{root.as_posix()}')
$buildRoot = Join-Path $repoRoot 'build'
$managedDirectories = @((Join-Path $buildRoot 'runtime'))
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile('{SCRIPT.as_posix()}', [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw $errors[0] }}
$names = @('Assert-ManagedDirectory', 'Remove-GeneratedDirectory', 'Assert-NoGeneratedRuntimeProcess')
foreach ($definition in $ast.FindAll({{param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}}, $false)) {{
    if ($definition.Name -in $names) {{ Invoke-Expression $definition.Extent.Text }}
}}
"""
    return subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", setup + body],
                          capture_output=True, text=True, timeout=20)


def exclusive_handle(path: Path):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel, handle


def test_cleanup_retries_a_real_file_lock(tmp_path):
    root = tmp_path / "workspace"
    runtime = root / "build/runtime"
    runtime.mkdir(parents=True)
    locked = runtime / "worker.dll"
    locked.write_bytes(b"locked runtime")
    kernel, handle = exclusive_handle(locked)
    timer = threading.Timer(3, lambda: kernel.CloseHandle(handle))
    timer.start()
    try:
        result = run_helper(root, "Remove-GeneratedDirectory $managedDirectories[0]")
    finally:
        timer.join()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Waiting for Windows" in result.stdout
    assert not runtime.exists()


def test_persistent_lock_has_bounded_actionable_failure(tmp_path):
    root = tmp_path / "workspace"
    runtime = root / "build/runtime"
    runtime.mkdir(parents=True)
    locked = runtime / "worker.dll"
    locked.write_bytes(b"locked runtime")
    kernel, handle = exclusive_handle(locked)
    try:
        result = run_helper(root, "function Start-Sleep { param($Seconds) }\nRemove-GeneratedDirectory $managedDirectories[0]")
    finally:
        kernel.CloseHandle(handle)
    assert result.returncode != 0
    assert "after 6 attempts" in result.stderr
    assert "Close any backend" in result.stderr
    assert result.stdout.count("Waiting for Windows") == 5
    assert locked.is_file()


def test_unmanaged_directory_is_never_deleted(tmp_path):
    root = tmp_path / "workspace"
    unmanaged = root / "outside"
    unmanaged.mkdir(parents=True)
    result = run_helper(root, "Remove-GeneratedDirectory (Join-Path $repoRoot 'outside')")
    assert result.returncode != 0
    assert "Refusing to modify" in result.stderr
    assert unmanaged.is_dir()


def test_standalone_backend_in_staging_blocks_build(tmp_path):
    root = tmp_path / "workspace"
    result = run_helper(root, """
function Get-Process { param($Name, $ErrorAction) [pscustomobject]@{Id=123; Path=(Join-Path $managedDirectories[0] 'stemlab-backend.exe')} }
Assert-NoGeneratedRuntimeProcess
""")
    assert result.returncode != 0
    assert "PID 123" in result.stderr
    assert "standalone StemLab backend" in result.stderr
