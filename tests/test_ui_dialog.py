from __future__ import annotations

import tkinter as tk
from tkinter import filedialog as tk_fd
from unittest.mock import MagicMock

from viib_stemlab.ui.dialog import pick_directory, pick_files


def test_pick_directory_tkinter_success(monkeypatch) -> None:
    mock_tk = MagicMock()
    monkeypatch.setattr(tk, "Tk", mock_tk)
    monkeypatch.setattr(tk_fd, "askdirectory", lambda **kwargs: "C:/Music/Tracks")

    folder, status = pick_directory(title="Select Folder")
    assert status == "ok"
    assert "Tracks" in folder


def test_pick_directory_tkinter_cancelled(monkeypatch) -> None:
    mock_tk = MagicMock()
    monkeypatch.setattr(tk, "Tk", mock_tk)
    monkeypatch.setattr(tk_fd, "askdirectory", lambda **kwargs: "")

    folder, status = pick_directory()
    assert folder is None
    assert status == "cancelled"


def test_pick_directory_unsupported_when_all_fail(monkeypatch) -> None:
    def raise_err(*args, **kwargs):
        raise RuntimeError("No display available")

    monkeypatch.setattr("tkinter.Tk", raise_err)
    monkeypatch.setattr("sys.platform", "linux")

    folder, status = pick_directory()
    assert folder is None
    assert status == "unsupported"


def test_pick_files_tkinter_success(monkeypatch) -> None:
    mock_tk = MagicMock()
    monkeypatch.setattr(tk, "Tk", mock_tk)
    monkeypatch.setattr(tk_fd, "askopenfilenames", lambda **kwargs: ("C:/Music/t1.wav", "C:/Music/t2.mp3"))

    files, status = pick_files(title="Select Tracks")
    assert status == "ok"
    assert len(files) == 2


def test_pick_files_tkinter_cancelled(monkeypatch) -> None:
    mock_tk = MagicMock()
    monkeypatch.setattr(tk, "Tk", mock_tk)
    monkeypatch.setattr(tk_fd, "askopenfilenames", lambda **kwargs: ())

    files, status = pick_files()
    assert files == []
    assert status == "cancelled"
