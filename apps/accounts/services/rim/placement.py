"""RİM detal kartı — «Vəzifə və bölmə»: üzvlüyün fakültə / kafedra yerləşdirilməsi (sahib 2026-11-04).

Sahib: «burda kafedra və s. də yoxdur, bura fakültə, bunlar da lazımdı qeyd edə bilmək». Ekranda müəllim
«Müəllim» rolu ilə görünürdü, amma rolun ``scope_unit``-i BOŞ idi — dərs yükü seçicisi (``workload.services.people``)
müəllimi məhz ``Membership.scope_unit``-in kafedra alt-ağacından tapır, yəni belə müəllim heç bir kafedranın
siyahısına düşmürdü.

YAZI YOLU: mövcud ``organizations.correct_membership_unit`` (rol / istifadəçi KOPYALANMIR; toqquşmada köhnə sətir
deaktiv tarixçə kimi qalır; ``expected_unit_id`` köhnəlmiş kartı 409 ilə dayandırır). Bu modul yalnız «kim, hansı
rolu, hansı bölməyə» qapısını verir:

* aktor — ``user.edit`` + rol təyini səlahiyyəti (``role.assign`` / ``org.manage_members``) — kanonik «Rol təyinatı»
  ilə EYNİ hüquq; şəxsi məlumat redaktəsi təkbaşına bölmə hüququ VERMİR;
* rol — müəllim rolları (kataloq: müəllim, assistent, laborant …) və aktorun TƏYİN edə bildiyi bölmə-əhatəli
  vəzifələr (``create_staff.staff_roles``); dekan / prorektor kimi yuxarı rollar burada yalnız görünür;
* bölmə — aktorun təyin + idxal əhatəsi (``create_staff.staff_units``, PR #189-un seçicisi ilə eyni mənbə):
  müəllimə kafedra, əməkdaşa kafedra / fakültə / şöbə (akademik yarpaq vahidlər — qrup, ixtisas — yox);
* mənbə — boş (yerləşdirilməyib) və ya ELƏ HƏMİN əhatədədir: kafedra müdiri başqa kafedranın müəllimini «çəkə» bilməz.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction, OrgUnitType, RoleScopeType

from ..people.constants import TEACHER_ROLE_NAMES
from .create_staff import can_assign_staff, staff_roles, staff_units
from .create_units import STAFF_PICKER_EXCLUDED_TYPES
from .lifecycle import normalize_reason
from .policy import PERM_EDIT, RimAccessError, assert_can_manage, require_permission
from .search import STUDENT_ROLE_NAMES

_CTX = "accounts.rim.placement"
KIND_TEACHER = "teacher"
KIND_STAFF = "staff"
FACULTY_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)


def can_place(actor) -> bool:
    return bool(
        actor.organization is not None and actor.user is not None and actor.has(PERM_EDIT) and can_assign_staff(actor)
    )


def _destinations(actor) -> dict:
    """``{kind: queryset}`` — yerləşdirmə hədəfləri (fail-closed: icazə yoxdursa boş)."""
    from apps.organizations.models import OrgUnit
    from apps.organizations.public import kafedra_unit_types

    if not can_place(actor):
        return {KIND_TEACHER: OrgUnit.objects.none(), KIND_STAFF: OrgUnit.objects.none()}
    base = staff_units(actor)
    return {
        KIND_TEACHER: base.filter(unit_type__in=kafedra_unit_types(actor.organization)),
        KIND_STAFF: base.exclude(unit_type__in=STAFF_PICKER_EXCLUDED_TYPES),
    }


def _kind_of(membership, staff_role_ids) -> str:
    role = membership.role
    if role.name in TEACHER_ROLE_NAMES:
        return KIND_TEACHER
    if role.scope_type == RoleScopeType.UNIT and role.pk in staff_role_ids:
        return KIND_STAFF
    return ""


def _faculty_map(organization) -> dict:
    from apps.organizations.models import OrgUnit

    return {
        str(unit.pk): unit
        for unit in OrgUnit.objects.filter(organization=organization, unit_type__in=FACULTY_TYPES).only(
            "id", "name", "path"
        )
    }


def _faculty_of(unit, faculties):
    """Bölmənin fakültəsi (materiallaşdırılmış yol üzrə ən yaxın fakültə/dekanlıq; özü də ola bilər)."""
    if unit is None:
        return None
    for segment in reversed(str(unit.path or unit.pk).split("/")):
        if segment in faculties:
            return faculties[segment]
    return None


def _unit_options(destinations, faculties) -> list:
    options: dict = {}
    for kind, queryset in destinations.items():
        for unit in queryset.only("id", "name", "code", "path"):
            faculty = _faculty_of(unit, faculties)
            item = options.setdefault(
                str(unit.pk),
                {
                    "id": str(unit.pk),
                    "name": unit.name,
                    "code": unit.code or "",
                    "faculty_id": str(faculty.pk) if faculty is not None else "",
                    "faculty": faculty.name if faculty is not None and faculty.pk != unit.pk else "",
                    "kinds": [],
                },
            )
            item["kinds"].append(kind)
    for item in options.values():
        item["kinds"] = " ".join(item["kinds"])
    return sorted(options.values(), key=lambda item: (item["name"].casefold(), item["faculty"].casefold()))


def card(actor, target) -> dict | None:
    """Detal kartının bölmə bloku: hər aktiv (tələbə olmayan) üzvlük + seçicilərin variantları."""
    from apps.organizations.models import Membership
    from core.staff_position import visible_role_label

    organization = actor.organization
    if organization is None:
        return None
    memberships = list(
        Membership.objects.filter(organization=organization, user=target, is_active=True, role__is_active=True)
        .exclude(role__name__in=STUDENT_ROLE_NAMES)
        .select_related("role", "scope_unit")
        .order_by("-role__level", "role__name")
    )
    if (
        not memberships
        and Membership.objects.filter(
            organization=organization, user=target, role__name__in=STUDENT_ROLE_NAMES
        ).exists()
    ):
        return None  # tələbə — bölməsi qrupudur (məzun kartı)
    placeable = can_place(actor)
    destinations = _destinations(actor)
    allowed = {kind: set(map(str, queryset.values_list("pk", flat=True))) for kind, queryset in destinations.items()}
    # Mənbə bölməsi istənilən tipdə ola bilər (köhnə idxal müəllimi fakültəyə / şöbəyə yazıb) — əsas olan, aktorun
    # təyin əhatəsində olmasıdır; hədəf isə rola uyğun tipdən seçilir.
    in_scope = set(map(str, staff_units(actor).values_list("pk", flat=True))) if placeable else set()
    staff_role_ids = {role.pk for role in staff_roles(actor)} if placeable else set()
    faculties = _faculty_map(organization)

    rows = []
    for membership in memberships:
        kind = _kind_of(membership, staff_role_ids)
        unit = membership.scope_unit if membership.scope_unit_id else None
        faculty = _faculty_of(unit, faculties)
        source_ok = unit is None or str(unit.pk) in in_scope
        if not placeable:
            locked = pgettext(_CTX, "Bölmə təyini üçün «Rol təyinatı» səlahiyyəti (role.assign) lazımdır.")
        elif not kind:
            locked = pgettext(_CTX, "Bu vəzifənin bölməsi «Rol təyinatı» bölməsində dəyişdirilir.")
        elif not source_ok:
            locked = pgettext(_CTX, "Cari bölmə sizin icazə əhatənizdən kənardadır.")
        elif not allowed.get(kind):
            locked = pgettext(_CTX, "Əhatənizdə seçilə bilən bölmə yoxdur.")
        else:
            locked = ""
        rows.append(
            {
                "id": str(membership.pk),
                "role_label": visible_role_label(membership.role.name, membership.role.display_name)
                or membership.role.name,
                "kind": kind,
                "unit_id": str(unit.pk) if unit is not None else "",
                "unit_name": unit.name if unit is not None else "",
                "faculty_id": str(faculty.pk) if faculty is not None else "",
                "faculty_name": (
                    faculty.name if faculty is not None and unit is not None and faculty.pk != unit.pk else ""
                ),
                "editable": not locked,
                "locked_reason": locked,
            }
        )
    units = _unit_options(destinations, faculties) if any(row["editable"] for row in rows) else []
    used = {unit["faculty_id"] for unit in units if unit["faculty_id"]}
    return {
        "memberships": rows,
        "units": units,
        "faculties": sorted(
            ({"id": key, "name": faculties[key].name} for key in used), key=lambda item: item["name"].casefold()
        ),
    }


def _source_membership(actor, target, membership_id):
    from apps.organizations.models import Membership

    try:
        return (
            Membership.objects.select_related("role", "scope_unit")
            .filter(
                pk=membership_id,
                organization=actor.organization,
                user=target,
                is_active=True,
                role__organization=actor.organization,
                role__is_active=True,
            )
            .exclude(role__name__in=STUDENT_ROLE_NAMES)
            .first()
        )
    except (ValidationError, ValueError, TypeError):
        return None


@transaction.atomic
def place(actor, target, *, membership_id, unit_id, expected_unit_id="", reason="", request=None) -> dict:
    """Seçilmiş üzvlüyü bölməyə yerləşdirir / bölməsini dəyişir (digər rollar toxunulmur)."""
    from apps.organizations.public import correct_membership_unit

    require_permission(actor, PERM_EDIT)
    if not can_place(actor):
        raise RimAccessError(
            "permission_denied",
            pgettext(_CTX, "Bölmə təyini üçün «Rol təyinatı» səlahiyyəti (role.assign) lazımdır."),
        )
    assert_can_manage(actor, target)
    reason = normalize_reason(reason, required=False)
    not_found = RimAccessError(
        "placement_not_found", pgettext(_CTX, "Təyinat və ya bölmə idarə sahənizdə deyil."), status=404
    )

    source = _source_membership(actor, target, membership_id)
    if source is None:
        raise not_found
    staff_role_ids = {role.pk for role in staff_roles(actor)}
    kind = _kind_of(source, staff_role_ids)
    if not kind:
        raise RimAccessError(
            "placement_role_locked",
            pgettext(_CTX, "Bu vəzifənin bölməsi «Rol təyinatı» bölməsində dəyişdirilir."),
            status=409,
        )
    destinations = _destinations(actor)[kind]
    try:
        unit = destinations.filter(pk=unit_id).first() if unit_id else None
    except (ValidationError, ValueError, TypeError):
        unit = None
    if unit is None and not unit_id:
        raise RimAccessError("unit_required", pgettext(_CTX, "Siyahıdan bölmə seçin."), status=400)
    if unit is None:
        raise not_found
    if source.scope_unit_id and not staff_units(actor).filter(pk=source.scope_unit_id).exists():
        raise not_found  # başqa (əhatədən kənar) bölmənin üzvünü «çəkmək» olmaz

    previous = {
        "membership_id": str(source.pk),
        "scope_unit_id": str(source.scope_unit_id or ""),
        "scope_unit": source.scope_unit.name if source.scope_unit_id else "",
    }
    try:
        result, changed, archived = correct_membership_unit(
            membership=source, unit=unit, expected_unit_id=expected_unit_id
        )
    except ValidationError:
        raise RimAccessError(
            "placement_stale", pgettext(_CTX, "Təyinat bu arada dəyişib. Kartı yenidən açın."), status=409
        ) from None

    department_synced = changed and _sync_department(target, result, unit, source_pk=source.pk)
    if changed:
        log_action(
            AuditAction.UPDATE,
            user=actor.user,
            organization=actor.organization,
            obj=result,
            request=request,
            reason=f"RİM: bölmə təyinatı. Səbəb: {reason or '-'}",
            old_values=previous,
            new_values={"membership_id": str(result.pk), "scope_unit_id": str(unit.pk), "scope_unit": unit.name},
            changes={
                "action": "rim.membership_unit_placed",
                "target_user_id": str(target.pk),
                "target_username": target.username,
                "role": source.role.name,
                "kind": kind,
                "archived_membership": str(archived) if archived else None,
                "profile_department_synced": department_synced,
                "reason_text": reason,
            },
        )
    return {"membership_id": str(result.pk), "changed": changed, "unit_name": unit.name}


def _sync_department(target, membership, unit, *, source_pk) -> bool:
    """Profilin göstəriş mətni «Departament / Kafedra» — əsas və ya YEGANƏ iş yeri dəyişəndə yenilənir."""
    from apps.organizations.models import Membership

    others = (
        Membership.objects.filter(organization=membership.organization_id, user=target, is_active=True)
        .exclude(role__name__in=STUDENT_ROLE_NAMES)
        .exclude(pk__in=(membership.pk, source_pk))
        .exists()
    )
    if others and not membership.is_primary:
        return False
    profile = getattr(target, "profile", None)
    if profile is None or profile.department == unit.name:
        return False
    profile.department = unit.name[:255]
    profile.save(update_fields=["department", "updated_at"])
    return True


__all__ = ["KIND_STAFF", "KIND_TEACHER", "can_place", "card", "place"]
