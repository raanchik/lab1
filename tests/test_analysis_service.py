"""Этап Б: центральный сервис, реестр, ошибки анализаторов, третий анализатор."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers import make_submission

from school.analysis import AnalysisService
from school.analyzers import AnalysisContext, AnalyzerRegistry, build_default_registry
from school.errors import AnalyzerError, ConfigurationError, ErrorCode
from school.models import AnalysisReport, Assignment, Evidence, Submission
from school.repository import InMemoryAssignmentCatalog, InMemorySubmissionRepository

PLUGIN_SRC = Path(__file__).resolve().parents[1] / "examples" / "ai_declaration_plugin" / "src"


def make_service(registry: AnalyzerRegistry, assignment: Assignment) -> AnalysisService:
    return AnalysisService(
        registry,
        InMemoryAssignmentCatalog({assignment.assignment_id: assignment}),
        InMemorySubmissionRepository(),
    )


class ExplodingAnalyzer:
    analyzer_id = "boom"
    analyzer_version = "0.0.1"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        raise KeyError("нет данных")


class OutOfRangeAnalyzer:
    analyzer_id = "liar"
    analyzer_version = "0.0.1"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return AnalysisReport(
            submission.submission_id,
            self.analyzer_id,
            self.analyzer_version,
            evidence=(Evidence("code", 1, 999),),
        )


def test_service_picks_analyzer_from_registry(assignment: Assignment) -> None:
    service = make_service(build_default_registry(), assignment)
    report = service.analyze(make_submission(), "template")
    assert report.analyzer_id == "template"


def test_unknown_analyzer(assignment: Assignment) -> None:
    service = make_service(build_default_registry(), assignment)
    with pytest.raises(ConfigurationError) as info:
        service.analyze(make_submission(), "nope")
    assert info.value.code is ErrorCode.UNKNOWN_ANALYZER


def test_unknown_assignment(assignment: Assignment) -> None:
    service = make_service(build_default_registry(), assignment)
    with pytest.raises(ConfigurationError) as info:
        service.analyze(make_submission(assignment_id="lab-99"), "length")
    assert info.value.code is ErrorCode.UNKNOWN_ASSIGNMENT


def test_analyzer_failure_is_wrapped(assignment: Assignment) -> None:
    registry = build_default_registry()
    registry.register("boom", ExplodingAnalyzer)
    service = make_service(registry, assignment)
    with pytest.raises(AnalyzerError) as info:
        service.analyze(make_submission(), "boom")
    detail = info.value.details[0]
    assert (detail.code, detail.field) == (ErrorCode.ANALYZER_FAILED, "boom")
    assert "KeyError" in detail.message
    assert isinstance(info.value.__cause__, KeyError)  # исходная причина сохранена


def test_evidence_out_of_range_is_rejected(assignment: Assignment) -> None:
    registry = build_default_registry()
    registry.register("liar", OutOfRangeAnalyzer)
    service = make_service(registry, assignment)
    with pytest.raises(AnalyzerError) as info:
        service.analyze(make_submission(code="x = 1\n"), "liar")
    assert info.value.code is ErrorCode.INVALID_REPORT
    assert "1-999" in info.value.details[0].message


def test_one_failing_analyzer_does_not_stop_others(assignment: Assignment) -> None:
    registry = build_default_registry()
    registry.register("boom", ExplodingAnalyzer)
    service = make_service(registry, assignment)
    run = service.analyze_many(make_submission(), ["length", "boom", "template"])
    assert [r.analyzer_id for r in run.reports] == ["length", "template"]
    assert [e.field for e in run.errors] == ["boom"]


def test_registry_rejects_duplicate_ids() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError):
        registry.register("length", ExplodingAnalyzer)


def test_each_registry_is_independent() -> None:
    first = build_default_registry()
    first.register("boom", ExplodingAnalyzer)
    assert "boom" not in build_default_registry()  # нет общего глобального состояния


def test_third_analyzer_without_changing_service(
    assignment: Assignment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сценарий защиты: подключаем анализатор AI-декларации, сервис не меняется."""
    monkeypatch.syspath_prepend(str(PLUGIN_SRC))
    from school_ai_declaration import AIDeclarationAnalyzer

    registry = build_default_registry()
    registry.register("ai_declaration", AIDeclarationAnalyzer)
    service = make_service(registry, assignment)

    empty = make_submission(ai_declaration={"used": True, "description": "  "})
    filled = make_submission(submission_id="sub-2", ai_declaration={"used": True, "description": "Подсказки по тестам"})
    unused = make_submission(submission_id="sub-3")

    assert service.analyze(empty, "ai_declaration").score == 0.0
    assert service.analyze(filled, "ai_declaration").score == 1.0
    assert service.analyze(unused, "ai_declaration").score == 1.0
