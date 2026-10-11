"""Контракт анализатора, проверка отчёта и встроенные анализаторы.

Analyzer — Protocol: анализатором считается ЛЮБОЙ класс с analyzer_id,
analyzer_version и analyze(submission, context) -> AnalysisReport.
Наследоваться ни от чего не нужно, поэтому внешний плагин не зависит
от базовых классов этого пакета.

Protocol проверяет только форму (mypy), но не поведение: он не гарантирует,
что evidence указывает на существующие строки. Поэтому есть validate_report
(проверка на границе каждого вызова) и контрактные тесты (проверка заранее).

Нумерация строк везде одна — str.splitlines(), нумерация с 1, по ИСХОДНОМУ
тексту (без strip, без удаления комментариев). Конечный перевод строки не
создаёт лишнюю пустую строку.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from .errors import AnalysisFailure
from .hashing import stable_hash, submission_hash
from .models import AnalysisMode, AnalysisReport, Assignment, Evidence, EvidenceField, Finding, Submission

FINDING_KINDS = frozenset({"similarity", "rubric_feedback", "processing_error"})


# ------------------------------------------------------------ контракт


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Требования задания + явная неизменяемая конфигурация анализа.

    config_hash = SHA-256 от config_payload(). Если поменять шаблон задания,
    режим или config_version, изменится config_hash, и старый отчёт формально
    перестанет соответствовать новой конфигурации (упражнение 7).
    """

    assignment: Assignment
    mode: AnalysisMode = "baseline"
    config_version: str = "1"

    def config_payload(self) -> dict[str, object]:
        return {"assignment": asdict(self.assignment), "mode": self.mode, "config_version": self.config_version}

    def config_hash(self) -> str:
        return stable_hash(self.config_payload())


class Analyzer(Protocol):
    @property
    def analyzer_id(self) -> str: ...

    @property
    def analyzer_version(self) -> str: ...

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport: ...


# ---------------------------------------------------- чистые функции


def nonempty_line_numbers(text: str) -> tuple[int, ...]:
    """Номера (с 1) строк, в которых есть непробельный символ."""
    return tuple(number for number, line in enumerate(text.splitlines(), 1) if line.strip())


def to_ranges(numbers: Iterable[int]) -> tuple[tuple[int, int], ...]:
    """(1, 2, 3, 7, 8) -> ((1, 3), (7, 8)): соседние строки склеиваются в диапазон."""
    ranges: list[tuple[int, int]] = []
    for number in numbers:
        if ranges and ranges[-1][1] == number - 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return tuple(ranges)


def template_ranges(source_code: str, template: str) -> tuple[tuple[int, int], ...]:
    """Все вхождения шаблона как БЛОКА подряд идущих строк, без нормализации пробелов.

    Пустой или пробельный шаблон ничего не находит (иначе он «совпал бы» со всем файлом).
    """
    if not template.strip():
        return ()
    source_lines = source_code.splitlines()
    template_lines = template.splitlines()
    width = len(template_lines)
    return tuple(
        (index + 1, index + width)
        for index in range(len(source_lines) - width + 1)
        if source_lines[index:index + width] == template_lines
    )


# --------------------------------------------- отчёт и его проверка


def validate_report(report: object, value: Submission, ctx: AnalysisContext) -> None:
    """Проверка отчёта на границе. Аннотация -> AnalysisReport сама ничего не гарантирует."""
    if not isinstance(report, AnalysisReport):
        raise AnalysisFailure("Ожидается AnalysisReport")
    if report.submission_id != value.submission_id or report.submission_hash != submission_hash(value):
        raise AnalysisFailure("Отчёт ссылается на другую версию сдачи")
    if report.config_hash != ctx.config_hash():
        raise AnalysisFailure("Отчёт использует другую конфигурацию")
    if not report.report_id or not report.analyzer_id or not report.analyzer_version:
        raise AnalysisFailure("Идентификаторы отчёта и анализатора обязательны")
    if type(report.review_required) is not bool:
        raise AnalysisFailure("review_required должен быть bool")
    try:
        created = datetime.fromisoformat(report.created_at)
    except (ValueError, TypeError) as exc:
        raise AnalysisFailure("Время отчёта имеет неверный формат") from exc
    if created.tzinfo is None or created.utcoffset() is None:
        raise AnalysisFailure("Часовой пояс времени отчёта обязателен")
    for finding in report.findings:
        if finding.kind not in FINDING_KINDS:
            raise AnalysisFailure(f"Неизвестный kind: {finding.kind!r}")
        score = finding.score
        if score is not None and (
            type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
        ):
            raise AnalysisFailure("score должен быть конечным числом 0–1 либо None (bool не допускается)")
        if not isinstance(finding.explanation, str) or not finding.explanation.strip():
            raise AnalysisFailure("Объяснение наблюдения обязательно")
        for ev in finding.evidence:
            if ev.submission_id != value.submission_id or ev.field not in ("text", "code"):
                raise AnalysisFailure("Evidence ссылается на неизвестный объект или поле")
            if type(ev.start_line) is not int or type(ev.end_line) is not int:
                raise AnalysisFailure("Номер строки должен быть int")
            total = len(getattr(value, ev.field).splitlines())
            if not 1 <= ev.start_line <= ev.end_line <= total:
                raise AnalysisFailure(
                    f"Evidence {ev.field}:{ev.start_line}-{ev.end_line} выходит за границы 1..{total}"
                )


def _new_report_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


def make_report(
    value: Submission,
    ctx: AnalysisContext,
    analyzer_id: str,
    version: str,
    findings: tuple[Finding, ...],
    *,
    review_required: bool = False,
    id_factory: Callable[[], str] = _new_report_id,
    clock: Callable[[], datetime] = _utc_now,
) -> AnalysisReport:
    """Собирает отчёт и сразу проверяет его.

    id_factory и clock можно подменить в тестах, чтобы получить полностью
    воспроизводимый отчёт без глобальной подмены системного времени.
    """
    report = AnalysisReport(
        report_id=id_factory(),
        submission_id=value.submission_id,
        submission_hash=submission_hash(value),
        analyzer_id=analyzer_id,
        analyzer_version=version,
        config_hash=ctx.config_hash(),
        findings=findings,
        created_at=clock().isoformat(),
        review_required=review_required,
    )
    validate_report(report, value, ctx)
    return report


# ------------------------------------------------------ анализаторы


class LengthAnalyzer:
    """Считает непустые строки text и code. Объём не равен качеству, поэтому score=None."""

    analyzer_id = "length"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        text_lines = nonempty_line_numbers(submission.text)
        code_lines = nonempty_line_numbers(submission.code)
        # Явный тип нужен mypy: литерал "text" в кортеже иначе выводится как str,
        # а Evidence.field принимает только Literal["text", "code"].
        fields: tuple[tuple[EvidenceField, tuple[int, ...]], ...] = (
            ("text", text_lines),
            ("code", code_lines),
        )
        evidence = tuple(
            Evidence(submission.submission_id, field_name, start, end)
            for field_name, numbers in fields
            for start, end in to_ranges(numbers)
        )
        finding = Finding(
            kind="rubric_feedback",
            score=None,
            evidence=evidence,
            explanation=(
                f"Непустые строки: text={len(text_lines)}, code={len(code_lines)}. "
                "Длина не оценивает корректность решения."
            ),
        )
        return make_report(submission, context, self.analyzer_id, self.analyzer_version, (finding,))


class TemplateAnalyzer:
    """Ищет точные вхождения разрешённого шаблона в код. Совпадение разрешено и не является нарушением."""

    analyzer_id = "template"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        if submission.assignment_id != context.assignment.assignment_id:
            raise AnalysisFailure("Контекст относится к другому заданию", code="context_mismatch", field=self.analyzer_id)
        ranges = template_ranges(submission.code, context.assignment.allowed_template)
        evidence = tuple(Evidence(submission.submission_id, "code", start, end) for start, end in ranges)
        explanation = (
            f"Найдены разрешённые блоки шаблона: {len(ranges)}. "
            "Это допустимое совпадение, а не основание для санкций."
            if ranges
            else "Точное совпадение с разрешённым шаблоном не найдено. Нечёткое сходство не проверялось."
        )
        finding = Finding("similarity", None, evidence, explanation)
        return make_report(submission, context, self.analyzer_id, self.analyzer_version, (finding,))


class MissingExplanationAnalyzer:
    """Упражнение 3: код есть, а текстового пояснения нет."""

    analyzer_id = "missing_explanation"
    analyzer_version = "1.0"

    def analyze(self, submission: Submission, context: AnalysisContext) -> AnalysisReport:
        missing = bool(submission.code.strip()) and not submission.text.strip()
        explanation = (
            "Код присутствует, но текстовое пояснение пустое."
            if missing
            else "Текстовое пояснение присутствует либо код отсутствует."
        )
        finding = Finding("rubric_feedback", None, (), explanation)
        return make_report(
            submission, context, self.analyzer_id, self.analyzer_version, (finding,), review_required=missing
        )
