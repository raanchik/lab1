"""Контракт анализатора.

Analyzer — это Protocol (структурная типизация, «утиная типизация с проверкой
типов»): любой класс с атрибутами analyzer_id, analyzer_version и методом
analyze(submission, context) -> AnalysisReport считается анализатором.
Наследоваться ни от чего не нужно — поэтому внешний плагин может вообще
не импортировать базовый класс из нашего пакета.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import AnalysisReport, Assignment, Submission
from ..repository import SubmissionReader


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Всё, что анализатор может знать помимо самой сдачи.

    - assignment  — требования задания (в т. ч. разрешённый шаблон);
    - submissions — доступ к другим сдачам ТОЛЬКО на чтение и через интерфейс
                    (пригодится для поиска похожих работ в следующих ЛР).
    """

    assignment: Assignment
    submissions: SubmissionReader


class Analyzer(Protocol):
    @property
    def analyzer_id(self) -> str: ...

    @property
    def analyzer_version(self) -> str: ...

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport: ...
