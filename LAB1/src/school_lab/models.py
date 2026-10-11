"""Доменная модель (контракт из памятки курса).

Все модели неизменяемые: frozen=True запрещает присваивание полей, а
коллекции хранятся в tuple. Важно: frozen — защита ПОВЕРХНОСТНАЯ, список
внутри frozen-объекта остался бы изменяемым, поэтому списков здесь нет.

Корректный Submission создаётся через parsing.parse_submission. Прямой
вызов конструктора инварианты НЕ проверяет — это граница валидации.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvidenceField = Literal["text", "code"]
FindingKind = Literal["similarity", "rubric_feedback", "processing_error"]
AnalysisMode = Literal["baseline", "stub"]


@dataclass(frozen=True, slots=True)
class AIDeclaration:
    used: bool
    tool: str | None
    purpose: str | None
    verified_by_student: bool  # заявление студента, а не доказанный факт


@dataclass(frozen=True, slots=True)
class Submission:
    schema_version: int
    submission_id: str
    student_id: str
    assignment_id: str
    submitted_at: str  # исходная строка из JSON (уже проверена: ISO 8601 с часовым поясом)
    text: str  # хранится как есть, со всеми переводами строк — на него ссылается evidence
    code: str
    template_id: str | None
    ai_declaration: AIDeclaration


@dataclass(frozen=True, slots=True)
class Assignment:
    assignment_id: str
    allowed_template: str
    requirements: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Evidence:
    """Включительный диапазон строк ИСХОДНОГО поля, нумерация с 1."""

    submission_id: str
    field: EvidenceField
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class Finding:
    kind: FindingKind
    score: float | None  # конечное число 0..1 или None («метрика не определена»)
    evidence: tuple[Evidence, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    report_id: str  # идентификатор ЗАПУСКА: у двух одинаковых анализов разный
    submission_id: str
    submission_hash: str  # к какой именно версии сдачи относится отчёт
    analyzer_id: str
    analyzer_version: str
    config_hash: str  # с какой конфигурацией получен результат
    findings: tuple[Finding, ...]
    created_at: str
    review_required: bool  # решение принимает преподаватель, отчёт лишь направляет
