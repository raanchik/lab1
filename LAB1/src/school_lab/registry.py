"""Явный реестр фабрик анализаторов и загрузка плагинов через entry points.

Фабрика — любой вызываемый объект без аргументов, возвращающий Analyzer.
Сам класс — тоже фабрика: LengthAnalyzer() создаёт экземпляр.

Реестр создаётся в точке сборки приложения (build_registry) и передаётся
сервису. Глобального изменяемого реестра нет: каждый тест получает свой.

Ловушка позднего связывания: при регистрации в цикле
    for name in names: registry.register(name, lambda: make(name))
все lambda увидят ПОСЛЕДНЕЕ значение name. Исправление — фиксировать значение
аргументом по умолчанию: lambda name=name: make(name).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points

from .analyzers import Analyzer, LengthAnalyzer, MissingExplanationAnalyzer, TemplateAnalyzer
from .errors import AnalysisFailure

AnalyzerFactory = Callable[[], Analyzer]

#: Группа entry points для внешних анализаторов. Версия plugin API: 1
#: (контракт Analyzer + AnalysisReport из school_lab.models).
ENTRY_POINT_GROUP = "school_lab.analyzers"
PLUGIN_API_VERSION = 1


class AnalyzerRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AnalyzerFactory] = {}

    def register(self, name: str, factory: AnalyzerFactory) -> None:
        if not name.strip():
            raise AnalysisFailure("Требуется непустое имя анализатора", code="invalid_registration", field="name")
        if name in self._factories:
            raise AnalysisFailure(f"Анализатор '{name}' уже зарегистрирован", code="invalid_registration", field=name)
        self._factories[name] = factory

    def create(self, name: str) -> Analyzer:
        try:
            factory = self._factories[name]
        except KeyError as exc:
            known = ", ".join(self.names()) or "нет"
            raise AnalysisFailure(
                f"Неизвестный анализатор: {name}. Доступны: {known}", code="unknown_analyzer", field=name
            ) from exc
        analyzer = factory()
        if analyzer.analyzer_id != name:
            raise AnalysisFailure(
                f"Имя регистрации '{name}' не совпадает с analyzer_id '{analyzer.analyzer_id}'",
                code="invalid_registration",
                field=name,
            )
        return analyzer

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))

    def __contains__(self, name: object) -> bool:
        return name in self._factories

    def load_entry_points(
        self,
        group: str = ENTRY_POINT_GROUP,
        *,
        discover: Callable[[str], Iterable[EntryPoint]] | None = None,
    ) -> list[str]:
        """Находит установленные плагины и регистрирует их. Возвращает имена.

        discover можно подменить в тестах; по умолчанию — importlib.metadata.entry_points.
        Проверки выполняются СРАЗУ при загрузке, а не при первом анализе:
        повтор имени, ошибка импорта, несоответствие entry.name и analyzer_id.

        Граница доверия: entry.load() ИСПОЛНЯЕТ код пакета. Механизм для
        контролируемых расширений, а не для кода из студенческих сдач.
        """
        found = discover(group) if discover is not None else entry_points(group=group)
        loaded: list[str] = []
        for entry in found:
            if entry.name in self._factories:
                raise AnalysisFailure(
                    f"Плагин '{entry.name}' конфликтует с уже зарегистрированным анализатором",
                    code="invalid_registration",
                    field=entry.name,
                )
            try:
                factory = entry.load()
                analyzer = factory()
            except Exception as exc:  # граница с чужим кодом: любая ошибка импорта/создания
                raise AnalysisFailure(
                    f"Не удалось загрузить плагин {entry.name} ({entry.value}): {type(exc).__name__}: {exc}",
                    code="plugin_error",
                    field=entry.name,
                ) from exc
            if getattr(analyzer, "analyzer_id", None) != entry.name:
                raise AnalysisFailure(
                    f"entry point '{entry.name}' создаёт анализатор с другим analyzer_id",
                    code="invalid_registration",
                    field=entry.name,
                )
            self.register(entry.name, factory)
            loaded.append(entry.name)
        return loaded


def build_registry(*, load_plugins: bool = False) -> AnalyzerRegistry:
    """Каждый вызов создаёт НОВЫЙ реестр со встроенными анализаторами."""
    registry = AnalyzerRegistry()
    registry.register(LengthAnalyzer.analyzer_id, LengthAnalyzer)
    registry.register(TemplateAnalyzer.analyzer_id, TemplateAnalyzer)
    registry.register(MissingExplanationAnalyzer.analyzer_id, MissingExplanationAnalyzer)
    if load_plugins:
        registry.load_entry_points()
    return registry
