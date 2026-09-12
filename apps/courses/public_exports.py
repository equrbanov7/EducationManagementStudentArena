"""Explicit public contracts for cross-module consumers; implementation stays local."""

from . import dashboard_sources  # noqa: F401

__all__ = [
    "dashboard_sources",
]
