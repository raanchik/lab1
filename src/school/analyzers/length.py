from __future__ import annotations

from ..lines import count_non_empty
from ..models import AnalysisReport, Submission
from .base import AnalysisContext


class LengthAnalyzer:
    """Считает непустые строки текста и кода. Оценку не ставит (score=None)."""

    analyzer_id = "length"
    analyzer_version = "1.0.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        text_lines = count_non_empty(submission.text)
        code_lines = count_non_empty(submission.code)
        return AnalysisReport(
            submission_id=submission.submission_id,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            score=None,
            rubric_feedback=(
                f"Текст: {text_lines} непустых строк.",
                f"Код: {code_lines} непустых строк.",
                "Анализатор только измеряет объём и не выставляет оценку.",
            ),
        )
