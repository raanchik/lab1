"""Источники сдач.

Источник отдаёт «сырые» записи (RawRecord): номер строки и текст.
Разбор и валидацию делает сервис приёма — так ошибки формата из любого
источника обрабатываются одинаково и всегда знают номер строки.

Оба источника — контекстные менеджеры с одинаковым контрактом:
  with source:                # открыть ресурс
      for record in source.records():
          ...
                              # ресурс закрыт, даже если внутри было исключение или break

Ресурсом управляет тот, кто пишет `with` (CLI или тест), а не сервис приёма.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self, TextIO


@dataclass(frozen=True, slots=True)
class RawRecord:
    position: int  # номер строки в исходном файле, с 1
    raw: str


class SubmissionSource(Protocol):
    @property
    def is_open(self) -> bool: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def records(self) -> Iterator[RawRecord]: ...


class SourceNotOpenError(RuntimeError):
    """Программная ошибка: records() вызвали вне блока with."""


class JsonlSubmissionSource:
    def __init__(self, path: str | Path, *, encoding: str = "utf-8") -> None:
        self._path = Path(path)
        self._encoding = encoding
        self._file: TextIO | None = None

    @property
    def is_open(self) -> bool:
        return self._file is not None and not self._file.closed

    def __enter__(self) -> Self:
        if self.is_open:
            raise RuntimeError("Источник уже открыт")
        self._file = self._path.open("r", encoding=self._encoding)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._file is not None:
            self._file.close()
        # Возвращаем None (а не True): исключение не «проглатывается», а летит дальше.

    def records(self) -> Iterator[RawRecord]:
        if self._file is None or self._file.closed:
            raise SourceNotOpenError("Используйте: with JsonlSubmissionSource(path) as source: ...")
        for number, line in enumerate(self._file, start=1):
            text = line.rstrip("\r\n")
            if text.strip():  # пустые строки пропускаем, но нумерацию не сбиваем
                yield RawRecord(number, text)


class InMemorySubmissionSource:
    """Источник из памяти: для тестов и для подмены файла."""

    def __init__(self, items: Iterable[str | Mapping[str, Any]]) -> None:
        # Словари сериализуем в JSON, чтобы они прошли тот же путь разбора, что и файл.
        self._items: tuple[str, ...] = tuple(
            item if isinstance(item, str) else json.dumps(dict(item), ensure_ascii=False)
            for item in items
        )
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def __enter__(self) -> Self:
        if self._open:
            raise RuntimeError("Источник уже открыт")
        self._open = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._open = False

    def records(self) -> Iterator[RawRecord]:
        if not self._open:
            raise SourceNotOpenError("Используйте: with InMemorySubmissionSource(...) as source: ...")
        for number, text in enumerate(self._items, start=1):
            if not self._open:  # источник закрыли посреди итерации
                return
            if text.strip():
                yield RawRecord(number, text)
