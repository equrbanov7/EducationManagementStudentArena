"""Explicit public contracts for cross-module consumers; implementation stays local."""

from .services.crud import create_notification  # noqa: F401

__all__ = [
    "create_notification",
]
