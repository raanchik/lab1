"""Внешний анализатор: при used=true AI-декларация должна быть непустой.

Он НЕ наследуется ни от какого базового класса пакета school — ему достаточно
соответствовать протоколу Analyzer (analyzer_id, analyzer_version, analyze).
Центральный сервис для его подключения не меняется.
"""

from __future__ import annotations

from school.analyzers import AnalysisContext
from school.models import AnalysisReport, Submission


class AIDeclarationAnalyzer:
    analyzer_id = "ai_declaration"
    analyzer_version = "1.0.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        declaration = submission.ai_declaration
        if not declaration.used:
            score, message = 1.0, "AI не использовался — описание не требуется."
        elif declaration.description.strip():
            score, message = 1.0, "AI использовался, декларация заполнена."
        else:
            score, message = 0.0, "AI использовался (used=true), но описание в декларации пустое."
        return AnalysisReport(
            submission_id=submission.submission_id,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            score=score,
            rubric_feedback=(message,),
        )
