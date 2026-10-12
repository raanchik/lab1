"""Анализаторы и их контракт."""

from .base import AnalysisContext, Analyzer
from .length import LengthAnalyzer
from .registry import ENTRY_POINT_GROUP, AnalyzerFactory, AnalyzerRegistry, build_default_registry
from .template import TemplateAnalyzer

__all__ = [
    "ENTRY_POINT_GROUP",
    "AnalysisContext",
    "Analyzer",
    "AnalyzerFactory",
    "AnalyzerRegistry",
    "LengthAnalyzer",
    "TemplateAnalyzer",
    "build_default_registry",
]
