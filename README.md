# ЛР 1 — Приём работ и расширяемые анализаторы (траектория Python Core)

Пакет принимает сдачи из JSONL, строго валидирует их по контракту схемы версии 1,
обрабатывает дубликаты и конфликты, запускает анализаторы через реестр фабрик и проверяет
их отчёты на границе. Принятый код **не исполняется**: поле `code` — это данные.
Машинный отчёт содержит наблюдения; решение о нарушении принимает преподаватель.


## Установка

Требуется Python ≥ 3.12. У пакета нет сторонних зависимостей.

```bash
python -m venv .venv
source .venv/bin/activate             
python -m pip install -e '.[dev]'
```

Проверка обычной (не editable) установки в новом окружении: `python -m pip install .`

## Запуск

```bash
school-lab import data/submissions.jsonl          
school-lab import data/demo_mixed.jsonl          
school-lab import data/invalid_submissions.jsonl  

school-lab analyze data/submissions.jsonl --assignments data/assignments.json
school-lab analyze data/submissions.jsonl --assignments data/assignments.json --analyzer template
python -m school_lab import data/submissions.jsonl   
```

stdout — один JSON-документ, stderr — диагностика.
Коды выхода: `0` — без ошибок; `1` — ошибки отдельных строк или анализа (корректные записи приняты);
`2` — источник недоступен или конфигурация неверна.

## Проверки

```bash
python -m pytest
ruff check .
mypy src
python scripts/bench.py --n 5000 --repeat 5
```

## Третий анализатор (сценарий защиты)

```bash
python -m pip install -e examples/declaration_plugin
school-lab analyze data/submissions.jsonl --assignments data/assignments.json --plugins
```

Плагин объявлен как entry point в группе `school_lab.analyzers` (plugin API версии 1):
имя `declaration` совпадает с `analyzer_id`. Центральный сервис не меняется.

## Структура

```
src/school_lab/
  models.py        Submission, AIDeclaration, Assignment, Evidence, Finding, AnalysisReport
  errors.py        SubmissionError(code, field, message), AnalysisFailure
  parsing.py       decode_json (строгий JSON), parse_submission (схема v1), parse_assignments
  hashing.py       canonical_json, stable_hash, submission_hash (SHA-256)
  repositories.py  Protocol SubmissionRepository + in-memory реализация
  sources.py       SourceRecord; InMemorySource, JSONLSource, StreamSource
  analyzers.py     Protocol Analyzer, AnalysisContext, validate_report, make_report,
                   LengthAnalyzer, TemplateAnalyzer, MissingExplanationAnalyzer
  registry.py      AnalyzerRegistry, entry points, build_registry
  services.py      SubmissionService, import_source, AnalysisService
  timing.py        типизированный декоратор @timed
  app.py           точка сборки приложения
  cli.py           командная строка
tests/             unit-, контрактные и интеграционные тесты
data/              учебный корпус из лекции + синтетические ошибочные записи
examples/          плагин DeclarationAnalyzer
scripts/bench.py   замеры
```

## Принятые политики

- **Схема v1**: неизвестные поля отклоняются; `schema_version` — строго `int` (не `bool`), равно 1;
  время — ISO 8601 с часовым поясом; хотя бы одно из `text`/`code` непустое; при `used=true`
  обязательны `tool` и `purpose`. Сообщается первая найденная ошибка.
- **Строгий JSON**: повтор ключа и `NaN`/`Infinity` — `invalid_json`. Пустая строка файла — тоже `invalid_json`.
- **Хеш** — SHA-256 канонического JSON всей сдачи. `submitted_at` хранится исходной строкой,
  поэтому `10:00+03:00` и `07:00+00:00` — разные хеши (следствие контракта, а не ошибка).
- **Шаблон** ищется как блок подряд идущих строк, точно, без нормализации пробелов.
  Пустой шаблон ничего не находит. Совпадение с шаблоном разрешено.
- **Нумерация строк** — `str.splitlines()`, с 1, по исходному тексту.
- **Импорт** атомарен на уровне одной сдачи, а не всего файла.


- Хранилище в памяти: данные исчезают при завершении процесса; `get`+`add` не атомарны (ЛР 3).
- TemplateAnalyzer не находит переименованные переменные и нечёткие совпадения (ЛР 2).
- Размер входной строки не ограничивается.
- Плагины исполняются с правами процесса: entry points — только для доверенных расширений.
