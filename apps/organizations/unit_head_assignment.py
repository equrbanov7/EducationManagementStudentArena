"""Bölmə rəhbərinin təyini — «rəhbər = rol» qaydasının TƏK icra nöqtəsi.

İki yol bu funksiyanı çağırır:

* «Fakültələr / Kafedralar» reyestri (``structure_registry_unit_actions._assign_head``);
* «Universitet strukturu» ağacı (``structure_actions._assign_head``).

2026-10-19 düzəlişi: ağac yolu YALNIZ ``OrgUnit.head``-i yazırdı. Sillabus
təsdiqi, plan zənciri və bildirişlər isə rəhbəri ROL ÜZVLÜYÜNDƏN tanıyır
(``chair_head`` / ``dean`` + ``scope_unit=bölmə``) — ağacdan təyin olunan
müdirin təsdiq əhatəsi yox idi. İndi hər iki yol eyni addımları atır:

1. ``unit.head`` yazılır;
2. **fakültə** → ``dean``, **kafedra/departament** → ``chair_head`` rolu
   bölməyə SCOPE-lu üzvlüklə verilir (varsa aktivləşdirilir);
3. əvvəlki rəhbərin HƏMİN bölmədəki həmin rol üzvlüyü söndürülür
   (``is_active=False`` — silinmir, tarixçə qalır).

Digər bölmə tipləri (ixtisas, qrup, inzibati şöbə…) üçün rol YOXDUR —
yalnız ``unit.head`` dəyişir (köhnə davranış).

Səlahiyyət, səbəb və audit ÇAĞIRANIN işidir (iki yolun qapıları fərqlidir);
bu funksiya yalnız yazır və ATOMİKDİR.
"""

from __future__ import annotations

from django.db import transaction

from core.constants import OrgUnitType

from .models import Membership
from .structure_registry_helpers import _ensure_membership, _is_student, _role
from .structure_views.constants import KAFEDRA_UNIT_TYPES
from .structure_views.registry_base import CHAIR_HEAD_ROLE, DEAN_ROLE


def head_role_name(unit) -> str:
    """Bölmə tipinə görə rəhbər rolunun adı; rol verilməyən tip üçün ``""``."""
    if unit.unit_type == OrgUnitType.FACULTY:
        return DEAN_ROLE
    if unit.unit_type in KAFEDRA_UNIT_TYPES:
        return CHAIR_HEAD_ROLE
    return ""


def head_target_is_student(organization, unit, user) -> bool:
    """Rol verən bölməyə tələbəni rəhbər etmək olmaz (sahib 2026-09-07: tələbə heç vaxt heyət deyil)."""
    return bool(user is not None and head_role_name(unit) and _is_student(organization, user))


@transaction.atomic
def apply_unit_head(organization, unit, new_head, *, assigned_by):
    """``unit.head`` + rol üzvlüyünü sinxron yazır; ``(old_head, role_name)`` qaytarır.

    ``role_name`` boşdursa rol verilmədi (tip rol daşımır VƏ YA rol təşkilatda
    seed olunmayıb — sonuncu halda yalnız ``unit.head`` yazılır, əvvəlki kimi).
    """
    old_head = unit.head
    unit.head = new_head
    unit.save(update_fields=["head", "updated_at"])

    role_name = head_role_name(unit)
    role = _role(organization, role_name) if role_name else None
    if role is None:
        return old_head, ""
    if old_head is not None and (new_head is None or old_head.pk != new_head.pk):
        Membership.objects.filter(
            organization=organization, user=old_head, role=role, scope_unit=unit, is_active=True
        ).update(is_active=False)
    if new_head is not None:
        _ensure_membership(organization, new_head, role, unit, assigned_by=assigned_by)
    return old_head, role_name


__all__ = ["apply_unit_head", "head_role_name", "head_target_is_student"]
