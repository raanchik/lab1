"""Воспроизводимые замеры для отчёта.

Запуск:  python scripts/bench.py --n 5000 --repeat 5
Данные синтетические (размножение учебного корпуса с новыми ID), реальные работы не используются.

Что измеряется:
1. import    — разбор JSON + валидация + приём N сдач (сдач в секунду);
2. analyzers — среднее время одного анализа (мкс), включая make_report и validate_report;
3. timed     — накладные расходы декоратора @timed, измеренные ИЗОЛИРОВАННО на пустой функции
               (на целом run() разница тонет в шуме ±5% и может выйти даже отрицательной);
4. slots     — память на объект Submission со slots=True и без (tracemalloc).
"""

from __future__ import annotations

import argparse
import copy
import json
import platform
import time
import timeit
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict, make_dataclass
from pathlib import Path

from school_lab.analyzers import AnalysisContext
from school_lab.app import build_application
from school_lab.models import Assignment, Submission
from school_lab.parsing import parse_submission
from school_lab.services import import_source
from school_lab.sources import InMemorySource
from school_lab.timing import timed

DATA = Path(__file__).resolve().parents[1] / "data" / "submissions.jsonl"


def corpus(n: int) -> list[dict[str, object]]:
    base = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
    result = []
    for i in range(n):
        item = copy.deepcopy(base[i % len(base)])
        item["submission_id"] = f"bench-{i}"
        result.append(item)
    return result


def best_of(repeat: int, func: Callable[[], object]) -> float:
    """Минимум из нескольких прогонов — наименее зашумлённая оценка."""
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)
    return min(times)


def bytes_per_object(cls: type, values: list[dict[str, object]]) -> float:
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    objects = [cls(**v) for v in values]
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    total = sum(stat.size_diff for stat in after.compare_to(before, "filename"))
    del objects
    return total / len(values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()

    raws = corpus(args.n)
    context = AnalysisContext(Assignment("assignment-01", "from typing import Iterable\n", ("Наличие функции solve",)))

    def do_import() -> None:
        import_source(InMemorySource(raws), build_application().submission_service)

    import_s = best_of(args.repeat, do_import)

    app = build_application()
    import_source(InMemorySource(raws), app.submission_service)
    ids = [s.submission_id for s in app.repository]

    analyzers = {}
    for name in app.registry.names():
        seconds = best_of(args.repeat, lambda name=name: [app.analysis_service.run(i, name, context) for i in ids])
        analyzers[name] = round(seconds / len(ids) * 1e6, 1)

    def plain(x: int) -> int:
        return x

    decorated = timed(plain)
    calls = 200_000
    plain_us = min(timeit.repeat(lambda: plain(1), number=calls, repeat=args.repeat)) / calls * 1e6
    timed_us = min(timeit.repeat(lambda: decorated(1), number=calls, repeat=args.repeat)) / calls * 1e6
    overhead_us = timed_us - plain_us

    # Плоские поля для сравнения памяти slots / без slots (вложенную декларацию берём как есть).
    flat = [asdict(parse_submission(r)) for r in raws[:2000]]
    field_names = list(Submission.__dataclass_fields__)
    no_slots_cls = make_dataclass("NoSlots", field_names, frozen=True)
    slots_cls = make_dataclass("Slots", field_names, frozen=True, slots=True)

    print(json.dumps({
        "python": platform.python_version(),
        "machine": platform.machine(),
        "n": args.n,
        "repeat": args.repeat,
        "import_records_per_s": round(args.n / import_s),
        "analyzer_us_per_run": analyzers,
        "timed_overhead_us_per_call": round(overhead_us, 3),
        "timed_overhead_percent_of_length_run": round(overhead_us / analyzers["length"] * 100, 2),
        "bytes_per_submission_no_slots": round(bytes_per_object(no_slots_cls, flat)),
        "bytes_per_submission_slots": round(bytes_per_object(slots_cls, flat)),
        "note": "best-of-repeat; DEBUG-логирование выключено; память — только сам объект модели, без строк полей",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
