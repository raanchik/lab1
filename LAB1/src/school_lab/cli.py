"""Командная строка — тонкий адаптер.

CLI отвечает за аргументы, выбор адаптера источника, формат вывода и код
завершения. Валидация, хранение и анализ — в общих компонентах.

stdout — один машиночитаемый JSON-документ; stderr — диагностика.
Коды завершения:
    0 — всё прошло без ошибок;
    1 — есть ошибки отдельных строк или анализа (корректные записи при этом приняты);
    2 — выполнить команду нельзя: источник недоступен, неверная конфигурация.
In-memory состояние исчезает при завершении процесса (постоянное хранение — ЛР 3).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analyzers import AnalysisContext
from .app import build_application
from .errors import AnalysisFailure, SubmissionError
from .models import Assignment
from .parsing import decode_json, parse_assignments
from .registry import build_registry
from .services import import_source
from .sources import JSONLSource


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="school-lab", description="Приём учебных сдач из JSONL и анализ")
    commands = parser.add_subparsers(dest="command", required=True)

    imp = commands.add_parser("import", help="импорт файла сдач")
    imp.add_argument("path", type=Path)

    ana = commands.add_parser("analyze", help="импорт и запуск анализаторов")
    ana.add_argument("path", type=Path)
    ana.add_argument("--assignments", type=Path, required=True, help="assignments.json")
    ana.add_argument("--analyzer", action="append", dest="analyzers", help="имя анализатора (можно несколько)")
    ana.add_argument("--mode", choices=("baseline", "stub"), default="baseline")
    ana.add_argument("--config-version", default="1")
    ana.add_argument("--plugins", action="store_true", help="подключить анализаторы из entry points")

    args = parser.parse_args(argv)
    if args.command == "import":
        return _cmd_import(args.path)
    return _cmd_analyze(args)


def _cmd_import(path: Path) -> int:
    app = build_application()
    try:
        summary = import_source(JSONLSource(path), app.submission_service)
    except (OSError, UnicodeError) as exc:
        return _fatal("source_unavailable", str(exc))
    _emit(summary.to_dict())
    return 1 if summary.errors else 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    # 1. Конфигурация проверяется ДО начала работы.
    try:
        assignments = _load_assignments(args.assignments)
    except (OSError, UnicodeError) as exc:
        return _fatal("source_unavailable", str(exc))
    except SubmissionError as exc:
        return _fatal("invalid_assignments", str(exc))
    try:
        registry = build_registry(load_plugins=args.plugins)
    except AnalysisFailure as exc:
        return _fatal(exc.code, str(exc))
    names: list[str] = args.analyzers or list(registry.names())
    unknown = [name for name in names if name not in registry]
    if unknown:
        known = ", ".join(registry.names())
        return _fatal("unknown_analyzer", f"Неизвестные анализаторы: {', '.join(unknown)}; доступны: {known}")

    # 2. Импорт.
    app = build_application(registry=registry)
    try:
        summary = import_source(JSONLSource(args.path), app.submission_service)
    except (OSError, UnicodeError) as exc:
        return _fatal("source_unavailable", str(exc))

    # 3. Анализ принятых сдач. Ошибка одного анализатора не мешает остальным.
    reports: list[dict[str, Any]] = []
    analysis_errors: list[dict[str, Any]] = []
    for submission_id in summary.accepted:
        submission = app.repository.get(submission_id)
        assert submission is not None  # только что принята
        assignment = assignments.get(submission.assignment_id)
        if assignment is None:
            analysis_errors.append({
                "submission_id": submission_id, "code": "unknown_assignment",
                "field": "assignment_id", "message": f"Задание {submission.assignment_id} не найдено",
            })
            continue
        context = AnalysisContext(assignment, mode=args.mode, config_version=args.config_version)
        for name in names:
            try:
                reports.append(asdict(app.analysis_service.run(submission_id, name, context)))
            except AnalysisFailure as exc:
                analysis_errors.append({"submission_id": submission_id, **exc.to_dict()})

    _emit({"import": summary.to_dict(), "reports": reports, "analysis_errors": analysis_errors})
    return 1 if summary.errors or analysis_errors else 0


def _load_assignments(path: Path) -> dict[str, Assignment]:
    return parse_assignments(decode_json(path.read_text(encoding="utf-8")))


def _emit(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _fatal(code: str, message: str) -> int:
    print(json.dumps({"code": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
