"""Registrar ictimai səthi — semestr kredit yükü + «Alt qrupa yerləşdirmə» (sahib 2026-10-18).

Kənar modullar (accounts kabineti, 25% təkrar imtahan axını) YALNIZ bu adları ``apps.registrar.public``
üzərindən işlədir:

* ``credit_load(student, period) -> {"total", "own", "subgroup", "limit", "remaining", …}``;
* ``place_in_subgroup(*, student, offering, document, actor, reason, request=None)`` —
  :class:`SubgroupPlacementError` (``code``, ``message``) atır;
* ``undo_subgroup_placement(*, event_id, actor, reason, organization, request=None)``;
* ``record_imported_placement(*, enrollment, actor, reason, details=None, load=None)`` — köçürmənin yazdığı
  «alt qrupdan əlavə» qeydiyyatına tarixçə sətri (legacy delta ``subgroups`` fazası);
* oxu köməkçiləri: önbaxış (``evaluate_subgroup_placement``), uyğun jurnallar, tarixçə, əhatə qapısı.
"""

from __future__ import annotations

from . import credit_load as _credit_load
from . import guest_merge  # noqa: F401 — «alt qrup birləşməsi» (release_source); legacy delta dedupe işlədir
from . import subgroup_access, subgroup_placement_history, subgroup_placement_lookups, subgroup_placement_query
from .subgroup_documents import PlacementDocument
from .subgroup_placement import evaluate as evaluate_subgroup_placement
from .subgroup_placement import place_in_subgroup
from .subgroup_placement import undo_placement as undo_subgroup_placement
from .subgroup_placement_errors import SubgroupPlacementError
from .subgroup_placement_import import record_imported_placement

#: Yerləşdirmə açarı (``retake.manage``) — menyu və HTTP qapısı eyni sabiti işlədir.
SUBGROUP_PLACEMENT_PERMISSION = subgroup_access.PLACEMENT_PERMISSION


def credit_load(student, period, **kwargs) -> dict:
    """Tələbənin *period* kredit yükü (bax :func:`apps.registrar.credit_load.credit_load`)."""
    return _credit_load.credit_load(student, period, **kwargs)


credit_limits = _credit_load.limits
student_active_record = _credit_load.active_record

__all__ = [
    "PlacementDocument",
    "guest_merge",
    "SUBGROUP_PLACEMENT_PERMISSION",
    "SubgroupPlacementError",
    "credit_limits",
    "credit_load",
    "evaluate_subgroup_placement",
    "place_in_subgroup",
    "record_imported_placement",
    "student_active_record",
    "subgroup_access",
    "subgroup_placement_history",
    "subgroup_placement_lookups",
    "subgroup_placement_query",
    "undo_subgroup_placement",
]
