"""Корень композиции: единственное место, где объекты собираются вместе.

Сервисы получают зависимости через конструктор (композиция), а не создают
их сами и не берут из глобальных переменных. Благодаря этому в тестах
любую зависимость легко подменить.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .analysis import AnalysisService
from .analyzers.registry import AnalyzerRegistry, build_default_registry
from .intake import IntakeService
from .models import Assignment
from .repository import InMemoryAssignmentCatalog, InMemorySubmissionRepository


@dataclass(frozen=True, slots=True)
class App:
    repository: InMemorySubmissionRepository
    registry: AnalyzerRegistry
    intake: IntakeService
    analysis: AnalysisService


def build_app(
    assignments: Mapping[str, Assignment] | None = None,
    *,
    registry: AnalyzerRegistry | None = None,
) -> App:
    repository = InMemorySubmissionRepository()
    registry = registry if registry is not None else build_default_registry()
    catalog = InMemoryAssignmentCatalog(assignments or {})
    return App(
        repository=repository,
        registry=registry,
        intake=IntakeService(repository),
        analysis=AnalysisService(registry, catalog, repository),
    )
