"""Этап Б: реестр, сервис анализа, ошибки анализаторов, entry points, третий анализатор."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from importlib.metadata import EntryPoint

import pytest
from helpers import PLUGIN_SRC, RAW_EXAMPLE, changed_declaration

from school_lab.analyzers import AnalysisContext, LengthAnalyzer
from school_lab.app import Application, build_application
from school_lab.errors import AnalysisFailure
from school_lab.models import AnalysisReport, Assignment, Evidence, Submission
from school_lab.registry import ENTRY_POINT_GROUP, AnalyzerRegistry, build_registry


class CrashingAnalyzer:
    analyzer_id = "crashing"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        raise KeyError("нет данных")


def own_report(analyzer: object, submission: Submission, context: AnalysisContext) -> AnalysisReport:
    """Корректный отчёт «от имени» данного анализатора — дальше ломаем ровно одно свойство."""
    good = LengthAnalyzer().analyze(submission, context)
    return replace(good, analyzer_id=analyzer.analyzer_id, analyzer_version=analyzer.analyzer_version)  # type: ignore[attr-defined]


class WrongHashAnalyzer:
    analyzer_id = "broken"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return replace(own_report(self, submission, context), submission_hash="incorrect")


class OutOfRangeAnalyzer:
    analyzer_id = "liar"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        report = own_report(self, submission, context)
        finding = replace(report.findings[0], evidence=(Evidence(submission.submission_id, "code", 1, 999),))
        return replace(report, findings=(finding,))


class ImpostorAnalyzer:
    """Возвращает отчёт от имени другого анализатора."""

    analyzer_id = "impostor"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        return LengthAnalyzer().analyze(submission, context)


def accepted_app(*extra: tuple[str, type]) -> Application:
    registry = build_registry()
    for name, factory in extra:
        registry.register(name, factory)
    app = build_application(registry=registry)
    app.submission_service.accept(RAW_EXAMPLE)
    return app


# ---------------------------------------------------------- сервис


@pytest.mark.parametrize("name", ["length", "template", "missing_explanation"])
def test_service_selects_by_registry(name: str, context: AnalysisContext) -> None:
    report = accepted_app().analysis_service.run("sub-001", name, context)
    assert report.analyzer_id == name


def test_analysis_requires_accepted_submission(app: Application, context: AnalysisContext) -> None:
    with pytest.raises(AnalysisFailure) as caught:
        app.analysis_service.run("sub-404", "length", context)
    assert caught.value.code == "not_found"


def test_analysis_requires_matching_context() -> None:
    other = AnalysisContext(Assignment("assignment-99", ""))
    with pytest.raises(AnalysisFailure) as caught:
        accepted_app().analysis_service.run("sub-001", "length", other)
    assert caught.value.code == "context_mismatch"


def test_crashing_analyzer_is_wrapped(context: AnalysisContext) -> None:
    app = accepted_app(("crashing", CrashingAnalyzer))
    before = app.repository.get("sub-001")
    with pytest.raises(AnalysisFailure) as caught:
        app.analysis_service.run("sub-001", "crashing", context)
    assert (caught.value.code, caught.value.field) == ("analyzer_crashed", "crashing")
    assert isinstance(caught.value.__cause__, KeyError)  # исходная причина сохранена
    assert app.repository.get("sub-001") == before  # отказ анализатора не меняет сдачу


@pytest.mark.parametrize(
    ("name", "factory"),
    [("broken", WrongHashAnalyzer), ("liar", OutOfRangeAnalyzer), ("impostor", ImpostorAnalyzer)],
)
def test_bad_report_is_rejected_at_boundary(context: AnalysisContext, name: str, factory: type) -> None:
    app = accepted_app((name, factory))
    with pytest.raises(AnalysisFailure) as caught:
        app.analysis_service.run("sub-001", name, context)
    assert (caught.value.code, caught.value.field) == ("invalid_report", name)


# ---------------------------------------------------------- реестр


def test_unknown_analyzer() -> None:
    with pytest.raises(AnalysisFailure) as caught:
        build_registry().create("nope")
    assert caught.value.code == "unknown_analyzer"


@pytest.mark.parametrize("name", ["length", "", "  "])
def test_register_rejects_duplicate_or_empty(name: str) -> None:
    with pytest.raises(AnalysisFailure):
        build_registry().register(name, LengthAnalyzer)


def test_registration_name_must_match_analyzer_id() -> None:
    registry = AnalyzerRegistry()
    registry.register("other", LengthAnalyzer)
    with pytest.raises(AnalysisFailure) as caught:
        registry.create("other")
    assert caught.value.code == "invalid_registration"


def test_registries_are_independent() -> None:
    first = build_registry()
    first.register("crashing", CrashingAnalyzer)
    assert "crashing" not in build_registry()  # нет общего глобального состояния


def test_late_binding_pitfall() -> None:
    names = ("length", "template")
    # Дефект воспроизводится намеренно, поэтому правило B023 для строки отключено.
    wrong = [lambda: name for name in names]  # noqa: B023
    fixed = [lambda name=name: name for name in names]
    assert [f() for f in wrong] == ["template", "template"]
    assert [f() for f in fixed] == ["length", "template"]


# ---------------------------------------------- entry points (углубление)


def fake_discover(*entries: EntryPoint) -> Callable[[str], list[EntryPoint]]:
    return lambda group: [e for e in entries if e.group == group]


PLUGIN_ENTRY = EntryPoint("declaration", "school_lab_declaration:DeclarationAnalyzer", ENTRY_POINT_GROUP)


def test_entry_point_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(PLUGIN_SRC))
    registry = build_registry()
    assert registry.load_entry_points(discover=fake_discover(PLUGIN_ENTRY)) == ["declaration"]
    assert registry.create("declaration").analyzer_id == "declaration"


def test_entry_point_duplicate_name() -> None:
    entry = EntryPoint("length", "school_lab.analyzers:LengthAnalyzer", ENTRY_POINT_GROUP)
    with pytest.raises(AnalysisFailure) as caught:
        build_registry().load_entry_points(discover=fake_discover(entry))
    assert caught.value.code == "invalid_registration"


def test_entry_point_import_error() -> None:
    entry = EntryPoint("ghost", "no_such_module_xyz:Analyzer", ENTRY_POINT_GROUP)
    with pytest.raises(AnalysisFailure) as caught:
        build_registry().load_entry_points(discover=fake_discover(entry))
    assert caught.value.code == "plugin_error"
    assert isinstance(caught.value.__cause__, ImportError)


def test_entry_point_name_must_match_analyzer_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(PLUGIN_SRC))
    entry = EntryPoint("ai", "school_lab_declaration:DeclarationAnalyzer", ENTRY_POINT_GROUP)
    with pytest.raises(AnalysisFailure) as caught:
        build_registry().load_entry_points(discover=fake_discover(entry))
    assert caught.value.code == "invalid_registration"


# ---------------------------- третий анализатор без изменения сервиса (защита)


def test_declaration_analyzer_without_changing_service(monkeypatch: pytest.MonkeyPatch, context: AnalysisContext) -> None:
    monkeypatch.syspath_prepend(str(PLUGIN_SRC))
    from school_lab_declaration import DeclarationAnalyzer

    registry = build_registry()
    registry.register("declaration", DeclarationAnalyzer)  # единственное изменение — регистрация
    app = build_application(registry=registry)

    app.submission_service.accept(RAW_EXAMPLE)  # used=false
    app.submission_service.accept(
        changed_declaration(used=True, tool="помощник", purpose="тесты", verified_by_student=True) | {"submission_id": "s-ok"}
    )
    app.submission_service.accept(
        changed_declaration(used=True, tool="помощник", purpose="тесты", verified_by_student=False)
        | {"submission_id": "s-unverified"}
    )
    run = app.analysis_service.run
    assert run("sub-001", "declaration", context).review_required is False
    assert run("s-ok", "declaration", context).review_required is False
    unverified = run("s-unverified", "declaration", context)
    assert unverified.review_required is True
    assert "ручная проверка" in unverified.findings[0].explanation


def test_declaration_analyzer_checks_nonempty_itself(
    monkeypatch: pytest.MonkeyPatch, submission: Submission, context: AnalysisContext
) -> None:
    """Сдача, созданная в обход parser: анализатор не полагается слепо на чужую валидацию."""
    monkeypatch.syspath_prepend(str(PLUGIN_SRC))
    from school_lab_declaration import DeclarationAnalyzer

    bypass = replace(submission, ai_declaration=replace(submission.ai_declaration, used=True, tool=" ", purpose=None))
    report = DeclarationAnalyzer().analyze(bypass, context)
    assert report.review_required is True
    assert "не указаны" in report.findings[0].explanation
