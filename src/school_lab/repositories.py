"""Хранилище сдач.

Сервису нужны только get и add, поэтому контракт — Protocol с этими двумя
методами. В ЛР 3 появится реализация с базой данных; сервис не изменится.

Ограничение: пара «get, затем add» не атомарна относительно других потоков.
Для синхронной ЛР 1 это допустимо; конкурентный случай — тема ЛР 3.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from .errors import SubmissionError
from .models import Submission


class SubmissionRepository(Protocol):
    def get(self, submission_id: str) -> Submission | None: ...
    def add(self, submission: Submission) -> None: ...


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._items: dict[str, Submission] = {}

    def get(self, submission_id: str) -> Submission | None:
        return self._items.get(submission_id)

    def add(self, submission: Submission) -> None:
        # Последняя линия обороны: даже при ошибке в сервисе запись не перезаписывается.
        if submission.submission_id in self._items:
            raise SubmissionError("conflict", "submission_id", "Идентификатор уже сохранён")
        self._items[submission.submission_id] = submission

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Submission]:
        return iter(list(self._items.values()))
