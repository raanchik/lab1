"""Интеграционные тесты: CLI, декоратор времени, итоговый сквозной сценарий."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from helpers import DATA_DIR, PUBLIC_SUBMISSIONS, TEMPLATE

from school_lab.analyzers import AnalysisContext
from school_lab.app import build_application
from school_lab.cli import main
from school_lab.models import Assignment
from school_lab.services import import_source
from school_lab.sources import InMemorySource
from school_lab.timing import timed

ASSIGNMENTS = str(DATA_DIR / "assignments.json")


def test_cli_import_success(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["import", str(DATA_DIR / "submissions.jsonl")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["accepted"]) == 12 and out["duplicate"] == [] and out["errors"] == []


def test_cli_import_conflict(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["import", str(DATA_DIR / "demo_mixed.jsonl")]) == 1
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["accepted"] == ["sub-001", "sub-002"]
    assert out["duplicate"] == ["sub-001"]
    assert [(e["line_no"], e["code"]) for e in out["errors"]] == [(2, "invalid_json"), (4, "conflict"), (5, "schema_error")]
    assert captured.err == ""  # stdout — результат, stderr — пусто


def test_cli_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["import", str(tmp_path / "nope.jsonl")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "source_unavailable"


def test_cli_analyze(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(DATA_DIR / "submissions.jsonl"), "--assignments", ASSIGNMENTS,
                 "--analyzer", "length", "--analyzer", "template"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["reports"]) == 24 and out["analysis_errors"] == []


def test_cli_unknown_analyzer_detected_before_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["analyze", str(tmp_path / "missing.jsonl"), "--assignments", ASSIGNMENTS, "--analyzer", "nope"])
    assert code == 2
    assert json.loads(capsys.readouterr().err)["code"] == "unknown_analyzer"


def test_cli_unknown_assignment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assignments = tmp_path / "a.json"
    assignments.write_text("[]", encoding="utf-8")
    code = main(["analyze", str(DATA_DIR / "submissions.jsonl"), "--assignments", str(assignments)])
    assert code == 1
    errors = json.loads(capsys.readouterr().out)["analysis_errors"]
    assert {e["code"] for e in errors} == {"unknown_assignment"}


# --------------------------------------------------------------- @timed


def test_timed_preserves_metadata() -> None:
    @timed
    def count(text: str) -> int:
        """Подсчёт строк."""
        return len(text.splitlines())

    assert count("a\nb\n") == 2
    assert count.__name__ == "count"
    assert count.__doc__ == "Подсчёт строк."
    assert count.__wrapped__("a\n") == 1  # type: ignore[attr-defined]


def test_timed_measures_even_on_exception(caplog: pytest.LogCaptureFixture) -> None:
    @timed
    def fail() -> None:
        raise ValueError("x")

    with caplog.at_level(logging.DEBUG, logger="school_lab.timing"), pytest.raises(ValueError):
        fail()
    assert "fail" in caplog.text and "duration_ms" in caplog.text


# ----------------------------------------------------- сквозной сценарий


def test_end_to_end_lab1() -> None:
    app = build_application()
    context = AnalysisContext(Assignment("assignment-01", TEMPLATE, ("Наличие функции solve",)))
    first = import_source(InMemorySource(PUBLIC_SUBMISSIONS), app.submission_service)
    second = import_source(InMemorySource(PUBLIC_SUBMISSIONS), app.submission_service)
    assert len(first.accepted) == 12 and not first.errors
    assert len(second.duplicate) == 12 and not second.accepted and not second.errors

    reports = 0
    for submission_id in first.accepted:
        original = app.repository.get(submission_id)
        assert original is not None
        for name in ("length", "template"):
            app.analysis_service.run(submission_id, name, context)
            assert app.repository.get(submission_id) == original
            reports += 1
    assert reports == 24
