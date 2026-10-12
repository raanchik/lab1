"""Типизированный декоратор измерения времени (углублённый уровень Core).

ParamSpec + TypeVar сохраняют сигнатуру: mypy знает, что обёрнутая функция
принимает те же аргументы и возвращает тот же тип, что и исходная.
functools.wraps сохраняет метаданные: __name__, __qualname__, __doc__,
__module__ и ссылку на оригинал в __wrapped__.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger("school.timing")


def timed(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:  # время пишется и при исключении
            if logger.isEnabledFor(logging.DEBUG):
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.debug("%s заняла %.3f мс", func.__qualname__, elapsed_ms)

    return wrapper
