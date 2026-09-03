"""«Fənn təhvili» bölməsinin view paketi (`journal.reassign`).

Bölgü ``people`` paketi ilə eynidir: ``policy`` (aktor + serializasiya),
``labels`` (tərcümələr), ``api`` (OXU, GET), ``actions`` (YAZMA, POST).
Domen məntiqi burada DEYİL — o, ``apps.registrar.handover`` /
``apps.registrar.handover_actions`` modullarındadır.
"""

from .actions import handover_action
from .api import handover_history, handover_offerings, handover_options, handover_teachers
from .policy import resolve_actor

__all__ = [
    "handover_action",
    "handover_history",
    "handover_offerings",
    "handover_options",
    "handover_teachers",
    "resolve_actor",
]
