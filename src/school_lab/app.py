"""Точка сборки приложения: единственное место, где компоненты соединяются.

Сервисы не создают зависимости сами и не берут их из глобальных переменных —
всё передаётся через конструкторы. Поэтому в тестах любую часть легко заменить.
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry import AnalyzerRegistry, build_registry
from .repositories import InMemorySubmissionRepository
from .services import AnalysisService, SubmissionService


@dataclass(frozen=True, slots=True)
class Application:
    repository: InMemorySubmissionRepository
    registry: AnalyzerRegistry
    submission_service: SubmissionService
    analysis_service: AnalysisService


def build_application(*, registry: AnalyzerRegistry | None = None) -> Application:
    repository = InMemorySubmissionRepository()
    registry = registry if registry is not None else build_registry()
    return Application(
        repository=repository,
        registry=registry,
        submission_service=SubmissionService(repository),
        analysis_service=AnalysisService(repository, registry),
    )
