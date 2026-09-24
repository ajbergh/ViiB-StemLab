from viib_stemlab.cli import main


def test_doctor_runs_without_demucs(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "ViiB-StemLab" in output
    assert "Auto device:" in output
