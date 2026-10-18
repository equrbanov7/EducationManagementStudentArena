"""«Alt qrupa tələbə əlavə et» view paketi (sahib 2026-10-18; açar ``retake.manage``).

Bölgü ``journal_hygiene`` paketi ilə eynidir: ``policy`` (aktor qapısı), ``api`` (OXU, GET), ``actions``
(YAZMA, POST), ``panel`` (bölmə çərçivəsi, template tag üçün), ``urls`` (accounts URLconf-a ``include``).
Domen məntiqi registrar-dadır (``credit_load``, ``subgroup_placement*``) və ``apps.registrar.public`` ilə gəlir.
"""

from .actions import placement_place, placement_undo
from .api import (
    placement_offerings,
    placement_preview,
    placement_recent,
    placement_student,
    placement_students,
    placement_subjects,
)
from .panel import build_panel_context

__all__ = [
    "build_panel_context",
    "placement_offerings",
    "placement_place",
    "placement_preview",
    "placement_recent",
    "placement_student",
    "placement_students",
    "placement_subjects",
    "placement_undo",
]
