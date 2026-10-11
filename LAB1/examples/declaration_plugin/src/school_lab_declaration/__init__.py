"""Анализатор AI-декларации — внешний плагин.

Не наследуется ни от чего из school_lab: достаточно соответствовать протоколу
Analyzer. Подключается через entry point; центральный сервис не меняется.

Что проверяет. Parser уже отклоняет used=true без tool/purpose, поэтому через
обычный приём неполная декларация не пройдёт. Анализатор всё равно проверяет
непустоту сам (Submission можно создать и в обход parser), описывает
декларацию и выставляет review_required, если:
  - декларация неполна, или
  - ИИ использован, но студент не подтвердил, что проверил результат.

Чего НЕ делает: не определяет авторство. Отсутствие заявления не доказывает,
что ИИ не использовался, а verified_by_student=true не заменяет защиту.
"""

from __future__ import annotations

from school_lab.analyzers import AnalysisContext, make_report
from school_lab.models import AnalysisReport, Finding, Submission


class DeclarationAnalyzer:
    analyzer_id = "declaration"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        declaration = submission.ai_declaration
        if not declaration.used:
            explanation = "Использование ИИ не заявлено. Авторство текста автоматически не определялось."
            review = False
        elif not (declaration.tool or "").strip() or not (declaration.purpose or "").strip():
            explanation = "Использование ИИ заявлено, но инструмент или цель не указаны."
            review = True
        else:
            explanation = f"Использование ИИ заявлено. Инструмент: {declaration.tool}; цель: {declaration.purpose}."
            review = not declaration.verified_by_student
            if review:
                explanation += " Студент не подтвердил проверку результата — нужна ручная проверка."
        finding = Finding("rubric_feedback", None, (), explanation)
        return make_report(
            submission, context, self.analyzer_id, self.analyzer_version, (finding,), review_required=review
        )
