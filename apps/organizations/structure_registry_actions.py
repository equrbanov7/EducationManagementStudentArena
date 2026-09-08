"""Fakültələr / Kafedralar kabinet reyestri — JSON əməl endpoint-ləri (2026-09-08).

Sahib istəyi: fakültəyə DEKAN, DEKAN MÜAVİNİ və PROQRAM KOORDİNATORU, kafedraya
KAFEDRA MÜDİRİ və MÜƏLLİM təyin etmək; vahidi yaratmaq / redaktə etmək /
arxivləmək — hamısı kabinetin içində, səhifə yenilənmədən (`teaching_office.js`
formanı JSON POST edir, cavabdan sonra bölmə fraqmenti yenidən yüklənir).

Üç endpoint:

* ``structure_unit_action`` (POST) — ``action`` açarı ilə tək giriş nöqtəsi:
  ``save_unit`` · ``archive_unit`` · ``assign_head`` · ``add_role`` ·
  ``add_teacher`` · ``remove_role``;
* ``structure_unit_staff`` (GET) — «Heyət» çekmecəsi üçün vahidin rəhbəri, rol
  qrupları və alt bölmələri (JSON);
* ``structure_role_candidates`` (GET) — axtarışlı seçici (`EMSSearchableSelect`)
  üçün namizədlər: ``kind=staff`` (rəhbər/müavin/koordinator — idarəetmə
  səviyyəli aktiv üzvlər) və ``kind=teacher`` (müəllim üzvlükləri).

QAPILAR (fail-closed, RBAC kataloqu ilə eyni açarlar):

* baxış/əhatə — ``unit.view`` (``tree_scope``; dekan yalnız öz fakültəsini görür);
* yaratma/redaktə/arxiv — ``unit.create`` / ``unit.edit`` / ``unit.delete``;
* rəhbər (dekan/müdir) — ``unit.assign_head`` VƏ YA ``member.edit``;
* müavin/koordinator/müəllim — ``member.edit``.

TƏLƏBƏ QORUMASI: aktiv akademik qeydi və ya tələbə rolu olan hesaba heç bir
heyət rolu verilmir (sahib, 2026-09-07) — 409 ``target_is_student``.

RƏHBƏR = ROL: dekan/müdir təyinatı ``OrgUnit.head``-i yazmaqla yanaşı həmin
vahidə əhatəli ``dean`` / ``chair_head`` üzvlüyünü də yaradır (varsa aktivləşdirir);
əvvəlki rəhbərin eyni vahiddəki rol üzvlüyü deaktiv edilir ki, köhnə dekan
fakültə üzərində icazə saxlamasın. Hər əməl auditə düşür.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType
from core.roles import ProfileRole
from core.staff_position import visible_role_label

from .models import Membership, Organization, OrgUnit, Role
from .structure_views._shared import (
    _teacher_memberships_qs,
    head_candidate_memberships,
    head_candidate_rows,
)
from .structure_views.constants import KAFEDRA_UNIT_TYPES, TEACHER_ROLE_NAMES
from .structure_views.registry import (
    CHAIR_HEAD_ROLE,
    COORDINATOR_ROLE,
    DEAN_ROLE,
    ROLE_LABELS,
    VICE_DEAN_ROLE,
    registry_flags,
    unit_type_label,
)
from .structure_views.tree import tree_scope
from .views import _unique_unit_slug, _visible_units_queryset

_CTX = "organizations.registry"

#: Arxivləmə üçün minimum səbəb uzunluğu — ağac əməlləri ilə eyni (audit qaydası).
ARCHIVE_REASON_MIN = 20

REGISTRY_UNIT_TYPES = (OrgUnitType.FACULTY, *KAFEDRA_UNIT_TYPES)

#: Bir səhifədə neçə namizəd (axtarışlı seçicinin infinite-scroll addımı).
CANDIDATE_PAGE_SIZE = 20
CANDIDATE_MAX_PAGE_SIZE = 50


# ─── Cavab köməkçiləri ──────────────────────────────────────────────────────


def _error(message, *, status=400, code="invalid", field=None):
    payload = {"ok": False, "error": code, "message": message}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _ok(message="", **extra):
    payload = {"ok": True, "message": message}
    payload.update(extra)
    return JsonResponse(payload)


def _forbidden(message):
    return _error(message, status=403, code="forbidden")


def _visible_unit(organization, scope, unit_id, unit_types=REGISTRY_UNIT_TYPES):
    if not unit_id:
        return None
    return (
        _visible_units_queryset(organization, scope)
        .filter(pk=unit_id, unit_type__in=unit_types)
        .select_related("parent", "head")
        .first()
    )


def _display_name(user):
    return user.get_full_name() or user.username


def _is_student(organization, user) -> bool:
    """`apps.accounts.services.people.actions._assert_not_student` ilə EYNİ meyar."""
    from apps.registrar.models import StudentAcademicRecord

    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=user, is_active=True).exists()
        or Membership.objects.filter(
            organization=organization,
            user=user,
            is_active=True,
            role__is_active=True,
            role__name__in=(ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT),
        ).exists()
    )


def _active_member_user(organization, user_id):
    """İstifadəçi YALNIZ bu təşkilatın aktiv üzvü ola bilər (cross-tenant qapısı)."""
    if not user_id:
        return None
    membership = (
        Membership.objects.filter(organization=organization, is_active=True, user__is_active=True, user_id=user_id)
        .select_related("user")
        .first()
    )
    return membership.user if membership else None


def _role(organization, name):
    return Role.objects.filter(organization=organization, name=name, is_active=True).first()


def _ensure_membership(organization, user, role, scope_unit, *, assigned_by):
    """(user, org, role, scope_unit) üzvlüyünü yarat və ya aktivləşdir.

    Qaytarır: ``(membership, created, reactivated)``. Artıq aktivdirsə
    ``(membership, False, False)``.
    """
    membership = Membership.objects.filter(
        organization=organization, user=user, role=role, scope_unit=scope_unit
    ).first()
    if membership is None:
        membership = Membership.objects.create(
            organization=organization,
            user=user,
            role=role,
            scope_unit=scope_unit,
            assigned_by=assigned_by,
            is_active=True,
        )
        return membership, True, False
    if not membership.is_active:
        membership.is_active = True
        membership.assigned_by = assigned_by
        membership.save(update_fields=["is_active", "assigned_by", "updated_at"])
        return membership, False, True
    return membership, False, False


def _in_subtree(unit, candidate) -> bool:
    return candidate.id == unit.id or candidate.path.startswith(f"{unit.path}/")


# ─── Əməllər ────────────────────────────────────────────────────────────────


def _save_unit(request, organization, scope, flags):
    kind = (request.POST.get("kind") or "").strip()
    if kind not in ("faculty", "kafedra"):
        return _error(pgettext(_CTX, "Vahid növü tanınmadı."), code="bad_kind")
    is_faculty = kind == "faculty"
    unit_types = (OrgUnitType.FACULTY,) if is_faculty else KAFEDRA_UNIT_TYPES

    unit_id = (request.POST.get("id") or "").strip()
    unit = _visible_unit(organization, scope, unit_id, unit_types) if unit_id else None
    if unit_id and unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")

    if unit is None:
        if not flags["can_create"]:
            return _forbidden(pgettext(_CTX, "Yeni bölmə yaratmaq üçün `unit.create` səlahiyyəti lazımdır."))
        if is_faculty and not scope.is_org_wide:
            return _forbidden(pgettext(_CTX, "Fakültə yaratmaq üçün bütün təşkilat əhatəsi lazımdır."))
    elif not flags["can_edit"]:
        return _forbidden(pgettext(_CTX, "Bölməni redaktə etmək üçün `unit.edit` səlahiyyəti lazımdır."))

    name = (request.POST.get("name") or "").strip()
    code = (request.POST.get("code") or "").strip()[:50]
    if not name:
        return _error(pgettext(_CTX, "Ad boş ola bilməz."), code="name_required", field="name")
    if len(name) > 255:
        return _error(pgettext(_CTX, "Ad maksimum 255 simvol ola bilər."), code="name_too_long", field="name")

    parent = None
    if not is_faculty:
        parent_id = (request.POST.get("parent") or "").strip()
        if not parent_id:
            return _error(pgettext(_CTX, "Kafedra üçün fakültə seçilməlidir."), code="parent_required", field="parent")
        parent = _visible_unit(organization, scope, parent_id, (OrgUnitType.FACULTY,))
        if parent is None:
            return _error(
                pgettext(_CTX, "Seçilmiş fakültə tapılmadı və ya əhatənizdə deyil."), code="bad_parent", field="parent"
            )

    # Unikallıq — eyni növdə eyni ad/kod ikinci dəfə yaradılmır (böyük/kiçik hərf fərqsiz).
    siblings = OrgUnit.objects.filter(organization=organization, is_active=True, unit_type__in=unit_types)
    if unit is not None:
        siblings = siblings.exclude(pk=unit.pk)
    if siblings.filter(name__iexact=name).exists():
        return _error(pgettext(_CTX, "Bu adda bölmə artıq var."), code="name_taken", field="name")
    if code and siblings.filter(code__iexact=code).exists():
        return _error(pgettext(_CTX, "Bu kodda bölmə artıq var."), code="code_taken", field="code")

    with transaction.atomic():
        if unit is None:
            unit = OrgUnit.objects.create(
                organization=organization,
                parent=parent,
                unit_type=OrgUnitType.FACULTY if is_faculty else OrgUnitType.CHAIR,
                name=name,
                slug=_unique_unit_slug(organization, name, kind),
                code=code,
            )
            log_action(
                action=AuditAction.CREATE,
                user=request.user,
                organization=organization,
                obj=unit,
                request=request,
                reason=f"structure registry: {kind} created",
                new_values={"name": name, "code": code, "parent": str(parent.id) if parent else ""},
            )
            message = pgettext(_CTX, "Fakültə yaradıldı.") if is_faculty else pgettext(_CTX, "Kafedra yaradıldı.")
        else:
            old_values = {"name": unit.name, "code": unit.code, "parent": str(unit.parent_id or "")}
            unit.name = name
            unit.code = code
            if not is_faculty:
                unit.parent = parent
            # save() level/path-i yenidən hesablayır və törəmələrə yayır.
            unit.save()
            log_action(
                action=AuditAction.UPDATE,
                user=request.user,
                organization=organization,
                obj=unit,
                request=request,
                reason=f"structure registry: {kind} updated",
                old_values=old_values,
                new_values={"name": name, "code": code, "parent": str(unit.parent_id or "")},
            )
            message = pgettext(_CTX, "Fakültə yeniləndi.") if is_faculty else pgettext(_CTX, "Kafedra yeniləndi.")
    return _ok(message, unit_id=str(unit.id))


def _archive_unit(request, organization, scope, flags):
    if not flags["can_delete"]:
        return _forbidden(pgettext(_CTX, "Bölməni arxivləmək üçün `unit.delete` səlahiyyəti lazımdır."))
    unit = _visible_unit(organization, scope, (request.POST.get("id") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")
    reason = (request.POST.get("reason") or "").strip()
    if len(reason) < ARCHIVE_REASON_MIN:
        return _error(
            pgettext(_CTX, "Səbəb ən azı 20 simvol olmalıdır — qısa qeyd audit üçün yetərli deyil."),
            code="reason_too_short",
            field="reason",
        )
    active_children = unit.children.filter(is_active=True).count()
    if active_children:
        return _error(
            pgettext(_CTX, "«%(name)s» arxivlənə bilməz: %(n)d aktiv alt bölmə var. Əvvəlcə onları köçürün.")
            % {"name": unit.name, "n": active_children},
            code="has_children",
        )
    scoped_members = unit.memberships.filter(is_active=True).count()
    if scoped_members:
        return _error(
            pgettext(_CTX, "«%(name)s» arxivlənə bilməz: %(n)d aktiv üzv bu bölməyə təyin olunub.")
            % {"name": unit.name, "n": scoped_members},
            code="has_members",
        )
    with transaction.atomic():
        unit.is_active = False
        unit.save(update_fields=["is_active", "updated_at"])
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=unit,
            request=request,
            reason=f"structure registry: archived — {reason}",
            old_values={"is_active": True},
            new_values={"is_active": False},
        )
    return _ok(pgettext(_CTX, "«%(name)s» arxivləndi.") % {"name": unit.name})


def _assign_head(request, organization, scope, flags):
    if not flags["can_assign_head"]:
        return _forbidden(pgettext(_CTX, "Rəhbər təyini üçün `unit.assign_head` və ya `member.edit` lazımdır."))
    unit = _visible_unit(organization, scope, (request.POST.get("id") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")

    head_id = (request.POST.get("head") or "").strip()
    new_head = None
    if head_id:
        new_head = _active_member_user(organization, head_id)
        if new_head is None:
            return _error(
                pgettext(_CTX, "Seçilmiş şəxs bu təşkilatın aktiv üzvü deyil."), code="bad_head", field="head"
            )
        if _is_student(organization, new_head):
            return _error(
                pgettext(_CTX, "Tələbə hesabına rəhbər rolu verilə bilməz."), status=409, code="target_is_student"
            )

    is_faculty = unit.unit_type == OrgUnitType.FACULTY
    role_name = DEAN_ROLE if is_faculty else CHAIR_HEAD_ROLE
    role = _role(organization, role_name)
    old_head = unit.head
    reason = (request.POST.get("reason") or "").strip()[:500]

    with transaction.atomic():
        unit.head = new_head
        unit.save(update_fields=["head", "updated_at"])
        if role is not None:
            if old_head is not None and (new_head is None or old_head.pk != new_head.pk):
                Membership.objects.filter(
                    organization=organization, user=old_head, role=role, scope_unit=unit, is_active=True
                ).update(is_active=False)
            if new_head is not None:
                _ensure_membership(organization, new_head, role, unit, assigned_by=request.user)
        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=unit,
            request=request,
            reason=f"structure registry: head assigned — {reason}" if reason else "structure registry: head assigned",
            old_values={"head": _display_name(old_head) if old_head else ""},
            new_values={"head": _display_name(new_head) if new_head else ""},
        )

    if new_head is None:
        message = pgettext(_CTX, "Rəhbər təyinatı silindi.")
    elif is_faculty:
        message = pgettext(_CTX, "%(name)s «%(unit)s» fakültəsinə dekan təyin edildi.") % {
            "name": _display_name(new_head),
            "unit": unit.name,
        }
    else:
        message = pgettext(_CTX, "%(name)s «%(unit)s» kafedrasına müdir təyin edildi.") % {
            "name": _display_name(new_head),
            "unit": unit.name,
        }
    return _ok(message)


def _add_role(request, organization, scope, flags):
    if not flags["can_assign_members"]:
        return _forbidden(pgettext(_CTX, "Heyət təyinatı üçün `member.edit` səlahiyyəti lazımdır."))
    unit = _visible_unit(organization, scope, (request.POST.get("id") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")

    role_name = (request.POST.get("role") or "").strip()
    is_faculty = unit.unit_type == OrgUnitType.FACULTY
    allowed = (VICE_DEAN_ROLE, COORDINATOR_ROLE) if is_faculty else (COORDINATOR_ROLE,)
    if role_name not in allowed:
        return _error(pgettext(_CTX, "Bu bölmə üçün belə rol təyin edilmir."), code="bad_role", field="role")
    role = _role(organization, role_name)
    if role is None:
        return _error(
            pgettext(_CTX, "«%(role)s» rolu bu təşkilatda yoxdur — default rollar yüklənməlidir.")
            % {"role": ROLE_LABELS.get(role_name, role_name)},
            code="role_missing",
        )

    user = _active_member_user(organization, (request.POST.get("user") or "").strip())
    if user is None:
        return _error(
            pgettext(_CTX, "Şəxs seçilməlidir və bu təşkilatın aktiv üzvü olmalıdır."), code="bad_user", field="user"
        )
    if _is_student(organization, user):
        return _error(pgettext(_CTX, "Tələbə hesabına heyət rolu verilə bilməz."), status=409, code="target_is_student")

    # Əhatə: koordinator üçün ixtisas (alt-ağacdan) və ya bütöv bölmə; müavin üçün bölmə özü.
    scope_unit = unit
    scope_id = (request.POST.get("scope") or "").strip()
    if scope_id and role_name == COORDINATOR_ROLE:
        candidate = OrgUnit.objects.filter(organization=organization, is_active=True, pk=scope_id).first()
        if candidate is None or not _in_subtree(unit, candidate):
            return _error(
                pgettext(_CTX, "Seçilmiş əhatə bu bölmənin alt-ağacında deyil."), code="bad_scope", field="scope"
            )
        scope_unit = candidate

    reason = (request.POST.get("reason") or "").strip()[:500]
    with transaction.atomic():
        membership, created, reactivated = _ensure_membership(
            organization, user, role, scope_unit, assigned_by=request.user
        )
        if not created and not reactivated:
            return _error(
                pgettext(_CTX, "%(name)s artıq bu əhatədə «%(role)s» rolundadır.")
                % {"name": _display_name(user), "role": ROLE_LABELS.get(role_name, role_name)},
                status=409,
                code="already_assigned",
            )
        log_action(
            action=AuditAction.CREATE if created else AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=membership,
            request=request,
            reason=(
                f"structure registry: {role_name} assigned — {reason}"
                if reason
                else f"structure registry: {role_name} assigned"
            ),
            new_values={"user": _display_name(user), "role": role_name, "scope_unit": scope_unit.name},
        )
    return _ok(
        pgettext(_CTX, "%(name)s «%(unit)s» üzrə %(role)s təyin edildi.")
        % {"name": _display_name(user), "unit": scope_unit.name, "role": ROLE_LABELS.get(role_name, role_name).lower()}
    )


def _add_teacher(request, organization, scope, flags):
    if not flags["can_assign_members"]:
        return _forbidden(pgettext(_CTX, "Müəllim təyinatı üçün `member.edit` səlahiyyəti lazımdır."))
    unit = _visible_unit(organization, scope, (request.POST.get("id") or "").strip(), KAFEDRA_UNIT_TYPES)
    if unit is None:
        return _error(pgettext(_CTX, "Kafedra tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")
    membership = (
        _teacher_memberships_qs(organization).filter(pk=(request.POST.get("membership") or "").strip() or None).first()
    )
    if membership is None:
        return _error(
            pgettext(_CTX, "Seçilmiş şəxs bu təşkilatın aktiv müəllim üzvü deyil."),
            code="bad_membership",
            field="membership",
        )
    if membership.scope_unit_id == unit.id:
        return _error(pgettext(_CTX, "Bu müəllim artıq həmin kafedradadır."), status=409, code="already_assigned")
    if _is_student(organization, membership.user):
        return _error(
            pgettext(_CTX, "Tələbə hesabına müəllim statusu verilə bilməz."), status=409, code="target_is_student"
        )

    previous = membership.scope_unit.name if membership.scope_unit_id else ""
    reason = (request.POST.get("reason") or "").strip()[:500]
    try:
        with transaction.atomic():
            membership.scope_unit = unit
            membership.save(update_fields=["scope_unit", "updated_at"])
            log_action(
                action=AuditAction.UPDATE,
                user=request.user,
                organization=organization,
                obj=membership,
                request=request,
                reason=(
                    f"structure registry: teacher assigned — {reason}"
                    if reason
                    else "structure registry: teacher assigned"
                ),
                old_values={"scope_unit": previous},
                new_values={"scope_unit": unit.name},
            )
    except IntegrityError:
        return _error(
            pgettext(_CTX, "Bu müəllimin həmin kafedrada eyni rolla üzvlüyü artıq mövcuddur."),
            status=409,
            code="already_assigned",
        )
    return _ok(
        pgettext(_CTX, "%(name)s «%(unit)s» kafedrasına təyin edildi.")
        % {"name": _display_name(membership.user), "unit": unit.name}
    )


def _remove_role(request, organization, scope, flags):
    if not flags["can_assign_members"]:
        return _forbidden(pgettext(_CTX, "Heyət təyinatını silmək üçün `member.edit` səlahiyyəti lazımdır."))
    unit = _visible_unit(organization, scope, (request.POST.get("id") or "").strip())
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")
    membership = (
        Membership.objects.filter(
            organization=organization, is_active=True, pk=(request.POST.get("membership") or "").strip() or None
        )
        .select_related("user", "role", "scope_unit")
        .first()
    )
    if membership is None or membership.scope_unit is None or not _in_subtree(unit, membership.scope_unit):
        return _error(pgettext(_CTX, "Bu bölmədə belə təyinat tapılmadı."), status=404, code="not_found")

    role_name = membership.role.name
    reason = (request.POST.get("reason") or "").strip()[:500]
    name = _display_name(membership.user)
    try:
        with transaction.atomic():
            if role_name in TEACHER_ROLE_NAMES:
                # Müəllim üzvlüyü SİLİNMİR — kafedradan ayrılır (jurnal/qiymət izi qalır).
                membership.scope_unit = None
                membership.save(update_fields=["scope_unit", "updated_at"])
                change = {"scope_unit": ""}
            else:
                membership.is_active = False
                membership.save(update_fields=["is_active", "updated_at"])
                change = {"is_active": False}
            if (
                role_name in (DEAN_ROLE, CHAIR_HEAD_ROLE)
                and unit.head_id == membership.user_id
                and membership.scope_unit_id in (unit.id, None)
            ):
                unit.head = None
                unit.save(update_fields=["head", "updated_at"])
                change["head"] = ""
            log_action(
                action=AuditAction.UPDATE,
                user=request.user,
                organization=organization,
                obj=membership,
                request=request,
                reason=(
                    f"structure registry: {role_name} removed — {reason}"
                    if reason
                    else f"structure registry: {role_name} removed"
                ),
                old_values={"user": name, "role": role_name, "scope_unit": unit.name},
                new_values=change,
            )
    except IntegrityError:
        return _error(
            pgettext(_CTX, "Müəllimin kafedrasız eyni rollu üzvlüyü artıq mövcuddur."), status=409, code="conflict"
        )
    return _ok(
        pgettext(_CTX, "%(name)s üçün «%(role)s» təyinatı silindi.")
        % {
            "name": name,
            "role": ROLE_LABELS.get(role_name, visible_role_label(role_name, membership.role.display_name)),
        }
    )


_HANDLERS = {
    "save_unit": _save_unit,
    "archive_unit": _archive_unit,
    "assign_head": _assign_head,
    "add_role": _add_role,
    "add_teacher": _add_teacher,
    "remove_role": _remove_role,
}


@login_required
@require_POST
def structure_unit_action(request, slug):
    """Fakültə/kafedra reyestri əməlləri — tək JSON endpoint."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _forbidden(pgettext(_CTX, "Struktur əhatəniz yoxdur."))
    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    return handler(request, organization, scope, registry_flags(request, organization))


# ─── «Heyət» çekmecəsi ───────────────────────────────────────────────────────


def _member_row(membership, *, unit):
    user = membership.user
    scope_unit = membership.scope_unit
    return {
        "membership_id": str(membership.id),
        "user_id": str(user.id),
        "name": _display_name(user),
        "username": user.username,
        "role": membership.role.name,
        "role_label": ROLE_LABELS.get(membership.role.name)
        or visible_role_label(membership.role.name, membership.role.display_name),
        "scope": scope_unit.name if scope_unit is not None and scope_unit.id != unit.id else "",
        "profile_url": reverse("accounts:public_profile", kwargs={"username": user.username}),
    }


@login_required
@require_GET
def structure_unit_staff(request, slug, unit_id):
    """Vahidin rəhbəri, rol qrupları və alt bölmələri — «Heyət» çekmecəsi (JSON)."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    if not scope.has_structure_access:
        return _forbidden(pgettext(_CTX, "Struktur əhatəniz yoxdur."))
    unit = _visible_unit(organization, scope, unit_id)
    if unit is None:
        return _error(pgettext(_CTX, "Bölmə tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")
    flags = registry_flags(request, organization)
    is_faculty = unit.unit_type == OrgUnitType.FACULTY

    subtree = Q(scope_unit_id=unit.id) | Q(scope_unit__path__startswith=f"{unit.path}/")
    role_names = (
        (VICE_DEAN_ROLE, COORDINATOR_ROLE, *TEACHER_ROLE_NAMES)
        if is_faculty
        else (COORDINATOR_ROLE, *TEACHER_ROLE_NAMES)
    )
    memberships = list(
        Membership.objects.filter(
            organization=organization, is_active=True, user__is_active=True, role__name__in=role_names
        )
        .filter(subtree)
        .select_related("user", "role", "scope_unit")
        .order_by("user__first_name", "user__last_name", "user__username")
    )
    groups = []
    order = [VICE_DEAN_ROLE, COORDINATOR_ROLE, "teacher"] if is_faculty else ["teacher", COORDINATOR_ROLE]
    for key in order:
        if key == "teacher":
            rows = [m for m in memberships if m.role.name in TEACHER_ROLE_NAMES]
            # Fakültədə müəllimlər KAFEDRA üzrədir — çekmecədə kafedra adı görünür.
            label = pgettext(_CTX, "Müəllimlər")
        else:
            rows = [m for m in memberships if m.role.name == key]
            label = ROLE_LABELS.get(key, key)
        groups.append(
            {
                "key": key,
                "label": label,
                "removable": flags["can_assign_members"],
                "members": [_member_row(m, unit=unit) for m in rows],
            }
        )

    child_types = KAFEDRA_UNIT_TYPES if is_faculty else (OrgUnitType.SPECIALTY,)
    children_qs = (
        OrgUnit.objects.filter(organization=organization, is_active=True, parent_id=unit.id, unit_type__in=child_types)
        .select_related("head")
        .order_by("name")
    )
    children = [
        {
            "id": str(child.id),
            "name": child.name,
            "code": child.code or "",
            "type_label": unit_type_label(child.unit_type),
            "head_name": _display_name(child.head) if child.head_id else "",
        }
        for child in children_qs
    ]
    return JsonResponse(
        {
            "ok": True,
            "unit": {
                "id": str(unit.id),
                "name": unit.name,
                "code": unit.code or "",
                "type": unit.unit_type,
                "type_label": unit_type_label(unit.unit_type),
                "parent_name": unit.parent.name if unit.parent_id else "",
                "head": (
                    {
                        "user_id": str(unit.head_id),
                        "name": _display_name(unit.head),
                        "username": unit.head.username,
                        "profile_url": reverse("accounts:public_profile", kwargs={"username": unit.head.username}),
                    }
                    if unit.head_id
                    else None
                ),
                "head_label": pgettext(_CTX, "Dekan") if is_faculty else pgettext(_CTX, "Kafedra müdiri"),
            },
            "groups": groups,
            "children": children,
            "children_label": pgettext(_CTX, "Kafedralar") if is_faculty else pgettext(_CTX, "İxtisaslar"),
            "can_assign_members": flags["can_assign_members"],
            "can_assign_head": flags["can_assign_head"],
        }
    )


# ─── Namizəd axtarışı ───────────────────────────────────────────────────────


def _bounds(request):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", CANDIDATE_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = CANDIDATE_PAGE_SIZE
    return offset, max(1, min(limit, CANDIDATE_MAX_PAGE_SIZE))


@login_required
@require_GET
def structure_role_candidates(request, slug):
    """``?kind=staff|teacher&unit=<id>&q=&offset=&limit=`` — axtarışlı seçici üçün namizədlər.

    Cavab forması layihədəki digər lookup-larla eynidir:
    ``{"results": [{"id", "text"}], "has_more": bool}``. Fail-closed: təyinat
    edə bilməyən aktora namizəd adları SIZMIR (boş 403).
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = tree_scope(request, organization)
    flags = registry_flags(request, organization) if scope.has_structure_access else None
    if flags is None or not (flags["can_assign_members"] or flags["can_assign_head"]):
        return JsonResponse({"results": [], "has_more": False}, status=403)

    offset, limit = _bounds(request)
    term = (request.GET.get("q") or "").strip()[:80]
    kind = (request.GET.get("kind") or "staff").strip()

    if kind == "teacher":
        queryset = _teacher_memberships_qs(organization)
        if term:
            queryset = queryset.filter(
                Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__username__icontains=term)
            )
        unit_id = (request.GET.get("unit") or "").strip()
        if unit_id:
            queryset = queryset.exclude(scope_unit_id=unit_id)
        page = list(queryset[offset : offset + limit + 1])
        no_chair = pgettext(_CTX, "kafedrasız")
        results = [
            {
                "id": str(m.id),
                "text": f"{_display_name(m.user)} — {m.scope_unit.name if m.scope_unit_id else no_chair}",
            }
            for m in page[:limit]
        ]
        return JsonResponse({"results": results, "has_more": len(page) > limit})

    memberships = head_candidate_memberships(organization, search=term)
    window = head_candidate_rows(memberships[: offset + (limit + 1) * 2])
    page = window[offset : offset + limit]
    return JsonResponse(
        {
            "results": [
                {
                    "id": str(row["user_id"]),
                    "text": f"{row['full_name']} — {row['role_label']}" if row["role_label"] else row["full_name"],
                }
                for row in page
            ],
            "has_more": len(window) > offset + limit,
        }
    )


__all__ = ["structure_unit_action", "structure_unit_staff", "structure_role_candidates", "ARCHIVE_REASON_MIN"]
