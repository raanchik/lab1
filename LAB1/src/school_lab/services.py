"""Сервисы: приём сдач, импорт из источника, запуск анализа.

Сервисы получают зависимости через конструктор (композиция) и не знают
ни о файлах, ни о stdin, ни о HTTP. Их можно вызывать из CLI, из тестов
и в будущем — из HTTP-адаптера.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Literal

from .analyzers import AnalysisContext, validate_report
from .errors import AnalysisFailure, SubmissionError
from .hashing import submission_hash
from .models import AnalysisReport
from .parsing import parse_submission
from .registry import AnalyzerRegistry
from .repositories import SubmissionRepository
from .sources import SubmissionSource
from .timing import timed

logger = logging.getLogger(__name__)


# -------------------------------------------------------------- приём


@dataclass(frozen=True, slots=True)
class Acceptance:
    status: Literal["accepted", "duplicate"]
    submission_id: str
    content_hash: str


class SubmissionService:
    """Идемпотентный приём:
    новый id                   -> accepted;
    тот же id и тот же хеш     -> duplicate (ничего не меняется);
    тот же id и другой хеш     -> SubmissionError("conflict"), исходная запись не трогается.
    Новая версия работы — это новый submission_id.
    """

    def __init__(self, repository: SubmissionRepository) -> None:
        self.repository = repository

    def accept(self, raw: object) -> Acceptance:
        value = parse_submission(raw)  # сначала полная проверка, потом изменение состояния
        digest = submission_hash(value)
        previous = self.repository.get(value.submission_id)
        if previous is not None:
            if submission_hash(previous) != digest:
                raise SubmissionError(
                    "conflict", "submission_id", "Идентификатор занят другой версией; для новой версии нужен новый ID"
                )
            return Acceptance("duplicate", value.submission_id, digest)
        self.repository.add(value)
        return Acceptance("accepted", value.submission_id, digest)


# -------------------------------------------------------------- импорт


@dataclass
class ImportSummary:
    # default_factory: у каждого отчёта свои списки (общий mutable default — классический дефект)
    accepted: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def import_source(source: SubmissionSource, service: SubmissionService) -> ImportSummary:
    """Импорт с частичным успехом: плохая запись попадает в errors, остальные обрабатываются.

    Атомарность — на уровне ОДНОЙ сдачи: записи, принятые до ошибки, остаются.
    Перехватывается только SubmissionError; любой другой Exception — дефект кода,
    его нельзя тихо превратить в «пропущенную строку».
    """
    summary = ImportSummary()
    with source.open() as records:
        for record in records:
            if record.error is not None:
                summary.errors.append({"line_no": record.line_no, **record.error.to_dict()})
                continue
            try:
                result = service.accept(record.raw)
            except SubmissionError as exc:
                summary.errors.append({"line_no": record.line_no, **exc.to_dict()})
            else:
                target = summary.accepted if result.status == "accepted" else summary.duplicate
                target.append(result.submission_id)
    return summary


# -------------------------------------------------------------- анализ


class AnalysisService:
    """Выбирает анализатор по имени через реестр. Ветвлений по конкретным классам нет."""

    def __init__(self, repository: SubmissionRepository, registry: AnalyzerRegistry) -> None:
        self.repository = repository
        self.registry = registry

    @timed
    def run(self, submission_id: str, analyzer_name: str, context: AnalysisContext) -> AnalysisReport:
        value = self.repository.get(submission_id)
        if value is None:
            raise AnalysisFailure("Анализ возможен только после приёма сдачи", code="not_found", field=submission_id)
        if value.assignment_id != context.assignment.assignment_id:
            raise AnalysisFailure("Требуется контекст соответствующего задания", code="context_mismatch", field="assignment_id")

        analyzer = self.registry.create(analyzer_name)
        try:
            report = analyzer.analyze(value, context)
        except AnalysisFailure:
            raise
        except Exception as exc:
            # Явное преобразование НА ГРАНИЦЕ с кодом анализатора (возможно, плагина):
            # пользователь видит, какой анализатор упал и почему; причина сохранена в __cause__.
            logger.exception("submission_id=%s analyzer_id=%s result=crashed", submission_id, analyzer_name)
            raise AnalysisFailure(
                f"Анализатор упал: {type(exc).__name__}: {exc}", code="analyzer_crashed", field=analyzer_name
            ) from exc

        try:
            validate_report(report, value, context)
        except AnalysisFailure as exc:
            raise AnalysisFailure(exc.message, code="invalid_report", field=analyzer_name) from exc
        if report.analyzer_id != analyzer.analyzer_id or report.analyzer_version != analyzer.analyzer_version:
            raise AnalysisFailure("Отчёт не соответствует вызванному анализатору", code="invalid_report", field=analyzer_name)

        logger.info("submission_id=%s analyzer_id=%s result=success", submission_id, analyzer_name)
        return report
