"""Доменная модель.

Все модели — неизменяемые dataclass (frozen=True). Это гарантирует, что
ни сервис приёма, ни анализаторы не могут «случайно» поправить сдачу:
попытка присваивания поля вызовет FrozenInstanceError. Коллекции хранятся
в tuple, а не в list, по той же причине.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

EvidenceSource = Literal["text", "code"]


@dataclass(frozen=True, slots=True)
class AIDeclaration:
    used: bool
    description: str = ""
    tools: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"used": self.used, "description": self.description, "tools": list(self.tools)}


@dataclass(frozen=True, slots=True)
class Submission:
    """Одна версия сдачи. Новая версия работы = новый submission_id."""

    submission_id: str
    student_id: str
    assignment_id: str
    submitted_at: datetime  # всегда с часовым поясом (гарантирует парсер)
    text: str
    code: str
    ai_declaration: AIDeclaration

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "student_id": self.student_id,
            "assignment_id": self.assignment_id,
            "submitted_at": self.submitted_at.isoformat(),
            "text": self.text,
            "code": self.code,
            "ai_declaration": self.ai_declaration.to_dict(),
        }

    def content_hash(self) -> str:
        """SHA-256 канонического JSON-представления.

        Канонический = ключи отсортированы, без лишних пробелов, UTF-8.
        Поэтому порядок полей во входной строке и форматирование на хеш не влияют.
        """
        canonical = json.dumps(
            self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Assignment:
    assignment_id: str
    title: str = ""
    allowed_template: str = ""  # код, который студентам разрешено использовать как есть


@dataclass(frozen=True, slots=True)
class Evidence:
    """Фрагмент исходного содержимого, на который опирается вывод анализатора.

    Номера строк — 1-based и включительные, относятся к ИСХОДНОМУ text/code.
    """

    source: EvidenceSource
    start_line: int
    end_line: int
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    submission_id: str
    analyzer_id: str
    analyzer_version: str
    score: float | None = None
    similarity: float | None = None
    rubric_feedback: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "analyzer_id": self.analyzer_id,
            "analyzer_version": self.analyzer_version,
            "score": self.score,
            "similarity": self.similarity,
            "rubric_feedback": list(self.rubric_feedback),
            "evidence": [e.to_dict() for e in self.evidence],
        }
