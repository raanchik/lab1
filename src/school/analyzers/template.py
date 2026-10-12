from __future__ import annotations

from collections.abc import Iterable

from ..lines import split_lines
from ..models import AnalysisReport, Evidence, Submission
from .base import AnalysisContext

ALLOWED_NOTE = "Строки совпадают с разрешённым шаблоном задания — это допустимо."


class TemplateAnalyzer:
    """Находит в коде строки, ТОЧНО совпадающие со строками разрешённого шаблона.

    similarity = совпавшие непустые строки кода / все непустые строки кода.
    Номера строк в evidence — по исходному коду (пустые строки тоже считаются).
    """

    analyzer_id = "template"
    analyzer_version = "1.0.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        template = {line for line in split_lines(context.assignment.allowed_template) if line.strip()}
        numbered = [
            (number, line)
            for number, line in enumerate(split_lines(submission.code), start=1)
            if line.strip()
        ]

        if not template:
            return self._report(submission, 0.0, ("У задания нет разрешённого шаблона.",), ())

        matched = [number for number, line in numbered if line in template]
        similarity = len(matched) / len(numbered) if numbered else 0.0
        evidence = tuple(
            Evidence("code", start, end, ALLOWED_NOTE) for start, end in _group_ranges(matched)
        )
        feedback = (
            f"С разрешённым шаблоном совпадают {len(matched)} из {len(numbered)} "
            f"непустых строк кода (similarity={similarity:.2f}).",
            "Совпадение с разрешённым шаблоном разрешено и не считается заимствованием.",
        )
        return self._report(submission, similarity, feedback, evidence)

    def _report(
        self,
        submission: Submission,
        similarity: float,
        feedback: tuple[str, ...],
        evidence: tuple[Evidence, ...],
    ) -> AnalysisReport:
        return AnalysisReport(
            submission_id=submission.submission_id,
            analyzer_id=self.analyzer_id,
            analyzer_version=self.analyzer_version,
            similarity=similarity,
            rubric_feedback=feedback,
            evidence=evidence,
        )


def _group_ranges(numbers: Iterable[int]) -> list[tuple[int, int]]:
    """[3, 4, 5, 9, 10] -> [(3, 5), (9, 10)] — соседние строки объединяются в диапазон."""
    ranges: list[tuple[int, int]] = []
    for n in numbers:
        if ranges and ranges[-1][1] == n - 1:
            ranges[-1] = (ranges[-1][0], n)
        else:
            ranges.append((n, n))
    return ranges
