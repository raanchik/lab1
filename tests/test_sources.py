"""Этап Б: ОДИН набор контрактных тестов для всех источников (+ упражнение 5).

Фикстура make_source параметризована: каждый тест выполняется для
InMemorySource, JSONLSource и StreamSource. Новый источник добавляется в params.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from helpers import PUBLIC_SUBMISSIONS

from school_lab.sources import InMemorySource, JSONLSource, StreamSource, SubmissionSource

SourceFactory = Callable[[list[str]], SubmissionSource]


@pytest.fixture(params=["memory", "jsonl", "stream"])
def make_source(request: pytest.FixtureRequest, tmp_path: Path) -> SourceFactory:
    def factory(lines: list[str]) -> SubmissionSource:
        if request.param == "memory":
            return InMemorySource([json.loads(line) for line in lines])
        text = "".join(line + "\n" for line in lines)
        if request.param == "jsonl":
            path = tmp_path / "data.jsonl"
            path.write_text(text, encoding="utf-8")
            return JSONLSource(path)
        return StreamSource(io.StringIO(text))

    return factory


def as_lines(values: list[dict[str, object]]) -> list[str]:
    return [json.dumps(v, ensure_ascii=False) for v in values]


def test_source_preserves_order_numbers_and_data(make_source: SourceFactory) -> None:
    with make_source(as_lines(PUBLIC_SUBMISSIONS)).open() as records:
        loaded = list(records)  # накопление допустимо только для малого тестового набора
    assert [r.line_no for r in loaded] == list(range(1, len(PUBLIC_SUBMISSIONS) + 1))
    assert [r.raw for r in loaded] == PUBLIC_SUBMISSIONS
    assert all(r.error is None for r in loaded)


def test_source_is_reopenable(make_source: SourceFactory) -> None:
    source = make_source(as_lines(PUBLIC_SUBMISSIONS[:2]))
    with source.open() as records:
        first = [r.raw for r in records]
    if isinstance(source, StreamSource):
        pytest.skip("StreamSource читает чужой поток один раз — это отличие зафиксировано в контракте")
    with source.open() as records:
        assert [r.raw for r in records] == first


def test_consumer_cannot_change_memory_source() -> None:
    source = InMemorySource(PUBLIC_SUBMISSIONS[:1])
    with source.open() as records:
        record = next(records)
        assert isinstance(record.raw, dict)
        record.raw["student_id"] = "испорчено"
    with source.open() as records:
        again = next(records).raw
    assert isinstance(again, dict) and again["student_id"] == PUBLIC_SUBMISSIONS[0]["student_id"]


# ------------------------------------------ JSONL: синтаксис и ресурс


def write(tmp_path: Path, text: str) -> JSONLSource:
    path = tmp_path / "data.jsonl"
    path.write_text(text, encoding="utf-8")
    return JSONLSource(path)


def test_broken_and_blank_lines_are_records_with_errors(tmp_path: Path) -> None:
    source = write(tmp_path, '{"a": 1}\n{broken\n\n{"b": 2}\n')
    with source.open() as records:
        loaded = list(records)
    assert [(r.line_no, r.error.code if r.error else None) for r in loaded] == [
        (1, None), (2, "invalid_json"), (3, "invalid_json"), (4, None),
    ]


def test_file_closed_after_full_read(tmp_path: Path) -> None:
    source = write(tmp_path, '{"a": 1}\n')
    with source.open() as records:
        list(records)
    assert source.last_closed is True


def test_file_closed_after_early_exit(tmp_path: Path) -> None:
    source = write(tmp_path, '{"a": 1}\n{"b": 2}\n{"c": 3}\n')
    with source.open() as records:
        for record in records:
            if record.line_no == 1:
                break  # потребление прекращено раньше конца файла
    assert source.last_closed is True


def test_file_closed_after_consumer_exception(tmp_path: Path) -> None:
    source = write(tmp_path, '{"a": 1}\n{"b": 2}\n')
    with pytest.raises(RuntimeError), source.open() as records:  # исключение не подавлено
        next(records)
        raise RuntimeError("ошибка потребителя прерывает обработку")
    assert source.last_closed is True


def test_missing_file_is_source_error_not_record_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError), JSONLSource(tmp_path / "nope.jsonl").open():
        pass


def test_stream_source_does_not_close_callers_stream() -> None:
    """Упражнение 5: поток открыл вызывающий — он и закрывает."""
    stream = io.StringIO('{"a": 1}\n')
    with StreamSource(stream).open() as records:
        list(records)
    assert not stream.closed
    stream.close()
