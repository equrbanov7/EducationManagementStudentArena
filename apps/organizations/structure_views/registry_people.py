"""Struktur reyestrlərinin ŞƏXS köməkçiləri (ad, inisial, rəhbər, heyət).

`registry.py` modul-ölçü büdcəsinə dayandığı üçün ayrıldı (2026-09-09). Burada
YALNIZ «vahid → şəxs» həlli var: göstərilən ad, inisial nişanı, dekan/kafedra
müdirinin tapılması və müavin/koordinator heyəti.

⚠️ Rəhbər İKİ mənbədən gəlir: rəsmi `OrgUnit.head` FK-sı, o boşdursa rol
üzvlüyü (`Membership.role=dean|chair_head`, `scope_unit=<vahid>`). Universitet
tenantında təyinat məhz rol üzvlüyü ilə aparılır və FK boş qalır — əvvəl reyestr
yalnız FK-ya baxdığı üçün bütün fakültə/kafedralar «rəhbəri yoxdur» görünürdü.
"""

from __future__ import annotations

from collections import defaultdict

from django.urls import reverse

from ..models import Membership

__all__ = [
    "display_name",
    "head_of",
    "initials",
    "person",
    "person_url",
    "role_heads",
    "staff_by_root",
]


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def display_name(user):
    return user.get_full_name() or user.username


def staff_by_root(organization, owner, role_names):
    """Heyət üzvlükləri (müavin/koordinator) → kök vahid → rol → [membership]."""
    rows = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__name__in=role_names,
            scope_unit__isnull=False,
        )
        .select_related("user", "role", "scope_unit")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    out = defaultdict(lambda: defaultdict(list))
    for membership in rows:
        root = owner(membership.scope_unit.path)
        if root is not None:
            out[root][membership.role.name].append(membership)
    return out


def person_url(user_id: str) -> str:
    """Şəxsin AÇIQ profil səhifəsi (yeni tabda açılır) — rəhbər adı klikləndikdə.

    Sahib (2026-09-09): «üzərinə klik edəndə keçmək olsun». Ad yoxdursa boş
    sətir qaytarılır və şablon linki ümumiyyətlə qurmur.
    """
    if not user_id:
        return ""
    return reverse("accounts:people_person_page", args=[user_id])


def role_heads(organization, units, role_name):
    """`scope_unit_id → Membership` — rolla təyin olunmuş RƏHBƏR.

    ⚠️ 2026-09-09 düzəlişi (sahib: «kafedra müdiri altında kafedranın adı
    görünür, müəllimin ad-soyadı görünməlidi … data yoxdu»). Reyestr rəhbəri
    YALNIZ `OrgUnit.head` FK-sından oxuyurdu. Universitetdə isə dekan/kafedra
    müdiri ROL ÜZVLÜYÜ ilə verilir (`Membership.role=dean|chair_head`,
    `scope_unit=<vahid>`) — FK isə boş qalır. Nəticədə 13 fakültənin 13-ü,
    18 kafedranın 18-i «təyin edilməyib» görünürdü, halbuki «Rol təyin et»
    ekranında dekanlar var idi.

    FK üstünlük daşıyır (rəsmi təyinat), rol üzvlüyü isə FALLBACK-dir.
    """
    unit_ids = [unit.id for unit in units]
    if not unit_ids:
        return {}
    rows = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__name=role_name,
            scope_unit_id__in=unit_ids,
        )
        .select_related("user")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    out = {}
    for membership in rows:
        out.setdefault(membership.scope_unit_id, membership)
    return out


def catalog_user_ids(organization, user_ids):
    """Verilən şəxslərdən «İnsanlar» kataloqunda GÖRÜNƏNLƏR (müəllim üzvlüyü olanlar).

    Rəhbərin adı yalnız bu halda linkə çevrilir: şəxs səhifəsi kataloq əhatəsi
    ilə qorunur (`people.build_person_page`) və kataloqda olmayan hesab (məs. QA
    xidməti hesabı) 404 verir — istifadəçini ölü linkə göndərmirik.
    """
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return set()
    from .constants import TEACHER_ROLE_NAMES

    return set(
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            user__is_active=True,
            role__name__in=TEACHER_ROLE_NAMES,
            user_id__in=ids,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


def head_of(unit, role_heads):
    """(ad, istifadəçi id) — FK varsa ondan, yoxsa rol üzvlüyündən."""
    if unit.head_id:
        return display_name(unit.head), unit.head_id
    membership = role_heads.get(unit.id)
    if membership is None:
        return "", None
    return display_name(membership.user), membership.user_id


def person(membership, *, root_id):
    scope = membership.scope_unit
    return {
        "membership_id": str(membership.id),
        "name": display_name(membership.user),
        "initials": initials(display_name(membership.user)),
        "scope": scope.name if scope is not None and scope.id != root_id else "",
    }


# ─── Filtr köməkçiləri ──────────────────────────────────────────────────────
