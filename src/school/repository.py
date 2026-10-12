"""Хранилища (в этой работе — in-memory).

Сервисы зависят от протоколов (SubmissionRepository, SubmissionReader,
AssignmentCatalog), а не от конкретных классов. В ЛР с базой данных
достаточно будет написать другой класс с теми же методами — сервисы не изменятся.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol

from .models import Assignment, Submission


@dataclass(frozen=True, slots=True)
class StoredSubmission:
    submission: Submission
    content_hash: str


class SubmissionReader(Protocol):
    """Только чтение — именно это получают анализаторы через контекст."""

    def get_submission(self, submission_id: str) -> Submission | None: ...


class SubmissionRepository(SubmissionReader, Protocol):
    def get(self, submission_id: str) -> StoredSubmission | None: ...
    def add(self, stored: StoredSubmission) -> None: ...
    def __len__(self) -> int: ...


class AssignmentCatalog(Protocol):
    def get(self, assignment_id: str) -> Assignment | None: ...


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._items: dict[str, StoredSubmission] = {}

    def get(self, submission_id: str) -> StoredSubmission | None:
        return self._items.get(submission_id)

    def get_submission(self, submission_id: str) -> Submission | None:
        stored = self._items.get(submission_id)
        return stored.submission if stored else None

    def add(self, stored: StoredSubmission) -> None:
        sid = stored.submission.submission_id
        if sid in self._items:
            # Решение «дубликат или конфликт» принимает сервис; репозиторий
            # лишь защищает себя от перезаписи.
            raise ValueError(f"submission_id '{sid}' уже существует")
        self._items[sid] = stored

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[StoredSubmission]:
        return iter(self._items.values())


class InMemoryAssignmentCatalog:
    def __init__(self, assignments: Mapping[str, Assignment]) -> None:
        self._items = dict(assignments)  # копия: внешний словарь можно менять без последствий

    def get(self, assignment_id: str) -> Assignment | None:
        return self._items.get(assignment_id)
