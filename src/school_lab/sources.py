"""Источники сдач.

Контракт источника: метод open() возвращает КОНТЕКСТНЫЙ МЕНЕДЖЕР, который
выдаёт итератор записей SourceRecord. Использование:

    with source.open() as records:
        for record in records:
            ...
    # здесь ресурс уже освобождён: и после полного чтения, и после break, и после исключения

Владение ресурсом. Файл открывает и закрывает источник (внутри open()),
а сервис только потребляет записи. Нельзя прятать open() внутри голого
генератора: после break такой генератор остаётся приостановленным, и файл
закроется лишь «когда-нибудь» сборщиком мусора — это не гарантия.

Источник отвечает только за синтаксис: каждая запись — это номер строки и
либо разобранный объект, либо ошибка invalid_json. Схему проверяет parser.
Пустая физическая строка по принятой политике тоже invalid_json (с продолжением).

Ошибка ОТКРЫТИЯ (нет файла) — не ошибка записи: продолжать невозможно, поэтому
OSError не превращается в строку отчёта, а летит из open().
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from .errors import SubmissionError
from .parsing import decode_json


@dataclass(frozen=True, slots=True)
class SourceRecord:
    line_no: int
    raw: object = None
    error: SubmissionError | None = None


class SubmissionSource(Protocol):
    def open(self) -> AbstractContextManager[Iterator[SourceRecord]]: ...


def _decode_lines(lines: Iterable[str]) -> Iterator[SourceRecord]:
    for number, line in enumerate(lines, start=1):
        try:
            raw = decode_json(line)
        except SubmissionError as exc:
            yield SourceRecord(number, error=exc)
        else:
            yield SourceRecord(number, raw=raw)


class InMemorySource:
    """Источник из памяти. Выдаёт КОПИИ, чтобы потребитель не испортил исходную коллекцию."""

    def __init__(self, values: Iterable[object]) -> None:
        self._values = copy.deepcopy(list(values))

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        def records() -> Iterator[SourceRecord]:
            for number, raw in enumerate(self._values, start=1):
                yield SourceRecord(number, raw=copy.deepcopy(raw))

        yield records()


class JSONLSource:
    """Файл JSONL: одна строка — одна сдача. Читается построчно, без загрузки целиком."""

    def __init__(self, path: Path | str, *, encoding: str = "utf-8") -> None:
        self.path = Path(path)
        self.encoding = encoding
        self.last_closed: bool | None = None  # диагностика для тестов освобождения ресурса

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        handle = self.path.open("r", encoding=self.encoding)  # OSError здесь = источник недоступен
        try:
            with handle:  # закроет файл при любом выходе из блока
                yield _decode_lines(handle)
        finally:
            self.last_closed = handle.closed


class StreamSource:
    """Источник поверх УЖЕ открытого потока (например, io.StringIO или sys.stdin).

    Отличие контракта (упражнение 5): поток открыл вызывающий код, значит
    и закрывать его — обязанность вызывающего. StreamSource поток НЕ закрывает.
    Поэтому по ресурсному поведению он не полностью эквивалентен JSONLSource,
    хотя по выдаваемым записям совпадает.
    """

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    @contextmanager
    def open(self) -> Iterator[Iterator[SourceRecord]]:
        yield _decode_lines(self._stream)
