"""Явный реестр фабрик анализаторов.

Центральный сервис не знает конкретных классов: он просит у реестра
«создай анализатор с id=X». Чтобы добавить анализатор, достаточно
зарегистрировать фабрику — код сервиса не меняется (принцип открытости/закрытости).

Фабрика — любой вызываемый объект без аргументов, возвращающий Analyzer.
Класс анализатора сам является такой фабрикой: LengthAnalyzer() -> экземпляр.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points

from ..errors import ConfigurationError, ErrorCode
from .base import Analyzer
from .length import LengthAnalyzer
from .template import TemplateAnalyzer

AnalyzerFactory = Callable[[], Analyzer]

#: Группа entry points, через которую внешние пакеты подключают анализаторы.
ENTRY_POINT_GROUP = "school.analyzers"


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AnalyzerFactory] = {}

    def register(self, analyzer_id: str, factory: AnalyzerFactory) -> None:
        if analyzer_id in self._factories:
            raise ValueError(f"Анализатор '{analyzer_id}' уже зарегистрирован")
        self._factories[analyzer_id] = factory

    def create(self, analyzer_id: str) -> Analyzer:
        factory = self._factories.get(analyzer_id)
        if factory is None:
            raise ConfigurationError.single(
                ErrorCode.UNKNOWN_ANALYZER,
                "analyzer_id",
                f"Неизвестный анализатор '{analyzer_id}'. Доступны: {', '.join(self.ids()) or 'нет'}",
            )
        analyzer = factory()
        if analyzer.analyzer_id != analyzer_id:
            raise ConfigurationError.single(
                ErrorCode.UNKNOWN_ANALYZER,
                "analyzer_id",
                f"Фабрика '{analyzer_id}' создала анализатор с id '{analyzer.analyzer_id}'",
            )
        return analyzer

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def __contains__(self, analyzer_id: object) -> bool:
        return analyzer_id in self._factories

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Подключает анализаторы из установленных пакетов. Возвращает их id."""
        loaded: list[str] = []
        for ep in entry_points(group=group):
            self.register(ep.name, ep.load())
            loaded.append(ep.name)
        return loaded


def build_default_registry(*, load_plugins: bool = False) -> AnalyzerRegistry:
    """Каждый вызов создаёт НОВЫЙ реестр — глобального изменяемого состояния нет."""
    registry = AnalyzerRegistry()
    registry.register(LengthAnalyzer.analyzer_id, LengthAnalyzer)
    registry.register(TemplateAnalyzer.analyzer_id, TemplateAnalyzer)
    if load_plugins:
        registry.load_entry_points()
    return registry
