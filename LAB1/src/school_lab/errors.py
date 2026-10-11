"""Доменные исключения.

SubmissionError — всё, что относится к ПРИЁМУ сдачи. Категория задаётся полем code:
    invalid_json         строка не является корректным JSON (ошибка формата);
    schema_error         JSON корректен, но не соответствует схеме;
    unsupported_version  schema_version не поддерживается;
    conflict             submission_id уже занят другой версией.

AnalysisFailure — всё, что относится к АНАЛИЗУ: неизвестный анализатор,
неверный контекст, падение анализатора, некорректный отчёт, сбой плагина.

Оба класса отдают to_dict() с полями code/field/message. Поэтому CLI, журнал
и будущий HTTP-адаптер получают ошибку в одном формате, а выбор HTTP-статуса
остаётся делом адаптера, а не домена.
"""

from __future__ import annotations

from typing import Literal

SubmissionErrorCode = Literal["invalid_json", "schema_error", "unsupported_version", "conflict"]

AnalysisErrorCode = Literal[
    "not_found",
    "context_mismatch",
    "unknown_analyzer",
    "invalid_registration",
    "plugin_error",
    "analyzer_crashed",
    "invalid_report",
]


class SubmissionError(Exception):
    def __init__(self, code: SubmissionErrorCode, field: str, message: str) -> None:
        super().__init__(message)
        self.code: SubmissionErrorCode = code
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}

    def __str__(self) -> str:
        return f"[{self.code}] {self.field}: {self.message}"


class AnalysisFailure(Exception):
    def __init__(self, message: str, *, code: AnalysisErrorCode = "invalid_report", field: str = "analysis") -> None:
        super().__init__(message)
        self.code: AnalysisErrorCode = code
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "field": self.field, "message": self.message}

    def __str__(self) -> str:
        return f"[{self.code}] {self.field}: {self.message}"
