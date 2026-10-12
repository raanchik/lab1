"""Этап А: разбор JSON и валидация схемы (включая упражнение 1)."""

from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError, asdict, replace
from typing import Any

import pytest
from helpers import RAW_EXAMPLE, changed, changed_declaration

from school_lab.errors import SubmissionError
from school_lab.hashing import submission_hash
from school_lab.parsing import decode_json, parse_assignments, parse_submission


def test_valid_submission_is_parsed_without_changes(raw_submission: dict[str, Any]) -> None:
    value = parse_submission(raw_submission)
    assert asdict(value) == RAW_EXAMPLE  # text/code/время сохранены как есть
    assert value.code == RAW_EXAMPLE["code"]


def test_utc_z_suffix_is_accepted() -> None:
    assert parse_submission(changed(submitted_at="2026-09-01T07:01:00Z")).submitted_at.endswith("Z")


@pytest.mark.parametrize(
    ("raw", "code", "field"),
    [
        # из лекции
        (changed(schema_version=True), "schema_error", "schema_version"),
        (changed(schema_version=2), "unsupported_version", "schema_version"),
        (changed(code=123), "schema_error", "code"),
        (changed(submitted_at="2026-09-01T10:00:00"), "schema_error", "submitted_at"),
        (changed(submitted_at="01.09.2026 10:00"), "schema_error", "submitted_at"),
        (changed(student_id="  "), "schema_error", "student_id"),
        (changed(unknown="value"), "schema_error", "unknown"),
        (changed(text=" ", code="\n"), "schema_error", "text/code"),
        (changed_declaration(used=True, tool=None, purpose=None), "schema_error", "ai_declaration"),
        # упражнение 1 и дополнительные случаи
        (changed_declaration(used="false"), "schema_error", "ai_declaration.used"),
        (changed_declaration(used=1), "schema_error", "ai_declaration.used"),
        (changed(template_id=" "), "schema_error", "template_id"),
        (changed(student_id=None), "schema_error", "student_id"),
        (changed(ai_declaration=[]), "schema_error", "ai_declaration"),
        (changed_declaration(model="x"), "schema_error", "ai_declaration.model"),
        (changed_declaration(used=True, tool="", purpose="тесты"), "schema_error", "ai_declaration.tool"),
        ([1, 2, 3], "schema_error", "submission"),
    ],
)
def test_schema_violations(raw: Any, code: str, field: str) -> None:
    before = copy.deepcopy(raw)
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw)
    assert (caught.value.code, caught.value.field) == (code, field)
    assert caught.value.message  # объяснение для человека
    assert raw == before  # вход не изменён даже при ошибке


def test_missing_nested_field() -> None:
    raw = copy.deepcopy(RAW_EXAMPLE)
    del raw["ai_declaration"]["verified_by_student"]
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw)
    assert caught.value.field == "ai_declaration.verified_by_student"


def test_typo_in_field_name_is_not_silently_dropped() -> None:
    raw = copy.deepcopy(RAW_EXAMPLE)
    raw["studnet_id"] = raw.pop("student_id")
    with pytest.raises(SubmissionError) as caught:
        parse_submission(raw)
    assert caught.value.field == "student_id"  # сначала сообщается отсутствующее обязательное поле


def test_success_does_not_mutate_input(raw_submission: dict[str, Any]) -> None:
    before = copy.deepcopy(raw_submission)
    parse_submission(raw_submission)
    assert raw_submission == before


def test_submission_is_frozen(raw_submission: dict[str, Any]) -> None:
    value = parse_submission(raw_submission)
    with pytest.raises(FrozenInstanceError):
        value.student_id = "another"  # type: ignore[misc]


def test_error_to_dict() -> None:
    error = SubmissionError("schema_error", "student_id", "Требуется непустой идентификатор")
    assert error.to_dict() == {"code": "schema_error", "field": "student_id", "message": "Требуется непустой идентификатор"}


@pytest.mark.parametrize(
    "line",
    ['{broken', '{"student_id": "a", "student_id": "b"}', '{"score": NaN}', '{"x": Infinity}', ""],
    ids=["broken", "repeated-key", "nan", "infinity", "empty-line"],
)
def test_decode_json_rejects(line: str) -> None:
    with pytest.raises(SubmissionError) as caught:
        decode_json(line)
    assert caught.value.code == "invalid_json"


def test_format_and_schema_errors_are_different(raw_submission: dict[str, Any]) -> None:
    assert parse_submission(decode_json(json.dumps(raw_submission))) == parse_submission(raw_submission)
    with pytest.raises(SubmissionError) as caught:
        parse_submission(decode_json("[1]"))  # JSON корректен, схема — нет
    assert caught.value.code == "schema_error"


# ----------------------------------------------------------------- хеш


def test_hash_ignores_key_order(raw_submission: dict[str, Any]) -> None:
    reordered = dict(reversed(list(raw_submission.items())))
    assert submission_hash(parse_submission(reordered)) == submission_hash(parse_submission(raw_submission))


def test_hash_depends_on_content(raw_submission: dict[str, Any]) -> None:
    value = parse_submission(raw_submission)
    assert submission_hash(replace(value, code=value.code + "\n")) != submission_hash(value)
    assert submission_hash(replace(value, student_id="student-other")) != submission_hash(value)


def test_same_moment_different_notation_gives_different_hash() -> None:
    a = parse_submission(changed(submitted_at="2026-09-01T10:01:00+03:00"))
    b = parse_submission(changed(submitted_at="2026-09-01T07:01:00+00:00"))
    assert submission_hash(a) != submission_hash(b)  # следствие контракта: время хранится строкой


# ------------------------------------------------------------- задания


def test_parse_assignments() -> None:
    result = parse_assignments([{"assignment_id": "a-1", "allowed_template": "x\n", "requirements": ["r"], "deadline": "-"}])
    assert result["a-1"].allowed_template == "x\n"
    assert result["a-1"].requirements == ("r",)


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"x": 1}, "assignments"),
        ([{"assignment_id": ""}], "assignments[0].assignment_id"),
        ([{"assignment_id": "a"}, {"assignment_id": "a"}], "assignments[1].assignment_id"),
        ([{"assignment_id": "a", "requirements": "r"}], "assignments[0].requirements"),
    ],
)
def test_parse_assignments_errors(raw: object, field: str) -> None:
    with pytest.raises(SubmissionError) as caught:
        parse_assignments(raw)
    assert caught.value.field == field
