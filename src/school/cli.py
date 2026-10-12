"""Командная строка — тонкий адаптер над доменом.

CLI отвечает только за ввод-вывод: открыть файл, вызвать доменные функции,
напечатать JSON и вернуть код выхода. Вся логика — в intake/parser/analysis.

Коды выхода:
  0 — всё принято без ошибок;
  1 — импорт выполнен, но в отчёте есть ошибки строк/анализа;
  2 — команду выполнить нельзя (нет файла, неверная конфигурация).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .analyzers.registry import build_default_registry
from .app import build_app
from .errors import ErrorCode, ErrorDetail, SchoolError
from .intake import import_records
from .models import Assignment
from .parser import parse_assignments, parse_json_line
from .sources import JsonlSubmissionSource


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="school", description="Приём сдач и анализаторы")
    commands = parser.add_subparsers(dest="command", required=True)

    imp = commands.add_parser("import", help="импортировать JSONL со сдачами")
    imp.add_argument("path", type=Path)

    ana = commands.add_parser("analyze", help="импортировать и запустить анализаторы")
    ana.add_argument("path", type=Path)
    ana.add_argument("--assignments", type=Path, required=True)
    ana.add_argument("--analyzer", action="append", dest="analyzers", help="id анализатора (можно несколько)")
    ana.add_argument("--plugins", action="store_true", help="подключить анализаторы из entry points")

    args = parser.parse_args(argv)
    if args.command == "import":
        return _cmd_import(args.path)
    return _cmd_analyze(args.path, args.assignments, args.analyzers, args.plugins)


def _cmd_import(path: Path) -> int:
    app = build_app()
    try:
        with JsonlSubmissionSource(path) as source:
            report = import_records(source.records(), app.intake)
    except (OSError, UnicodeDecodeError) as exc:
        return _fatal(ErrorCode.IO_ERROR, "path", f"Не удалось прочитать '{path}': {exc}")
    _print(report.to_dict())
    return 1 if report.errors else 0


def _cmd_analyze(path: Path, assignments_path: Path, analyzer_ids: list[str] | None, plugins: bool) -> int:
    try:
        assignments = _load_assignments(assignments_path)
        registry = build_default_registry(load_plugins=plugins)
    except SchoolError as error:
        return _fatal_details(error.details)
    except (OSError, UnicodeDecodeError) as exc:
        return _fatal(ErrorCode.IO_ERROR, "assignments", f"Не удалось прочитать '{assignments_path}': {exc}")

    ids = analyzer_ids or list(registry.ids())
    unknown = [i for i in ids if i not in registry]
    if unknown:  # проверяем конфигурацию ДО начала работы
        message = f"Неизвестные анализаторы: {', '.join(unknown)}. Доступны: {', '.join(registry.ids())}"
        return _fatal(ErrorCode.UNKNOWN_ANALYZER, "analyzer", message)

    app = build_app(assignments, registry=registry)
    try:
        with JsonlSubmissionSource(path) as source:
            report = import_records(source.records(), app.intake)
    except (OSError, UnicodeDecodeError) as exc:
        return _fatal(ErrorCode.IO_ERROR, "path", f"Не удалось прочитать '{path}': {exc}")

    reports: list[dict[str, Any]] = []
    analysis_errors: list[dict[str, Any]] = []
    for submission_id in report.accepted:
        submission = app.repository.get_submission(submission_id)
        assert submission is not None
        run = app.analysis.analyze_many(submission, ids)
        reports.extend(r.to_dict() for r in run.reports)
        analysis_errors.extend({"submission_id": submission_id, **e.to_dict()} for e in run.errors)

    _print({"import": report.to_dict(), "reports": reports, "analysis_errors": analysis_errors})
    return 1 if report.errors or analysis_errors else 0


def _load_assignments(path: Path) -> dict[str, Assignment]:
    return parse_assignments(parse_json_line(path.read_text(encoding="utf-8")))


def _print(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _fatal(code: ErrorCode, field: str, message: str) -> int:
    return _fatal_details([ErrorDetail(code, field, message)])


def _fatal_details(details: Sequence[ErrorDetail]) -> int:
    print(json.dumps({"errors": [d.to_dict() for d in details]}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
