"""Центральный сервис анализа.

Обратите внимание: здесь НЕТ ни одного `if analyzer_id == "length"` или
`isinstance(analyzer, TemplateAnalyzer)`. Сервис работает с любым объектом,
удовлетворяющим протоколу Analyzer, который выдаёт реестр.

Сервис также охраняет границу с чужим кодом:
- падение анализатора превращается в AnalyzerError с понятным описанием;
- отчёт проверяется (id, версия, similarity в [0, 1], диапазоны evidence).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .analyzers.base import AnalysisContext, Analyzer
from .analyzers.registry import AnalyzerRegistry
from .errors import AnalyzerError, ConfigurationError, ErrorCode, ErrorDetail, SchoolError
from .lines import split_lines
from .models import AnalysisReport, Submission
from .repository import AssignmentCatalog, SubmissionReader
from .timing import timed


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    reports: tuple[AnalysisReport, ...]
    errors: tuple[ErrorDetail, ...]


class AnalysisService:
    def __init__(
        self,
        registry: AnalyzerRegistry,
        assignments: AssignmentCatalog,
        submissions: SubmissionReader,
    ) -> None:
        self._registry = registry
        self._assignments = assignments
        self._submissions = submissions

    @timed
    def analyze(self, submission: Submission, analyzer_id: str) -> AnalysisReport:
        assignment = self._assignments.get(submission.assignment_id)
        if assignment is None:
            raise ConfigurationError.single(
                ErrorCode.UNKNOWN_ASSIGNMENT,
                "assignment_id",
                f"Задание '{submission.assignment_id}' не найдено",
            )
        analyzer = self._registry.create(analyzer_id)
        context = AnalysisContext(assignment=assignment, submissions=self._submissions)

        try:
            report = analyzer.analyze(submission, context)
        except SchoolError:
            raise
        except Exception as exc:
            # Широкий except здесь оправдан: это граница с кодом анализатора
            # (возможно, внешнего плагина). Его падение не должно ронять систему,
            # а пользователь должен увидеть, КАКОЙ анализатор упал и почему.
            raise AnalyzerError.single(
                ErrorCode.ANALYZER_FAILED, analyzer_id, f"{type(exc).__name__}: {exc}"
            ) from exc

        problems = validate_report(report, submission, analyzer)
        if problems:
            raise AnalyzerError(problems)
        return report

    def analyze_many(self, submission: Submission, analyzer_ids: Iterable[str]) -> AnalysisRun:
        """Запускает несколько анализаторов; ошибка одного не мешает остальным."""
        reports: list[AnalysisReport] = []
        errors: list[ErrorDetail] = []
        for analyzer_id in analyzer_ids:
            try:
                reports.append(self.analyze(submission, analyzer_id))
            except SchoolError as error:
                errors.extend(error.details)
        return AnalysisRun(tuple(reports), tuple(errors))


def validate_report(
    report: object, submission: Submission, analyzer: Analyzer
) -> list[ErrorDetail]:
    """Проверяет, что анализатор соблюдает контракт результата."""
    aid = analyzer.analyzer_id

    def problem(message: str) -> ErrorDetail:
        return ErrorDetail(ErrorCode.INVALID_REPORT, aid, message)

    if not isinstance(report, AnalysisReport):
        return [problem(f"Ожидался AnalysisReport, получено {type(report).__name__}")]

    problems: list[ErrorDetail] = []
    if report.submission_id != submission.submission_id:
        problems.append(problem("submission_id отчёта не совпадает со сдачей"))
    if report.analyzer_id != aid or report.analyzer_version != analyzer.analyzer_version:
        problems.append(problem("analyzer_id/analyzer_version отчёта не совпадают с анализатором"))
    if report.similarity is not None and not 0.0 <= report.similarity <= 1.0:
        problems.append(problem(f"similarity={report.similarity} вне диапазона [0, 1]"))

    line_counts = {"text": len(split_lines(submission.text)), "code": len(split_lines(submission.code))}
    for ev in report.evidence:
        total = line_counts.get(ev.source)
        if total is None:
            problems.append(problem(f"evidence: неизвестный источник '{ev.source}'"))
        elif not 1 <= ev.start_line <= ev.end_line <= total:
            problems.append(
                problem(
                    f"evidence {ev.source}:{ev.start_line}-{ev.end_line} вне диапазона 1..{total}"
                )
            )
    return problems
