from __future__ import annotations

import json
from pathlib import Path

from conftest import write_test_wav

from viib_stemlab.cli import main
from viib_stemlab.queue.store import QueueStore


def test_cli_queue_add_and_list(tmp_path: Path, capsys) -> None:
    db = tmp_path / "queue.db"
    out = tmp_path / "stems"
    wav = tmp_path / "test_track.wav"
    write_test_wav(wav)

    code = main(
        [
            "queue",
            "add",
            str(wav),
            "--output",
            str(out),
            "--db",
            str(db),
        ]
    )
    assert code == 0
    captured = capsys.readouterr().out
    assert "Added to queue:        1" in captured

    code_list = main(["queue", "list", "--db", str(db)])
    assert code_list == 0
    list_out = capsys.readouterr().out
    assert "test_track.wav" in list_out
    assert "queued" in list_out


def test_cli_queue_list_json(tmp_path: Path, capsys) -> None:
    db = tmp_path / "queue.db"
    out = tmp_path / "stems"
    wav = tmp_path / "track.wav"
    write_test_wav(wav)

    main(["queue", "add", str(wav), "--output", str(out), "--db", str(db)])
    capsys.readouterr()

    code = main(["queue", "list", "--json", "--db", str(db)])
    assert code == 0
    out_json = json.loads(capsys.readouterr().out)
    assert len(out_json) == 1
    assert out_json[0]["status"] == "queued"
    assert "track.wav" in out_json[0]["source_path"]


def test_cli_queue_cancel_and_retry(tmp_path: Path, capsys) -> None:
    db = tmp_path / "queue.db"
    store = QueueStore(db)
    job = store.add_job(tmp_path / "t.wav", tmp_path / "out")

    # Cancel
    code = main(["queue", "cancel", job.id, "--db", str(db)])
    assert code == 0
    assert store.get_job(job.id).status.value == "cancelled"

    # Retry
    code_retry = main(["queue", "retry", job.id, "--db", str(db)])
    assert code_retry == 0
    assert store.get_job(job.id).status.value == "queued"


def test_cli_queue_remove_and_clear(tmp_path: Path, capsys) -> None:
    db = tmp_path / "queue.db"
    store = QueueStore(db)
    j1 = store.add_job(tmp_path / "1.wav", tmp_path / "out")
    j2 = store.add_job(tmp_path / "2.wav", tmp_path / "out")

    store.mark_cancelled(j1.id)

    # Clear terminal jobs
    code_clear = main(["queue", "clear", "--db", str(db)])
    assert code_clear == 0
    assert store.get_job(j1.id) is None
    assert store.get_job(j2.id) is not None

    # Remove single job
    code_remove = main(["queue", "remove", j2.id, "--db", str(db)])
    assert code_remove == 0
    assert store.get_job(j2.id) is None


def test_cli_queue_start_empty(tmp_path: Path, capsys) -> None:
    db = tmp_path / "queue.db"
    code = main(["queue", "start", "--db", str(db)])
    assert code == 0
    assert "Queue is empty" in capsys.readouterr().out
