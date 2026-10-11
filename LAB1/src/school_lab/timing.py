"""Типизированный декоратор измерения времени (углублённый уровень Core).

@timed эквивалентно function = timed(function).
- Параметры типа [**P, R] (синтаксис PEP 695, Python 3.12+) — это те же
  ParamSpec P и TypeVar R: P сохраняет типы параметров, R — тип результата.
  Поэтому mypy проверяет вызовы обёрнутой функции так же строго, как исходной.
  Обёртка Callable[..., object] эту проверку потеряла бы.
- functools.wraps копирует __name__, __qualname__, __doc__, __module__ и
  кладёт оригинал в __wrapped__ (интроспекция, документация, замеры без обёртки).
- Время фиксируется в finally — и при успехе, и при исключении; результат
  и исключение не изменяются.
- Записи уходят в logging (logger настраивает точка запуска, а не библиотека).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from time import perf_counter

logger = logging.getLogger(__name__)


def timed[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        start = perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            if logger.isEnabledFor(logging.DEBUG):
                duration_ms = (perf_counter() - start) * 1000
                logger.debug("function=%s duration_ms=%.3f", function.__qualname__, duration_ms)

    return wrapped
