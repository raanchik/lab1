"""Этап Б: контракт анализаторов, отчёт, LengthAnalyzer, TemplateAnalyzer (+ упражнения 3, 4, 6, 7)."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime

import pytest
from helpers import PUBLIC_SUBMISSIONS, changed

from school_lab.analyzers import (
    AnalysisContext,
    Analyzer,
    LengthAnalyzer,
    MissingExplanationAnalyzer,
    TemplateAnalyzer,
    make_report,
    nonempty_line_numbers,
    template_ranges,
    to_ranges,
    validate_report,
)
from school_lab.errors import AnalysisFailure
from school_lab.models import AnalysisReport, Assignment, Evidence, Finding, Submission
from school_lab.parsing import parse_submission

ANALYZERS = [LengthAnalyzer, TemplateAnalyzer, MissingExplanationAnalyzer]


@pytest.fixture(params=ANALYZERS, ids=lambda cls: cls.__name__)
def analyzer(request: pytest.FixtureRequest) -> Analyzer:
    instance: Analyzer = request.param()
    return instance


# ------------------------------------------------------ общий контракт


@pytest.mark.parametrize("index", range(len(PUBLIC_SUBMISSIONS)))
def test_analyzer_contract_on_corpus(analyzer: Analyzer, context: AnalysisContext, index: int) -> None:
    value = parse_submission(PUBLIC_SUBMISSIONS[index])
    before = asdict(value)

    first = analyzer.analyze(value, context)
    second = analyzer.analyze(value, context)

    validate_report(first, value, context)  # в т. ч. границы evidence
    assert first.analyzer_id == analyzer.analyzer_id
    assert first.analyzer_version == analyzer.analyzer_version
    assert all(f.explanation.strip() for f in first.findings)
    assert first.findings == second.findings  # смысловой результат повторяем
    assert first.report_id != second.report_id  # а запуск — нет
    assert asdict(value) == before  # исходная сдача не изменилась


def test_reproducible_report_with_injected_clock_and_id(submission: Submission, context: AnalysisContext) -> None:
    fixed = datetime(2026, 9, 1, tzinfo=UTC)
    finding = Finding("rubric_feedback", None, (), "x")

    def make() -> AnalysisReport:
        return make_report(
            submission, context, "length", "1.0", (finding,), id_factory=lambda: "r-1", clock=lambda: fixed
        )

    assert make() == make()


# ------------------------------------------------------ LengthAnalyzer


def test_nonempty_line_numbers() -> None:
    assert nonempty_line_numbers("\n a \n\n b\n") == (2, 4)
    assert to_ranges((1, 2, 3, 7, 8, 10)) == ((1, 3), (7, 8), (10, 10))


def test_length_analyzer(context: AnalysisContext) -> None:
    value = parse_submission(changed(text="a\n\nb", code="x = 1\ny = 2\n\n\nz = 3\n"))
    report = LengthAnalyzer().analyze(value, context)
    finding = report.findings[0]
    assert finding.kind == "rubric_feedback" and finding.score is None
    assert "text=2, code=3" in finding.explanation
    assert [(e.field, e.start_line, e.end_line) for e in finding.evidence] == [
        ("text", 1, 1), ("text", 3, 3), ("code", 1, 2), ("code", 5, 5),
    ]


# ---------------------------------------------------- TemplateAnalyzer


def test_template_ranges_basic() -> None:
    assert template_ranges("a\nb\na\nb\n", "a\nb\n") == ((1, 2), (3, 4))
    assert template_ranges("a\n", " \n") == ()


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("import os\nimport sys\nx = 1\n", ((1, 2),)),  # точное совпадение
        ("import os \nimport sys\nx = 1\n", ()),  # пробел в конце строки — уже не совпадение
        ("import os\nimport sys\n\nimport os\nimport sys\n", ((1, 2), (4, 5))),  # два совпадения
        ("x = 1\n", ()),  # нет совпадений
        ("\n\n# c\nimport os\nimport sys\n", ((4, 5),)),  # номера по исходнику
        ("import os\nx = 1\nimport sys\n", ()),  # строки шаблона не подряд
    ],
    ids=["exact", "space", "twice", "none", "offset", "split"],
)
def test_two_line_template(code: str, expected: tuple[tuple[int, int], ...]) -> None:
    """Упражнение 4."""
    assignment = Assignment("assignment-01", "import os\nimport sys\n")
    context = AnalysisContext(assignment)
    value = parse_submission(changed(code=code))
    report = TemplateAnalyzer().analyze(value, context)
    finding = report.findings[0]
    assert finding.kind == "similarity"
    assert tuple((e.start_line, e.end_line) for e in finding.evidence) == expected
    assert ("допустимое совпадение" in finding.explanation) == bool(expected)


def test_template_on_corpus_points_to_line_1(submission: Submission, context: AnalysisContext) -> None:
    report = TemplateAnalyzer().analyze(submission, context)
    assert report.findings[0].evidence[0].start_line == 1


def test_template_rejects_other_assignment(submission: Submission) -> None:
    other = AnalysisContext(Assignment("assignment-99", "x\n"))
    with pytest.raises(AnalysisFailure) as caught:
        TemplateAnalyzer().analyze(submission, other)
    assert caught.value.code == "context_mismatch"


# --------------------------------------------- упражнение 3


def test_missing_explanation(context: AnalysisContext) -> None:
    missing = parse_submission(changed(text="  ", code="print(1)\n"))
    present = parse_submission(changed(text="Пояснение", code="print(1)\n"))
    a = MissingExplanationAnalyzer().analyze(missing, context)
    b = MissingExplanationAnalyzer().analyze(present, context)
    assert a.review_required and not b.review_required
    assert a.findings[0].score is None


# ------------------------------------- упражнение 6: проверка отчёта


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), 1.5, -0.1, "0.5"], ids=repr)
def test_invalid_score_rejected(submission: Submission, context: AnalysisContext, score: object) -> None:
    good = LengthAnalyzer().analyze(submission, context)
    bad = replace(good, findings=(replace(good.findings[0], score=score),))  # type: ignore[arg-type]
    with pytest.raises(AnalysisFailure):
        validate_report(bad, submission, context)


@pytest.mark.parametrize(
    "evidence",
    [
        Evidence("sub-001", "code", 0, 1),  # строка 0
        Evidence("sub-001", "code", 1, 999),  # за концом
        Evidence("sub-001", "code", 3, 2),  # start > end
        Evidence("sub-001", "notes", 1, 1),  # type: ignore[arg-type]  # нет такого поля
        Evidence("sub-999", "code", 1, 1),  # чужая сдача
        Evidence("sub-001", "code", True, 1),  # bool вместо int
    ],
    ids=["zero", "past-end", "reversed", "unknown-field", "other-submission", "bool"],
)
def test_invalid_evidence_rejected(submission: Submission, context: AnalysisContext, evidence: Evidence) -> None:
    good = LengthAnalyzer().analyze(submission, context)
    bad = replace(good, findings=(replace(good.findings[0], evidence=(evidence,)),))
    with pytest.raises(AnalysisFailure):
        validate_report(bad, submission, context)


@pytest.mark.parametrize(
    "change",
    [
        {"submission_hash": "incorrect"},
        {"config_hash": "other"},
        {"report_id": ""},
        {"created_at": "2026-09-01T10:00:00"},
        {"review_required": "no"},
    ],
    ids=["hash", "config", "report-id", "naive-time", "review"],
)
def test_invalid_report_fields(submission: Submission, context: AnalysisContext, change: dict[str, object]) -> None:
    good = LengthAnalyzer().analyze(submission, context)
    with pytest.raises(AnalysisFailure):
        validate_report(replace(good, **change), submission, context)  # type: ignore[arg-type]


def test_empty_explanation_and_unknown_kind(submission: Submission, context: AnalysisContext) -> None:
    good = LengthAnalyzer().analyze(submission, context)
    for finding in (replace(good.findings[0], explanation=" "), replace(good.findings[0], kind="verdict")):
        with pytest.raises(AnalysisFailure):
            validate_report(replace(good, findings=(finding,)), submission, context)  # type: ignore[arg-type]


# ------------------------------------------- упражнение 7: config_hash


def test_config_hash_changes_with_configuration(assignment: Assignment, submission: Submission) -> None:
    base = AnalysisContext(assignment)
    variants = [
        replace(base, config_version="2"),
        replace(base, mode="stub"),
        AnalysisContext(replace(assignment, allowed_template="def solve(values):\n")),
    ]
    old_report = LengthAnalyzer().analyze(submission, base)
    for ctx in variants:
        assert ctx.config_hash() != base.config_hash()
        with pytest.raises(AnalysisFailure):  # старый отчёт — не результат новой конфигурации
            validate_report(old_report, submission, ctx)
