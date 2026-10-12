"""Сервис приёма сдач и импорт.

Правила идемпотентности:
- новый submission_id                        -> ACCEPTED (сохраняем);
- тот же submission_id и тот же хеш          -> DUPLICATE (возвращаем уже принятую);
- тот же submission_id и другой хеш          -> ConflictError (исходная запись не трогается).

Доменный слой не знает про stdin, файлы и HTTP: import_records получает
любой итерируемый набор RawRecord.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .errors import ConflictError, ErrorCode, ErrorDetail, SchoolError
from .models import Submission
from .parser import parse_submission
from .repository import StoredSubmission, SubmissionRepository
from .sources import RawRecord


class IntakeStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class IntakeResult:
    status: IntakeStatus
    submission: Submission  # для DUPLICATE — ранее сохранённый объект


class IntakeService:
    def __init__(self, repository: SubmissionRepository) -> None:
        self._repository = repository  # композиция: сервис ИСПОЛЬЗУЕТ репозиторий

    def submit(self, submission: Submission) -> IntakeResult:
        content_hash = submission.content_hash()
        existing = self._repository.get(submission.submission_id)

        if existing is None:
            self._repository.add(StoredSubmission(submission, content_hash))
            return IntakeResult(IntakeStatus.ACCEPTED, submission)

        if existing.content_hash == content_hash:
            return IntakeResult(IntakeStatus.DUPLICATE, existing.submission)

        raise ConflictError.single(
            ErrorCode.CONFLICT,
            "submission_id",
            f"Сдача '{submission.submission_id}' уже принята с другим содержимым. "
            "Новая версия работы должна иметь новый submission_id.",
        )


@dataclass(frozen=True, slots=True)
class LineError:
    line: int
    detail: ErrorDetail

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, **self.detail.to_dict()}


@dataclass(slots=True)
class ImportReport:
    accepted: list[str] = field(default_factory=list)
    duplicate: list[str] = field(default_factory=list)
    errors: list[LineError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": list(self.accepted),
            "duplicate": list(self.duplicate),
            "errors": [e.to_dict() for e in self.errors],
        }


def import_records(records: Iterable[RawRecord], service: IntakeService) -> ImportReport:
    """Импортирует записи. Плохая запись попадает в отчёт и не останавливает импорт."""
    report = ImportReport()
    for record in records:
        try:
            result = service.submit(parse_submission(record.raw))
        except SchoolError as error:
            # Ловим ТОЛЬКО доменные ошибки (формат/схема/конфликт).
            # Любое другое исключение — это баг в коде, и прятать его нельзя.
            report.errors.extend(LineError(record.position, d) for d in error.details)
            continue
        if result.status is IntakeStatus.ACCEPTED:
            report.accepted.append(result.submission.submission_id)
        else:
            report.duplicate.append(result.submission.submission_id)
    return report
