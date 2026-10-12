"""Единая нумерация строк.

Анализаторы и проверка диапазонов evidence обязаны считать строки
одинаково, иначе номера строк «поплывут». Поэтому правило вынесено в одно место.
"""

from __future__ import annotations


def split_lines(content: str) -> list[str]:
    """Разбивает текст на строки так, как их нумерует редактор (строка 1 — первая).

    - пустые строки сохраняются (они участвуют в нумерации);
    - завершающий перевод строки не создаёт лишнюю пустую строку;
    - Windows-окончания ``\\r\\n`` обрабатываются так же, как ``\\n``.
    """
    if content == "":
        return []
    lines = content.split("\n")
    if lines[-1] == "":
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def count_non_empty(content: str) -> int:
    """Число строк, содержащих хотя бы один непробельный символ."""
    return sum(1 for line in split_lines(content) if line.strip())
