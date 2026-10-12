"""CLI end-to-end и декоратор измерения времени."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from helpers import TEMPLATE, make_record

from school.cli import main
from school.timing import timed


def write_jsonl(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_cli_import_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_jsonl(tmp_path / "ok.jsonl", [json.dumps(make_record())])
    assert main(["import", str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"accepted": ["sub-1"], "duplicate": [], "errors": []}


def test_cli_import_conflict_and_bad_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_jsonl(
        tmp_path / "mixed.jsonl",
        [
            json.dumps(make_record()),
            "{oops",
            json.dumps(make_record()),
            json.dumps(make_record(text="изменено")),
        ],
    )
    assert main(["import", str(path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["accepted"] == ["sub-1"]
    assert output["duplicate"] == ["sub-1"]
    assert [(e["line"], e["code"]) for e in output["errors"]] == [(2, "invalid_json"), (4, "conflict")]


def test_cli_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["import", str(tmp_path / "nope.jsonl")]) == 2
    assert "io_error" in capsys.readouterr().err


def test_cli_analyze(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = write_jsonl(tmp_path / "s.jsonl", [json.dumps(make_record(code=TEMPLATE))])
    assignments = tmp_path / "a.json"
    assignments.write_text(json.dumps([{"assignment_id": "lab-1", "allowed_template": TEMPLATE}]), encoding="utf-8")

    assert main(["analyze", str(data), "--assignments", str(assignments)]) == 0
    output = json.loads(capsys.readouterr().out)
    by_id = {r["analyzer_id"]: r for r in output["reports"]}
    assert set(by_id) == {"length", "template"}
    assert by_id["template"]["similarity"] == 1.0


def test_cli_rejects_unknown_analyzer_before_work(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assignments = tmp_path / "a.json"
    assignments.write_text("[]", encoding="utf-8")
    # Файла сдач нет, но ошибка конфигурации обнаруживается раньше чтения.
    code = main(["analyze", str(tmp_path / "missing.jsonl"), "--assignments", str(assignments), "--analyzer", "nope"])
    assert code == 2
    assert "unknown_analyzer" in capsys.readouterr().err


def test_timed_preserves_metadata() -> None:
    @timed
    def add(a: int, b: int = 1) -> int:
        """Складывает числа."""
        return a + b

    assert add(2, b=3) == 5
    assert add.__name__ == "add"
    assert add.__doc__ == "Складывает числа."
    assert add.__wrapped__(1) == 2  # type: ignore[attr-defined]


def test_timed_logs_even_on_error(caplog: pytest.LogCaptureFixture) -> None:
    @timed
    def fail() -> None:
        raise ValueError("x")

    with caplog.at_level(logging.DEBUG, logger="school.timing"):
        with pytest.raises(ValueError):
            fail()
    assert "fail" in caplog.text
