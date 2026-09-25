"""Native OS file and folder picker dialogs for ViiB-StemLab UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def pick_directory(
    title: str = "Select Audio Folder",
    initial_dir: str | None = None,
) -> tuple[str | None, str]:
    """Open a native OS directory picker dialog.

    Returns:
        tuple of (path_or_none, status) where status is "ok", "cancelled", or "unsupported".
    """
    # 1. Try Tkinter (cross-platform: Windows, macOS, Linux with display)
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        init_dir = str(initial_dir) if initial_dir and Path(initial_dir).is_dir() else None
        folder = filedialog.askdirectory(title=title, initialdir=init_dir)
        root.destroy()
        if folder:
            return os.path.normpath(folder), "ok"
        return None, "cancelled"
    except Exception:
        pass

    # 2. Windows fallback via PowerShell if Tkinter is missing or fails
    if sys.platform == "win32":
        try:
            import subprocess

            init_dir_arg = f'$f.SelectedPath = "{initial_dir}"; ' if initial_dir and Path(initial_dir).is_dir() else ""
            script = (
                '[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; '
                '$f = New-Object System.Windows.Forms.FolderBrowserDialog; '
                f'$f.Description = "{title}"; '
                + init_dir_arg
                + 'if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }'
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=120,
            )
            chosen = res.stdout.strip()
            if chosen and Path(chosen).is_dir():
                return os.path.normpath(chosen), "ok"
            if res.returncode == 0:
                return None, "cancelled"
        except Exception:
            pass

    return None, "unsupported"


def pick_files(
    title: str = "Select Audio Files",
    initial_dir: str | None = None,
) -> tuple[list[str], str]:
    """Open a native OS file picker dialog for audio files.

    Returns:
        tuple of (paths_list, status) where status is "ok", "cancelled", or "unsupported".
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        init_dir = str(initial_dir) if initial_dir and Path(initial_dir).is_dir() else None
        filetypes = [
            ("Audio files", "*.wav;*.flac;*.mp3;*.ogg;*.m4a;*.opus;*.aiff;*.aif"),
            ("All files", "*.*"),
        ]
        files = filedialog.askopenfilenames(
            title=title,
            initialdir=init_dir,
            filetypes=filetypes,
        )
        root.destroy()
        if files:
            return [os.path.normpath(f) for f in files if f], "ok"
        return [], "cancelled"
    except Exception:
        pass

    return [], "unsupported"
