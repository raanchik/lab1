"""Доменные ошибки.

Каждая ошибка описывается тройкой (code, field, message):
- code    — машинно-читаемый код (стабилен, на него можно опираться в тестах и UI);
- field   — к какому полю относится проблема (None, если ко всей записи);
- message — объяснение для человека.

Иерархия исключений позволяет различать три вида проблем приёма,
которых требует задание: ошибку формата, нарушение схемы и конфликт идентификатора.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self


class ErrorCode(StrEnum):
    # Формат (строка вообще не JSON)
    INVALID_JSON = "invalid_json"
    # Схема (JSON корректен, но данные не те)
    NOT_AN_OBJECT = "not_an_object"
    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    INVALID_TYPE = "invalid_type"
    EMPTY_VALUE = "empty_value"
    INVALID_TIMESTAMP = "invalid_timestamp"
    MISSING_TIMEZONE = "missing_timezone"
    INCONSISTENT_DECLARATION = "inconsistent_declaration"
    # Идентификатор
    CONFLICT = "conflict"
    # Анализ и конфигурация
    UNKNOWN_ANALYZER = "unknown_analyzer"
    UNKNOWN_ASSIGNMENT = "unknown_assignment"
    ANALYZER_FAILED = "analyzer_failed"
    INVALID_REPORT = "invalid_report"
    # Ввод-вывод (только на уровне CLI)
    IO_ERROR = "io_error"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: ErrorCode
    field: str | None
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {"code": str(self.code), "field": self.field, "message": self.message}

    def __str__(self) -> str:
        return f"[{self.code}] {self.field or '-'}: {self.message}"


class SchoolError(Exception):
    """Базовое доменное исключение. Несёт одну или несколько ErrorDetail."""

    def __init__(self, details: Iterable[ErrorDetail]) -> None:
        self.details: tuple[ErrorDetail, ...] = tuple(details)
        if not self.details:
            raise ValueError(f"{type(self).__name__} требует хотя бы одну ErrorDetail")
        super().__init__("; ".join(map(str, self.details)))

    @classmethod
    def single(cls, code: ErrorCode, field: str | None, message: str) -> Self:
        return cls([ErrorDetail(code, field, message)])

    @property
    def code(self) -> ErrorCode:
        """Код первой ошибки — удобно, когда ошибка одна."""
        return self.details[0].code


class FormatError(SchoolError):
    """Строку нельзя разобрать как JSON."""


class SchemaError(SchoolError):
    """JSON разобран, но не соответствует схеме (может содержать несколько нарушений)."""


class ConflictError(SchoolError):
    """submission_id уже занят записью с другим содержимым."""


class ConfigurationError(SchoolError):
    """Неизвестный анализатор, задание и т. п."""


class AnalyzerError(SchoolError):
    """Анализатор упал или вернул некорректный отчёт."""
