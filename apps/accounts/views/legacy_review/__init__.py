"""«Köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi» view paketi.

Bölgü ``handover`` / ``people`` paketləri ilə eynidir: ``policy`` (aktor qapısı),
``api`` (OXU, GET), ``actions`` (YAZMA, POST). Domen məntiqi burada DEYİL — o,
``apps.registrar.legacy_grade_review`` (sorğu), ``…_rows`` (təqdimat) və
``…_actions`` (append-only yazı) modullarındadır.
"""

from .actions import legacy_review_action
from .api import (
    legacy_review_groups,
    legacy_review_options,
    legacy_review_queue,
    legacy_review_subjects,
    legacy_review_teachers,
    legacy_review_units,
)
from .policy import resolve_actor

__all__ = [
    "legacy_review_action",
    "legacy_review_groups",
    "legacy_review_options",
    "legacy_review_queue",
    "legacy_review_subjects",
    "legacy_review_teachers",
    "legacy_review_units",
    "resolve_actor",
]
