"""Fakültələr / Kafedralar reyestri — ``structure_unit_action`` əməl işləyiciləri.

``structure_registry_actions.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21):
``save_unit`` · ``archive_unit`` · ``assign_head`` · ``add_role`` · ``add_teacher``
· ``remove_role`` və ``_HANDLERS`` xəritəsi. Qapılar, tələbə qoruması və
«rəhbər = rol» qaydası üçün bax ``structure_registry_actions.py`` başlığı.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType
from core.staff_position import visible_role_label

from .models import Membership, OrgUnit
from .name_matching import name_exists
from .structure_registry_helpers import (
    ARCHIVE_REASON_MIN,
    _active_member_user,
    _display_name,
    _ensure_membership,
    _error,
    _forbidden,
    _in_subtree,
    _is_student,
    _ok,
    _role,
    _visible_unit,
)
from .structure_views._shared import _teacher_memberships_qs
from .structure_views.constants import KAFEDRA_UNIT_TYPES, TEACHER_ROLE_NAMES
from .structure_views.registry import CHAIR_HEAD_ROLE, COORDINATOR_ROLE, DEAN_ROLE, ROLE_LABELS, VICE_DEAN_ROLE
from .views import _unique_unit_slug

# i18n skaneri kontekst sabitini MODUL daxilində axtarır — yerli təyin.
_CTX = "organizations.registry"


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
    if name_exists(siblings, name):
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
