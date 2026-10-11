"""school_lab — приём сдач и расширяемые анализаторы (ЛР 1, траектория Python Core).

Небольшой стабильный публичный API; тяжёлые адаптеры (CLI) здесь не импортируются.
"""

import logging

from .analyzers import AnalysisContext, Analyzer
from .errors import AnalysisFailure, SubmissionError
from .models import AIDeclaration, AnalysisReport, Assignment, Evidence, Finding, Submission
from .parsing import decode_json, parse_submission

__version__ = "0.1.0"

# Библиотека не настраивает журналирование сама: handlers и уровень задаёт точка запуска.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AIDeclaration",
    "AnalysisContext",
    "AnalysisFailure",
    "AnalysisReport",
    "Analyzer",
    "Assignment",
    "Evidence",
    "Finding",
    "Submission",
    "SubmissionError",
    "decode_json",
    "parse_submission",
]
