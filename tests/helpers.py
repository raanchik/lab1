"""Общие тестовые данные. Учебный корпус берётся из data/submissions.jsonl (12 сдач из лекции)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
PLUGIN_SRC = PROJECT_ROOT / "examples" / "declaration_plugin" / "src"

PUBLIC_SUBMISSIONS: list[dict[str, Any]] = [
    json.loads(line) for line in (DATA_DIR / "submissions.jsonl").read_text(encoding="utf-8").splitlines()
]
RAW_EXAMPLE: dict[str, Any] = PUBLIC_SUBMISSIONS[0]
TEMPLATE = "from typing import Iterable\n"


def changed(**updates: Any) -> dict[str, Any]:
    """Копия корректной сдачи sub-001 с изменёнными полями."""
    result = copy.deepcopy(RAW_EXAMPLE)
    result.update(updates)
    return result


def changed_declaration(**updates: Any) -> dict[str, Any]:
    result = copy.deepcopy(RAW_EXAMPLE)
    result["ai_declaration"].update(updates)
    return result
