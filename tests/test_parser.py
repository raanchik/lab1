"""Этап А: разбор и валидация."""

from __future__ import annotations

import copy
import dataclasses
import json
from typing import Any

import pytest
from helpers import make_record

from school.errors import ErrorCode, FormatError, SchemaError
from school.parser import parse_assignments, parse_submission, validate_submission


def codes(error: SchemaError) -> set[tuple[ErrorCode, str | None]]:
    return {(d.code, d.field) for d in error.details}


def test_valid_record_is_accepted(record: dict[str, Any]) -> None:
    submission = validate_submission(record)
    assert submission.submission_id == "sub-1"
    assert submission.submitted_at.utcoffset() is not None
    assert submission.ai_declaration.used is False


def test_parse_submission_from_json_line(record: dict[str, Any]) -> None:
    submission = parse_submission(json.dumps(record))
    assert submission == validate_submission(record)


def test_utc_z_suffix_is_accepted() -> None:
    submission = validate_submission(make_record(submitted_at="2026-09-14T07:00:00Z"))
    assert submission.submitted_at.utcoffset() is not None


def test_broken_json_is_format_error() -> None:
    with pytest.raises(FormatError) as info:
        parse_submission('{"submission_id": "x", ')
    assert info.value.code is ErrorCode.INVALID_JSON


def test_format_error_and_schema_error_are_different_kinds() -> None:
    with pytest.raises(SchemaError):  # корректный JSON, но не объект
        parse_submission("[1, 2, 3]")


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"submitted_at": "14.09.2026 10:00"}, (ErrorCode.INVALID_TIMESTAMP, "submitted_at")),
        ({"submitted_at": "2026-09-14T10:00:00"}, (ErrorCode.MISSING_TIMEZONE, "submitted_at")),
        ({"student_id": ""}, (ErrorCode.EMPTY_VALUE, "student_id")),
        ({"student_id": "   "}, (ErrorCode.EMPTY_VALUE, "student_id")),
        ({"grade": 5}, (ErrorCode.UNKNOWN_FIELD, "grade")),
        ({"code": 42}, (ErrorCode.INVALID_TYPE, "code")),
        ({"student_id": None}, (ErrorCode.INVALID_TYPE, "student_id")),
        ({"ai_declaration": "нет"}, (ErrorCode.INVALID_TYPE, "ai_declaration")),
        ({"ai_declaration": {"used": "yes"}}, (ErrorCode.INVALID_TYPE, "ai_declaration.used")),
        ({"ai_declaration": {"used": 1}}, (ErrorCode.INVALID_TYPE, "ai_declaration.used")),
        ({"ai_declaration": {}}, (ErrorCode.MISSING_FIELD, "ai_declaration.used")),
        ({"ai_declaration": {"used": True, "model": "x"}}, (ErrorCode.UNKNOWN_FIELD, "ai_declaration.model")),
        ({"ai_declaration": {"used": True, "tools": "ChatGPT"}}, (ErrorCode.INVALID_TYPE, "ai_declaration.tools")),
        (
            {"ai_declaration": {"used": False, "tools": ["ChatGPT"]}},
            (ErrorCode.INCONSISTENT_DECLARATION, "ai_declaration.tools"),
        ),
    ],
)
def test_schema_violations_are_explained(overrides: dict[str, Any], expected: tuple[ErrorCode, str]) -> None:
    with pytest.raises(SchemaError) as info:
        validate_submission(make_record(**overrides))
    assert expected in codes(info.value)
    assert all(d.message for d in info.value.details)  # у каждой ошибки есть объяснение


def test_missing_field() -> None:
    record = make_record()
    del record["code"]
    with pytest.raises(SchemaError) as info:
        validate_submission(record)
    assert (ErrorCode.MISSING_FIELD, "code") in codes(info.value)


def test_all_violations_reported_at_once() -> None:
    with pytest.raises(SchemaError) as info:
        validate_submission(make_record(student_id="", submitted_at="вчера", extra=1))
    assert {ErrorCode.EMPTY_VALUE, ErrorCode.INVALID_TIMESTAMP, ErrorCode.UNKNOWN_FIELD} <= {
        d.code for d in info.value.details
    }


def test_used_true_with_empty_description_is_valid_schema() -> None:
    # Это не ошибка схемы: пустую декларацию проверяет отдельный анализатор (см. защиту).
    submission = validate_submission(make_record(ai_declaration={"used": True, "description": ""}))
    assert submission.ai_declaration.used is True


def test_validation_does_not_mutate_input(record: dict[str, Any]) -> None:
    snapshot = copy.deepcopy(record)
    validate_submission(record)
    assert record == snapshot

    broken = make_record(student_id="", extra=1)
    broken_snapshot = copy.deepcopy(broken)
    with pytest.raises(SchemaError):
        validate_submission(broken)
    assert broken == broken_snapshot


def test_submission_is_immutable(record: dict[str, Any]) -> None:
    submission = validate_submission(record)
    with pytest.raises(dataclasses.FrozenInstanceError):
        submission.text = "подмена"  # type: ignore[misc]


def test_hash_ignores_key_order_and_formatting(record: dict[str, Any]) -> None:
    a = parse_submission(json.dumps(record))
    b = parse_submission(json.dumps(dict(reversed(list(record.items()))), indent=4))
    assert a.content_hash() == b.content_hash()


def test_hash_changes_with_content(record: dict[str, Any]) -> None:
    a = validate_submission(record)
    b = validate_submission(make_record(text="другое"))
    assert a.content_hash() != b.content_hash()


def test_parse_assignments() -> None:
    result = parse_assignments([{"assignment_id": "lab-1", "allowed_template": "x", "deadline": "ignored"}])
    assert result["lab-1"].allowed_template == "x"


def test_parse_assignments_reports_bad_items() -> None:
    with pytest.raises(SchemaError) as info:
        parse_assignments([{"assignment_id": ""}, 5])
    fields = {d.field for d in info.value.details}
    assert fields == {"assignments[0].assignment_id", "assignments[1]"}
