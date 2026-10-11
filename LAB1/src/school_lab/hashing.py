"""Устойчивые отпечатки.

Встроенный hash() не подходит: для строк он меняется между запусками
Python (рандомизация хешей). SHA-256 от согласованной сериализации даёт
одинаковый результат в любом процессе и на любой машине.

Политика сериализации: sort_keys, без пробелов, ensure_ascii=False, UTF-8,
allow_nan=False. Порядок ключей на хеш не влияет, а любое изменение
содержимого (даже лишний перевод строки в коде) влияет.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from .models import Submission


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def stable_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def submission_hash(value: Submission) -> str:
    """Хеш ВСЕЙ сдачи, включая идентификаторы и декларацию.

    Поэтому одинаковый код двух студентов — это разные хеши сдач.
    """
    return stable_hash(asdict(value))
