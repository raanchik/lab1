"""Этап Б: ОДИН набор контрактных тестов для обоих источников.

Фикстура make_source параметризована: каждый тест выполняется дважды —
для JSONL-файла и для источника в памяти. Если появится третий источник
(например, БД), его достаточно добавить в params.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from school.sources import (
    InMemorySubmissionSource,
    JsonlSubmissionSource,
    SourceNotOpenError,
    SubmissionSource,
)

SourceFactory = Callable[[list[str]], SubmissionSource]


@pytest.fixture(params=["jsonl", "memory"])
def make_source(request: pytest.FixtureRequest, tmp_path: Path) -> SourceFactory:
    def factory(lines: list[str]) -> SubmissionSource:
        if request.param == "jsonl":
            path = tmp_path / "data.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return JsonlSubmissionSource(path)
        return InMemorySubmissionSource(lines)

    return factory


def test_records_in_order_with_positions(make_source: SourceFactory) -> None:
    with make_source(['{"a": 1}', '{"b": 2}']) as source:
        records = list(source.records())
    assert [(r.position, r.raw) for r in records] == [(1, '{"a": 1}'), (2, '{"b": 2}')]


def test_blank_lines_skipped_but_numbering_kept(make_source: SourceFactory) -> None:
    with make_source(['{"a": 1}', "", "   ", '{"b": 2}']) as source:
        positions = [r.position for r in source.records()]
    assert positions == [1, 4]


def test_records_outside_with_is_an_error(make_source: SourceFactory) -> None:
    source = make_source(['{"a": 1}'])
    with pytest.raises(SourceNotOpenError):
        list(source.records())


def test_closed_after_normal_exit(make_source: SourceFactory) -> None:
    source = make_source(['{"a": 1}'])
    with source:
        assert source.is_open
        list(source.records())
    assert not source.is_open


def test_closed_after_exception(make_source: SourceFactory) -> None:
    source = make_source(['{"a": 1}', '{"b": 2}'])
    with pytest.raises(ZeroDivisionError):
        with source:
            for _ in source.records():
                1 / 0
    assert not source.is_open  # ресурс освобождён, исключение не проглочено


def test_closed_after_early_break(make_source: SourceFactory) -> None:
    source = make_source(['{"a": 1}', '{"b": 2}', '{"c": 3}'])
    with source:
        for record in source.records():
            if record.position == 1:
                break
    assert not source.is_open


def test_jsonl_really_closes_the_file(tmp_path: Path) -> None:
    """Проверяем не флаг, а сам файловый объект ОС."""
    path = tmp_path / "data.jsonl"
    path.write_text('{"a": 1}\n', encoding="utf-8")
    source = JsonlSubmissionSource(path)
    with pytest.raises(RuntimeError):
        with source:
            file_object = source._file  # доступ к приватному полю допустим в тесте ресурса
            raise RuntimeError("досрочная ошибка")
    assert file_object is not None and file_object.closed


def test_missing_file_raises_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        with JsonlSubmissionSource(tmp_path / "nope.jsonl"):
            pass
