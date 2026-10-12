"""Этап А: сервис приёма, дубликаты, конфликты, импорт."""

from __future__ import annotations

import json

import pytest
from helpers import make_record, make_submission

from school.errors import ConflictError, ErrorCode
from school.intake import IntakeService, IntakeStatus, import_records
from school.repository import InMemorySubmissionRepository
from school.sources import InMemorySubmissionSource


@pytest.fixture
def service(repository: InMemorySubmissionRepository) -> IntakeService:
    return IntakeService(repository)


def test_new_submission_is_accepted(service: IntakeService, repository: InMemorySubmissionRepository) -> None:
    result = service.submit(make_submission())
    assert result.status is IntakeStatus.ACCEPTED
    assert len(repository) == 1


def test_duplicate_returns_existing_and_does_not_grow(
    service: IntakeService, repository: InMemorySubmissionRepository
) -> None:
    first = service.submit(make_submission()).submission
    again = service.submit(make_submission())
    assert again.status is IntakeStatus.DUPLICATE
    assert again.submission is first  # возвращается именно ранее принятая сдача
    assert len(repository) == 1


def test_conflict_does_not_overwrite(service: IntakeService, repository: InMemorySubmissionRepository) -> None:
    original = make_submission()
    service.submit(original)
    with pytest.raises(ConflictError) as info:
        service.submit(make_submission(text="совсем другой текст"))
    assert info.value.code is ErrorCode.CONFLICT
    assert info.value.details[0].field == "submission_id"
    assert repository.get_submission("sub-1") == original
    assert len(repository) == 1


def test_new_version_has_new_id(service: IntakeService) -> None:
    service.submit(make_submission())
    result = service.submit(make_submission(submission_id="sub-1-v2", text="исправлено"))
    assert result.status is IntakeStatus.ACCEPTED


def test_import_continues_after_broken_line(service: IntakeService) -> None:
    lines = [
        json.dumps(make_record(submission_id="a")),
        '{"broken": ',
        json.dumps(make_record(submission_id="b", student_id="")),
        json.dumps(make_record(submission_id="a")),  # дубликат
        json.dumps(make_record(submission_id="a", text="другое")),  # конфликт
        json.dumps(make_record(submission_id="c")),
    ]
    with InMemorySubmissionSource(lines) as source:
        report = import_records(source.records(), service)

    assert report.accepted == ["a", "c"]
    assert report.duplicate == ["a"]
    by_line = {(e.line, e.detail.code) for e in report.errors}
    assert by_line == {
        (2, ErrorCode.INVALID_JSON),
        (3, ErrorCode.EMPTY_VALUE),
        (5, ErrorCode.CONFLICT),
    }


def test_import_report_to_dict_has_required_keys(service: IntakeService) -> None:
    with InMemorySubmissionSource(["not json"]) as source:
        data = import_records(source.records(), service).to_dict()
    assert set(data) == {"accepted", "duplicate", "errors"}
    assert data["errors"][0] == {
        "line": 1,
        "code": "invalid_json",
        "field": None,
        "message": data["errors"][0]["message"],
    }


def test_unexpected_exception_is_not_swallowed() -> None:
    class BrokenRepository(InMemorySubmissionRepository):
        def add(self, stored: object) -> None:  # type: ignore[override]
            raise RuntimeError("диск сломался")

    service = IntakeService(BrokenRepository())
    with InMemorySubmissionSource([json.dumps(make_record())]) as source:
        with pytest.raises(RuntimeError):
            import_records(source.records(), service)
