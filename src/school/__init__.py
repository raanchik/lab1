"""school — приём сдач лабораторных и расширяемые анализаторы (ЛР 1, Python Core)."""

from .errors import (
    AnalyzerError,
    ConfigurationError,
    ConflictError,
    ErrorCode,
    ErrorDetail,
    FormatError,
    SchemaError,
    SchoolError,
)
from .models import AIDeclaration, AnalysisReport, Assignment, Evidence, Submission
from .parser import parse_assignments, parse_json_line, parse_submission, validate_submission

__version__ = "0.1.0"

__all__ = [
    "AIDeclaration",
    "AnalysisReport",
    "AnalyzerError",
    "Assignment",
    "ConfigurationError",
    "ConflictError",
    "ErrorCode",
    "ErrorDetail",
    "Evidence",
    "FormatError",
    "SchemaError",
    "SchoolError",
    "Submission",
    "parse_assignments",
    "parse_json_line",
    "parse_submission",
    "validate_submission",
]
