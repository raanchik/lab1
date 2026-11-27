# Отчёт по лабораторной работе 1 «Приём работ и расширяемые анализаторы»

**Траектория:** Python Core.
**Уровень:** основной + углубление Core (внешние анализаторы через entry points; типизированный  декоратор измерения времени).

## 1. Выполненные требования

### Этап А — приём и валидация

| Требование | Реализация | Проверка (тесты) |
|---|---|---|
| Пакет в src-layout, устанавливается в чистое окружение | `src/school_lab`, `pyproject.toml`, команда `school-lab` | установка `pip install .` в новом venv |
| Модель `Submission` по контракту схемы v1 | `models.py` (frozen dataclass, без изменяемых коллекций) | `test_submission_is_frozen` |
| Разбор JSON отдельно от проверки схемы | `parsing.decode_json` / `parsing.parse_submission` | `test_format_and_schema_errors_are_different` |
| Строгий JSON (повтор ключа, NaN, пустая строка) | хуки `object_pairs_hook`, `parse_constant` | `test_decode_json_rejects` |
| Валидация полей, типов, часового пояса, AI-декларации | `parsing.py`, без неявных преобразований типов | `test_schema_violations` (17 случаев) |
| Ошибка содержит code, field, message | `errors.SubmissionError.to_dict()` | `test_error_to_dict` |
| Различение формата, схемы, версии и конфликта | коды `invalid_json`, `schema_error`, `unsupported_version`, `conflict` | `test_invalid_submissions_file_gives_explained_errors` |
| Входные данные не изменяются | валидатор только читает вход | `test_success_does_not_mutate_input`, `test_schema_violations` |
| Дубликат не увеличивает число сдач | `SubmissionService.accept` сравнивает SHA-256 | `test_accept_then_duplicate` |
| Конфликт не перезаписывает исходную запись | исключение `conflict` + защита в репозитории | `test_conflict_does_not_overwrite` |
| Импорт продолжается после повреждённой строки | `services.import_source`, номер строки `line_no` | `test_import_partial_success` |
| CLI выводит JSON с accepted, duplicate, errors | `school-lab import` | `test_cli_import_success`, `test_cli_import_conflict` |

### Этап Б — контракты и расширения

| Требование | Реализация | Проверка (тесты) |
|---|---|---|
| Контракт `Analyzer.analyze(submission, context) -> AnalysisReport` | `typing.Protocol` в `analyzers.py` | `test_analyzer_contract_on_corpus` |
| Context с требованиями задания и конфигурацией | `AnalysisContext` + `config_hash` | `test_config_hash_changes_with_configuration` |
| analyzer_id и analyzer_version в отчёте | `make_report`, проверка в `validate_report` | `test_bad_report_is_rejected_at_boundary` |
| LengthAnalyzer: непустые строки, score=null | `LengthAnalyzer` | `test_length_analyzer` |
| TemplateAnalyzer: разрешённый шаблон, пояснение | `TemplateAnalyzer`, поиск блоков строк | `test_two_line_template` |
| Номера строк evidence — по исходному содержимому | `str.splitlines()`, нумерация с 1 | `test_invalid_evidence_rejected` |
| JSONL- и in-memory источники, общие контрактные тесты | `JSONLSource`, `InMemorySource` (+ `StreamSource`) | `tests/test_sources.py` (параметризованная фикстура) |
| Контекстный менеджер; файл закрывается при ошибке и досрочном выходе | `JSONLSource.open()` | `test_file_closed_after_early_exit`, `test_file_closed_after_consumer_exception` |
| Выбор анализатора по реестру без ветвления по классам | `registry.AnalyzerRegistry`, `AnalysisService.run` | `test_service_selects_by_registry` |
| Ошибка анализатора обрабатывается на границе | `analyzer_crashed`, `invalid_report` | `test_crashing_analyzer_is_wrapped` |
| Третий анализатор без изменения центрального сервиса | плагин `examples/declaration_plugin` | `test_declaration_analyzer_without_changing_service` |

### Углубление Core

- **Entry points:** анализаторы из установленных пакетов подключаются через группу `school_lab.analyzers`. При загрузке проверяются повтор имени, ошибка импорта и совпадение имени с `analyzer_id` (`test_entry_point_*`).
- **Декоратор `@timed`:** параметры типа `[**P, R]` (синтаксис PEP 695 для `ParamSpec` и `TypeVar`) сохраняют сигнатуру для статической проверки, `functools.wraps` — метаданные функции; время фиксируется и при исключении (`test_timed_*`).

### Упражнения из ноутбука лекции

Выполнены упражнения 1–7 (соответствие тестам — `docs/GUIDE.md`, раздел 9).

## 2. Команды проверки

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
mypy src
school-lab import data/submissions.jsonl          # успешный импорт
school-lab import data/demo_mixed.jsonl           # дубликат, конфликт, повреждённая строка
python scripts/bench.py --n 5000 --repeat 5       # замеры
```

Результаты прогона (Windows, Python 3.15.0):

- `pytest` 9.1.1: **162 passed, 1 skipped**. Пропуск предусмотрен контрактом: `StreamSource` читает чужой поток один раз и не поддерживает повторное открытие.
- `ruff check .` (ruff 0.17.0): **All checks passed!** Первый прогон выявил 13 замечаний стиля (порядок импортов, `datetime.UTC`, синтаксис PEP 695 для декоратора, вложенные `with`, лишние `noqa`); все исправлены. В тесте позднего связывания правило B023 отключено для одной строки: дефект там воспроизводится намеренно.
- `mypy src` (mypy 2.4.0, strict): **Success: no issues found in 14 source files.** Первый прогон нашёл одну ошибку: в `LengthAnalyzer` литерал `"text"` внутри кортежа выводился как `str`, а `Evidence.field` принимает только `Literal["text", "code"]`; исправлено явной аннотацией типа.

## 3. Измерения

**Окружение:** Python 3.15.0, Windows (AMD64), AMD Ryzen 7 5700X 8-Core Processor.
**Методика:** `python scripts/bench.py --n 5000 --repeat 5`. Синтетический корпус из 5000 сдач (учебные сдачи лекции с новыми идентификаторами), для каждой метрики берётся лучший из 5 прогонов. DEBUG-журналирование выключено.

| Метрика | Значение |
|---|---|
| Импорт (разбор + валидация + хеш + сохранение) | 41 668 сдач/с |
| Один анализ: length / template / missing_explanation | 66,7 / 63,0 / 55,7 мкс |
| Накладные расходы `@timed` | 0,153 мкс на вызов (0,23 % от анализа length) |
| Память объекта `Submission`: без slots / со slots | 161 / 112 байт |

**Выводы:**

- **Производительность импорта** достаточна для учебной нагрузки: 5000 сдач обрабатываются примерно за 0,12 с (около 24 мкс на сдачу, включая строгий разбор JSON, проверку схемы и SHA-256).
- **Время анализа у всех трёх анализаторов почти одинаковое** (56–67 мкс), хотя их алгоритмы разные. Это значит, что доминирует общая часть — создание и проверка отчёта, а не сам анализ.
- **Время анализа в основном уходит на хеширование.** По профилю `cProfile` бóльшая часть времени — пересчёт SHA-256 через `dataclasses.asdict`: отчёт проверяется дважды (в `make_report` и повторно на границе сервиса), поэтому хеш сдачи и `config_hash` вычисляются несколько раз за вызов. Двойная проверка оставлена сознательно: надёжность на границе с внешними анализаторами важнее долей миллисекунды. Возможная оптимизация — кешировать хеш сдачи.
- **Цена декоратора `@timed`** — 0,15 мкс на вызов, 0,23 % от времени анализа, то есть пренебрежимо мала. Сравнение «с декоратором и без» на целом анализе тонет в случайном разбросе времени, поэтому накладные расходы измерены изолированно на пустой функции (`timeit`, минимум из повторов).
- **`slots=True`** уменьшает размер самого объекта модели со 161 до 112 байт (примерно на 30 %), но основную память занимают строки `text` и `code`, поэтому влияние на общий расход памяти невелико. Ускорения работы `slots` не гарантирует.

