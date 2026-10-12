"""Fixtures: каждый тест получает НОВЫЙ сервис и отдельную копию входа.

Общий глобальный репозиторий сделал бы тесты зависимыми от порядка запуска.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from helpers import RAW_EXAMPLE, TEMPLATE

from school_lab.analyzers import AnalysisContext
from school_lab.app import Application, build_application
from school_lab.models import Assignment, Submission
from school_lab.parsing import parse_submission
from school_lab.repositories import InMemorySubmissionRepository
from school_lab.services import SubmissionService


@pytest.fixture
def raw_submission() -> dict[str, Any]:
    return copy.deepcopy(RAW_EXAMPLE)


@pytest.fixture
def repository() -> InMemorySubmissionRepository:
    return InMemorySubmissionRepository()


@pytest.fixture
def service(repository: InMemorySubmissionRepository) -> SubmissionService:
    return SubmissionService(repository)


@pytest.fixture
def submission() -> Submission:
    return parse_submission(copy.deepcopy(RAW_EXAMPLE))


@pytest.fixture
def assignment() -> Assignment:
    return Assignment("assignment-01", TEMPLATE, ("Наличие функции solve",))


@pytest.fixture
def context(assignment: Assignment) -> AnalysisContext:
    return AnalysisContext(assignment)


@pytest.fixture
def app() -> Application:
    return build_application()
