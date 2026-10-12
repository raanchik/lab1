"""Разбор и валидация входных данных.

Два шага намеренно разделены:
1. parse_json_line  — «это вообще JSON?»          -> FormatError
2. validate_submission — «это корректная сдача?»   -> SchemaError

validate_submission принимает уже разобранный объект, поэтому её можно
вызывать напрямую (из тестов, из другого адаптера), а не только из CLI.

Валидатор только ЧИТАЕТ входной словарь и никогда его не изменяет.
Он собирает ВСЕ нарушения сразу, а не падает на первом: студенту
полезнее увидеть полный список проблем.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from .errors import ErrorCode, ErrorDetail, FormatError, SchemaError
from .models import AIDeclaration, Assignment, Submission

SUBMISSION_FIELDS: frozenset[str] = frozenset(
    {"submission_id", "student_id", "assignment_id", "submitted_at", "text", "code", "ai_declaration"}
)
DECLARATION_FIELDS: frozenset[str] = frozenset({"used", "description", "tools"})

_MISSING = object()  # маркер «поля нет» (отличаем от значения null)


def parse_json_line(raw: str) -> Any:
    """Разбирает одну JSONL-строку. Бросает FormatError, если это не JSON."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FormatError.single(
            ErrorCode.INVALID_JSON, None, f"Некорректный JSON: {exc.msg} (символ {exc.pos})"
        ) from exc


def parse_submission(raw: str) -> Submission:
    """Строка JSONL -> Submission. FormatError или SchemaError при проблемах."""
    return validate_submission(parse_json_line(raw))


def validate_submission(data: object) -> Submission:
    """Проверяет разобранный JSON-объект и строит доменный Submission."""
    if not isinstance(data, Mapping):
        raise SchemaError.single(
            ErrorCode.NOT_AN_OBJECT, None, f"Ожидался JSON-объект, получено: {_json_type(data)}"
        )

    issues: list[ErrorDetail] = []

    for name in sorted(set(map(str, data)) - SUBMISSION_FIELDS):
        issues.append(
            ErrorDetail(
                ErrorCode.UNKNOWN_FIELD,
                name,
                f"Неизвестное поле '{name}'. Допустимые: {', '.join(sorted(SUBMISSION_FIELDS))}",
            )
        )

    submission_id = _require_identifier(data, "submission_id", issues)
    student_id = _require_identifier(data, "student_id", issues)
    assignment_id = _require_identifier(data, "assignment_id", issues)
    submitted_at = _require_timestamp(data, "submitted_at", issues)
    text = _require_str(data, "text", issues)
    code = _require_str(data, "code", issues)
    declaration = _require_declaration(data, "ai_declaration", issues)

    if issues:
        raise SchemaError(issues)

    # Если нарушений нет, все значения гарантированно заполнены;
    # assert здесь только сужает типы для mypy.
    assert submission_id is not None and student_id is not None and assignment_id is not None
    assert submitted_at is not None and text is not None and code is not None
    assert declaration is not None

    return Submission(
        submission_id=submission_id,
        student_id=student_id,
        assignment_id=assignment_id,
        submitted_at=submitted_at,
        text=text,
        code=code,
        ai_declaration=declaration,
    )


def parse_assignments(data: object) -> dict[str, Assignment]:
    """assignments.json -> {assignment_id: Assignment}.

    Принимает список заданий или объект {"assignments": [...]}.
    Лишние поля задания игнорируются: файл заданий ведёт преподаватель,
    и он может содержать данные для будущих лабораторных.
    """
    if isinstance(data, Mapping) and "assignments" in data:
        data = data["assignments"]
    if not isinstance(data, list):
        raise SchemaError.single(
            ErrorCode.INVALID_TYPE, "assignments", "Ожидался список заданий"
        )

    issues: list[ErrorDetail] = []
    result: dict[str, Assignment] = {}
    for index, item in enumerate(data):
        prefix = f"assignments[{index}]"
        if not isinstance(item, Mapping):
            issues.append(ErrorDetail(ErrorCode.NOT_AN_OBJECT, prefix, "Задание должно быть объектом"))
            continue
        local: list[ErrorDetail] = []
        assignment_id = _require_identifier(item, "assignment_id", local)
        title = _optional_str(item, "title", local)
        template = _optional_str(item, "allowed_template", local)
        for detail in local:
            issues.append(ErrorDetail(detail.code, f"{prefix}.{detail.field}", detail.message))
        if not local and assignment_id is not None:
            result[assignment_id] = Assignment(assignment_id, title, template)
    if issues:
        raise SchemaError(issues)
    return result


# ---------------------------------------------------------------- helpers


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _get(data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]) -> object:
    value = data.get(name, _MISSING)
    if value is _MISSING:
        issues.append(ErrorDetail(ErrorCode.MISSING_FIELD, name, f"Обязательное поле '{name}' отсутствует"))
    return value


def _require_str(data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]) -> str | None:
    value = _get(data, name, issues)
    if value is _MISSING:
        return None
    if not isinstance(value, str):
        issues.append(
            ErrorDetail(
                ErrorCode.INVALID_TYPE,
                name,
                f"Поле '{name}' должно быть строкой, получено: {_json_type(value)}",
            )
        )
        return None
    return value


def _optional_str(data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]) -> str:
    value = data.get(name, "")
    if not isinstance(value, str):
        issues.append(
            ErrorDetail(ErrorCode.INVALID_TYPE, name, f"Поле '{name}' должно быть строкой")
        )
        return ""
    return value


def _require_identifier(data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]) -> str | None:
    value = _require_str(data, name, issues)
    if value is not None and not value.strip():
        issues.append(ErrorDetail(ErrorCode.EMPTY_VALUE, name, f"Поле '{name}' не может быть пустым"))
        return None
    return value


def _require_timestamp(data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]) -> datetime | None:
    raw = _require_str(data, name, issues)
    if raw is None:
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        issues.append(
            ErrorDetail(
                ErrorCode.INVALID_TIMESTAMP,
                name,
                f"'{raw}' не является датой ISO 8601 (пример: 2026-09-14T10:00:00+03:00)",
            )
        )
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        issues.append(
            ErrorDetail(
                ErrorCode.MISSING_TIMEZONE,
                name,
                f"У времени '{raw}' не указан часовой пояс (добавьте, например, +03:00 или Z)",
            )
        )
        return None
    return value


def _require_declaration(
    data: Mapping[Any, Any], name: str, issues: list[ErrorDetail]
) -> AIDeclaration | None:
    value = _get(data, name, issues)
    if value is _MISSING:
        return None
    if not isinstance(value, Mapping):
        issues.append(
            ErrorDetail(
                ErrorCode.INVALID_TYPE, name, f"Поле '{name}' должно быть объектом, получено: {_json_type(value)}"
            )
        )
        return None

    before = len(issues)
    for key in sorted(set(map(str, value)) - DECLARATION_FIELDS):
        issues.append(ErrorDetail(ErrorCode.UNKNOWN_FIELD, f"{name}.{key}", f"Неизвестное поле '{key}'"))

    used = value.get("used", _MISSING)
    if used is _MISSING:
        issues.append(ErrorDetail(ErrorCode.MISSING_FIELD, f"{name}.used", "Обязательное поле 'used' отсутствует"))
    elif not isinstance(used, bool):  # bool проверяем явно: 1 и "true" — не bool
        issues.append(
            ErrorDetail(
                ErrorCode.INVALID_TYPE, f"{name}.used", f"'used' должно быть true/false, получено: {_json_type(used)}"
            )
        )

    description = value.get("description", "")
    if not isinstance(description, str):
        issues.append(ErrorDetail(ErrorCode.INVALID_TYPE, f"{name}.description", "'description' должно быть строкой"))

    tools = value.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        issues.append(ErrorDetail(ErrorCode.INVALID_TYPE, f"{name}.tools", "'tools' должно быть списком строк"))
    elif used is False and tools:
        issues.append(
            ErrorDetail(
                ErrorCode.INCONSISTENT_DECLARATION,
                f"{name}.tools",
                "Указаны инструменты AI, но used=false",
            )
        )

    if len(issues) > before:
        return None
    assert isinstance(used, bool) and isinstance(description, str) and isinstance(tools, list)
    return AIDeclaration(used=used, description=description, tools=tuple(tools))
