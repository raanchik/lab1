"""Этап А: приём, дубликат, конфликт, импорт с частичным успехом (+ упражнение 2)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from helpers import DATA_DIR, RAW_EXAMPLE, changed

from school_lab.errors import SubmissionError
from school_lab.models import Submission
from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import ImportSummary, SubmissionService, import_source
from school_lab.sources import InMemorySource, JSONLSource


def test_accept_then_duplicate(service: SubmissionService, repository: InMemorySubmissionRepository) -> None:
    first = service.accept(RAW_EXAMPLE)
    second = service.accept(copy.deepcopy(RAW_EXAMPLE))
    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert first.content_hash == second.content_hash
    assert len(repository) == 1  # дубликат не увеличил число сдач


def test_conflict_does_not_overwrite(service: SubmissionService, repository: InMemorySubmissionRepository) -> None:
    service.accept(RAW_EXAMPLE)
    original = repository.get("sub-001")
    with pytest.raises(SubmissionError) as caught:
        service.accept(changed(code="print('другая версия')"))
    assert (caught.value.code, caught.value.field) == ("conflict", "submission_id")
    assert repository.get("sub-001") == original
    assert len(repository) == 1


@pytest.mark.parametrize("student_id", ["", " ", None, 42])
def test_reject_bad_student_id(
    raw_submission: dict[str, Any], service: SubmissionService, student_id: object
) -> None:
    raw_submission["student_id"] = student_id
    with pytest.raises(SubmissionError) as caught:
        service.accept(raw_submission)
    assert caught.value.code == "schema_error"
    assert service.repository.get(raw_submission["submission_id"]) is None  # состояние не изменилось


def test_new_version_with_new_id(service: SubmissionService, repository: InMemorySubmissionRepository) -> None:
    """Упражнение 2: новая версия — новый ID, обе версии сохранены."""
    service.accept(RAW_EXAMPLE)
    result = service.accept(changed(submission_id="sub-001-v2", code="def solve(values):\n    return 1\n"))
    assert result.status == "accepted"
    assert len(repository) == 2
    v1, v2 = repository.get("sub-001"), repository.get("sub-001-v2")
    assert v1 is not None and v2 is not None and v1.code != v2.code


def test_repository_refuses_overwrite(repository: InMemorySubmissionRepository, submission: Submission) -> None:
    repository.add(submission)
    with pytest.raises(SubmissionError):
        repository.add(submission)


def test_import_partial_success(tmp_path: Path) -> None:
    lines = [
        json.dumps(RAW_EXAMPLE),
        "{broken",
        json.dumps(RAW_EXAMPLE),
        json.dumps(changed(text="Другое содержимое с тем же ID")),
        json.dumps(changed(submission_id="bad-record", student_id="")),
        "",
        json.dumps(changed(submission_id="sub-002")),
    ]
    path = tmp_path / "mixed.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    repo = InMemorySubmissionRepository()

    summary = import_source(JSONLSource(path), SubmissionService(repo))

    assert summary.accepted == ["sub-001", "sub-002"]
    assert summary.duplicate == ["sub-001"]
    assert [(e["line_no"], e["code"]) for e in summary.errors] == [
        (2, "invalid_json"), (4, "conflict"), (5, "schema_error"), (6, "invalid_json"),
    ]
    assert len(repo) == 2


def test_invalid_submissions_file_gives_explained_errors() -> None:
    service = SubmissionService(InMemorySubmissionRepository())
    summary = import_source(JSONLSource(DATA_DIR / "invalid_submissions.jsonl"), service)
    assert summary.accepted == [] and summary.duplicate == []
    assert len(summary.errors) == 18
    assert all(e["code"] and e["field"] and e["message"] for e in summary.errors)
    assert {e["code"] for e in summary.errors} == {"invalid_json", "schema_error", "unsupported_version"}


def test_reimport_gives_only_duplicates() -> None:
    service = SubmissionService(InMemorySubmissionRepository())
    raws = [json.loads(line) for line in (DATA_DIR / "submissions.jsonl").read_text(encoding="utf-8").splitlines()]
    first = import_source(InMemorySource(raws), service)
    second = import_source(InMemorySource(raws), service)
    assert len(first.accepted) == 12 and not first.errors
    assert len(second.duplicate) == 12 and not second.accepted


def test_unexpected_defect_is_not_swallowed() -> None:
    class BrokenRepository(InMemorySubmissionRepository):
        def add(self, submission: Submission) -> None:
            raise RuntimeError("дефект хранилища")

    with pytest.raises(RuntimeError):
        import_source(InMemorySource([RAW_EXAMPLE]), SubmissionService(BrokenRepository()))


def test_import_summaries_do_not_share_lists() -> None:
    left, right = ImportSummary(), ImportSummary()
    left.errors.append({"line_no": 1})
    assert right.errors == []
