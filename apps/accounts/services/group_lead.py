"""Qrupun STAROSTASI (``lead_student``) — təyin et / dəyiş / götür (2026-10-13 (gecə)).

NİYƏ AYRICA XİDMƏT?
-------------------
Sahib: «qrupa starosta əlavə etmək yerinə yenidən bax, problem olan hissəni dəyiş». Əvvəl starosta
ümumi rol axınları ilə verilirdi və hər biri öz yolunda sınırdı:

* «Rol təyin et» (``role_assignment`` → ``update_member``) tələbənin YEGANƏ üzvlüyünün rolunu yerində
  ``lead_student`` edirdi — ``scope_unit`` boş qalırdı (tələbə üzvlüklərində həmişə boşdur), baş tələbənin
  ``member.view`` əhatəsi boşa çıxırdı və «Starosta» bölməsi GÖRÜNMÜRDÜ (QA hesabında belə gördük);
* «Rolları idarə et» (``grant_role``) istənilən ``scope_unit`` qəbul edirdi — fakültə, başqa qrup, hətta
  tələbənin oxumadığı qrup; eyni qrupa iki aktiv starosta da düşə bilirdi;
* heç bir yol tələbəyə bildiriş göndərmirdi, qrup reyestrində kimin starosta olduğu görünmürdü,
  dəyişmək/götürmək üçün ayrıca əməl yox idi.

QAYDALAR (hamısı SERVERDƏ — UI gizlətməsi təhlükəsizlik deyil):

1. Starosta YALNIZ həmin qrupun AKTİV + QEYDİYYATLI (``enrolled``) tələbəsi ola bilər.
2. Bir qrupda ən çox BİR aktiv starosta: yeni təyinat köhnəni avtomatik götürür («dəyiş»). Qrup sətri
   ``SELECT … FOR UPDATE`` ilə kilidlənir — iki paralel təyinat iki starosta yarada bilməz.
3. Üzvlük ƏLAVƏDİR: tələbənin ``student`` üzvlüyünə TOXUNULMUR, ``lead_student`` ayrıca sətirdir və
   ``scope_unit`` = qrup. Götürüləndə yalnız bu sətir ``is_active=False`` olur (silinmir — tarixçə).
   Köhnə (sınıq) axından qalan, şəxsin YEGANƏ üzvlüyü olan starosta sətri götürüləndə şəxs üzvlüksüz
   qalmasın deyə ``student`` üzvlüyü bərpa/yaradılır.
4. Tələbənin başqa qrupa/əhatəsiz bağlı köhnə starosta sətirləri yeni təyinatda söndürülür (bir
   tələbə yalnız öz qrupunun starostası ola bilər).
5. Hər əməl audit jurnalına (aktor + vaxt + köhnə/yeni starosta + səbəb) düşür; təyin olunan və
   götürülən tələbəyə daxili bildiriş gedir (bildiriş xətası əməli GERİ QAYTARMIR — commit-dən sonra).
6. ``UserProfile.role`` (köhnə enum) ən yüksək aktiv üzvlüyə görə yenilənir.

Qapı (açar + əhatə) çağıran view-dadır: ``views/group_lead.py`` (``unit.group_manage`` və ya
``role.assign`` əhatəsində görünən qrup).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction, OrgUnitType

logger = logging.getLogger(__name__)

_CTX = "accounts.group_lead"

LEAD_ROLE_NAME = "lead_student"
STUDENT_ROLE_NAME = "student"

#: Səbəb mətninin yuxarı həddi (səbəb opsionaldır — audit aktor + vaxtı onsuz da yazır).
REASON_MAX_LENGTH = 500


class GroupLeadError(Exception):
    """İstifadəçiyə göstərilən rədd (``code`` — maşın üçün, ``status`` — HTTP)."""

    def __init__(self, message, *, code="invalid", status=400, field=""):
        super().__init__(message)
        self.message = str(message)
        self.code = code
        self.status = status
        self.field = field


@dataclass(frozen=True)
class LeadInfo:
    """Reyestr sətri / çekmecə üçün starosta xülasəsi."""

    user_id: int
    username: str
    name: str
    #: Starosta HƏMİN qrupun qeydiyyatlı tələbəsi deyil (köçürülüb / xaric / köhnə sınıq təyinat).
    not_in_group: bool = False


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _lead_role(organization):
    Role = _model("organizations", "Role")
    return Role.objects.filter(organization=organization, name=LEAD_ROLE_NAME, is_active=True).first()


def _active_lead_memberships(organization, group):
    Membership = _model("organizations", "Membership")
    return list(
        Membership.objects.filter(
            organization=organization, role__name=LEAD_ROLE_NAME, scope_unit=group, is_active=True
        ).select_related("user", "role")
    )


def _enrolled_record(organization, group, record_id):
    StudentAcademicRecord = _model("registrar", "StudentAcademicRecord")
    try:
        record_uuid = uuid.UUID(str(record_id or "").strip())
    except (ValueError, TypeError, AttributeError):
        return None
    return (
        StudentAcademicRecord.objects.filter(
            organization=organization, group=group, is_active=True, status="enrolled", pk=record_uuid
        )
        .select_related("student")
        .first()
    )


def _clean_reason(reason) -> str:
    return (reason or "").strip()[:REASON_MAX_LENGTH]


def _sync_profile(user, organization):
    from .role_catalog import sync_profile_primary_role

    try:
        sync_profile_primary_role(user, organization)
    except Exception:  # noqa: BLE001 — köhnə enum sinxronu əməli sındırmamalıdır
        logger.exception("group_lead: profile role sync failed for user=%s", getattr(user, "pk", None))


def _ensure_student_membership(user, organization, *, actor, only_if_orphan=True):
    """``student`` üzvlüyünü təmin et.

    ``only_if_orphan=True`` (götürmə): yalnız şəxsin HEÇ BİR aktiv üzvlüyü qalmayıbsa — köhnə «Rol təyin
    et» axını tələbənin yeganə üzvlüyünü ``lead_student``-ə çevirirdi, götürmə onu üzvlüksüz qoymamalıdır.
    ``only_if_orphan=False`` (təyinat): starosta HƏM DƏ tələbədir — ``student`` sətri yoxdursa yaradılır.
    """
    Membership = _model("organizations", "Membership")
    Role = _model("organizations", "Role")
    active = Membership.objects.filter(user=user, organization=organization, is_active=True)
    if only_if_orphan and active.exists():
        return None
    student_role = Role.objects.filter(organization=organization, name=STUDENT_ROLE_NAME, is_active=True).first()
    if student_role is None or active.filter(role=student_role).exists():
        return None
    has_primary = active.filter(is_primary=True).exists()
    membership, _created = Membership.objects.update_or_create(
        user=user,
        organization=organization,
        role=student_role,
        scope_unit=None,
        defaults={"is_active": True, "assigned_by": actor, "is_primary": not has_primary},
    )
    return membership


def _deactivate(membership, *, actor):
    membership.is_active = False
    membership.is_primary = False
    membership.assigned_by = actor
    membership.save(update_fields=["is_active", "is_primary", "assigned_by", "updated_at"])


def _notify(user, organization, *, title, message):
    """Daxili bildiriş — commit-dən SONRA; xəta yalnız loqa düşür."""
    from apps.notifications.models import NotificationType
    from apps.notifications.public import create_notification

    link = f"{reverse('accounts:profile')}?section=my-group"

    def _send():
        try:
            create_notification(
                recipient=user,
                title=title,
                message=message,
                link=link,
                notification_type=NotificationType.SYSTEM,
                organization=organization,
                metadata={"organization_id": str(organization.pk), "kind": "group_lead"},
            )
        except Exception:  # noqa: BLE001
            logger.exception("group_lead: notification failed for user=%s", getattr(user, "pk", None))

    transaction.on_commit(_send)


def _audit(actor, organization, membership, *, request, reason, old_values, new_values, created):
    log_action(
        action=AuditAction.CREATE if created else AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=membership,
        request=request,
        reason=f"group lead: {new_values.get('event', '')} — {reason}" if reason else (
            f"group lead: {new_values.get('event', '')}"
        ),
        old_values=old_values,
        new_values=new_values,
    )


def _lock_group(organization, group):
    OrgUnit = _model("organizations", "OrgUnit")
    locked = (
        OrgUnit.objects.select_for_update()
        .filter(organization=organization, pk=group.pk, unit_type=OrgUnitType.GROUP, is_active=True)
        .first()
    )
    if locked is None:
        raise GroupLeadError(pgettext(_CTX, "Qrup tapılmadı və ya arxivdədir."), code="not_found", status=404)
    return locked


def assign_group_lead(*, organization, group, record_id, actor, reason="", request=None, notify=True) -> dict:
    """``record_id`` tələbəsini qrupun starostası et (köhnə starosta varsa götürülür).

    ``notify=False`` — yalnız ``repair_group_leads`` əmri üçün (köhnə təyinatın düzəlişi yeni xəbər deyil).
    Qaytarır: ``{"lead": LeadInfo, "replaced": [ad, …], "created": bool}``.
    """
    reason = _clean_reason(reason)
    role = _lead_role(organization)
    if role is None:
        raise GroupLeadError(
            pgettext(_CTX, "«Baş tələbə» (lead_student) rolu bu təşkilatda yoxdur — standart rollar yüklənməlidir."),
            code="role_missing",
            status=409,
        )
    Membership = _model("organizations", "Membership")
    with transaction.atomic():
        group = _lock_group(organization, group)
        record = _enrolled_record(organization, group, record_id)
        if record is None:
            raise GroupLeadError(
                pgettext(_CTX, "Starosta yalnız bu qrupun qeydiyyatlı tələbəsi ola bilər."),
                code="not_group_student",
                status=409,
                field="record_id",
            )
        student = record.student
        if actor is not None and student.pk == actor.pk:
            raise GroupLeadError(pgettext(_CTX, "Özünüzü starosta təyin edə bilməzsiniz."), code="self", status=403)
        current = _active_lead_memberships(organization, group)
        if [m.user_id for m in current] == [student.pk]:
            raise GroupLeadError(
                pgettext(_CTX, "%(name)s artıq bu qrupun starostasıdır.") % {"name": _display_name(student)},
                code="already_lead",
                status=409,
            )

        replaced = []
        for membership in current:
            if membership.user_id == student.pk:
                continue
            _deactivate(membership, actor=actor)
            replaced.append(membership)
            _ensure_student_membership(membership.user, organization, actor=actor)

        # Tələbənin BAŞQA əhatəyə (və ya əhatəsiz) bağlı köhnə starosta sətirləri — bir tələbə yalnız
        # öz qrupunun starostası ola bilər (qayda 4).
        stale = list(
            Membership.objects.filter(
                organization=organization, user=student, role__name=LEAD_ROLE_NAME, is_active=True
            ).exclude(scope_unit=group)
        )
        for membership in stale:
            _deactivate(membership, actor=actor)

        membership, created = Membership.objects.update_or_create(
            user=student,
            organization=organization,
            role=role,
            scope_unit=group,
            defaults={"is_active": True, "assigned_by": actor},
        )
        _ensure_student_membership(student, organization, actor=actor, only_if_orphan=False)

        for old in replaced:
            _audit(
                actor,
                organization,
                old,
                request=request,
                reason=reason,
                old_values={"group": group.name, "lead": old.user.username},
                new_values={"event": "replaced", "group": group.name, "group_id": str(group.pk),
                            "lead": "", "replaced_by": student.username},
                created=False,
            )
        _audit(
            actor,
            organization,
            membership,
            request=request,
            reason=reason,
            old_values={
                "group": group.name,
                "lead": ", ".join(old.user.username for old in replaced),
                "stale_scopes": [str(m.scope_unit_id or "") for m in stale],
            },
            new_values={"event": "assigned", "group": group.name, "group_id": str(group.pk),
                        "lead": student.username, "reason": reason},
            created=created,
        )

        _sync_profile(student, organization)
        for old in replaced:
            _sync_profile(old.user, organization)

    if not notify:
        replaced_names = [_display_name(old.user) for old in replaced]
        return {
            "lead": LeadInfo(user_id=student.pk, username=student.username, name=_display_name(student)),
            "replaced": replaced_names,
            "created": created,
        }
    for old in replaced:
        _notify(
            old.user,
            organization,
            title=pgettext(_CTX, "Starosta vəzifəniz başa çatdı"),
            message=pgettext(_CTX, "«%(group)s» qrupunun starostası artıq %(name)s-dir.")
            % {"group": group.name, "name": _display_name(student)},
        )
    _notify(
        student,
        organization,
        title=pgettext(_CTX, "Siz qrupun starostası təyin olundunuz"),
        message=pgettext(
            _CTX,
            "«%(group)s» qrupunun starostası təyin olundunuz. Kabinetdə «Starosta» bölməsi açıldı: qrupun "
            "fənləri, seçmə fənlər, birləşmiş dərslər, cədvəl, imtahanlar və elanlar.",
        )
        % {"group": group.name},
    )
    return {
        "lead": LeadInfo(user_id=student.pk, username=student.username, name=_display_name(student)),
        "replaced": [_display_name(old.user) for old in replaced],
        "created": created,
    }


def remove_group_lead(*, organization, group, actor, reason="", request=None) -> dict:
    """Qrupun aktiv starostasını (starostalarını) götür. Starosta yoxdursa 409."""
    reason = _clean_reason(reason)
    with transaction.atomic():
        group = _lock_group(organization, group)
        current = _active_lead_memberships(organization, group)
        if not current:
            raise GroupLeadError(pgettext(_CTX, "Bu qrupun starostası yoxdur."), code="no_lead", status=409)
        for membership in current:
            _deactivate(membership, actor=actor)
            _ensure_student_membership(membership.user, organization, actor=actor)
            _audit(
                actor,
                organization,
                membership,
                request=request,
                reason=reason,
                old_values={"group": group.name, "lead": membership.user.username},
                new_values={"event": "removed", "group": group.name, "group_id": str(group.pk), "lead": "",
                            "reason": reason},
                created=False,
            )
            _sync_profile(membership.user, organization)
    for membership in current:
        _notify(
            membership.user,
            organization,
            title=pgettext(_CTX, "Starosta vəzifəniz başa çatdı"),
            message=pgettext(_CTX, "«%(group)s» qrupunun starostası vəzifəsindən götürüldünüz.")
            % {"group": group.name},
        )
    return {"removed": [_display_name(m.user) for m in current]}


def group_lead_map(organization, group_ids) -> dict:
    """``{group_id: [LeadInfo, …]}`` — reyestr səhifəsi üçün (2 sorğu, qrup sayından asılı deyil)."""
    group_ids = [gid for gid in group_ids or () if gid]
    if not group_ids or organization is None:
        return {}
    Membership = _model("organizations", "Membership")
    StudentAcademicRecord = _model("registrar", "StudentAcademicRecord")
    rows = list(
        Membership.objects.filter(
            organization=organization, role__name=LEAD_ROLE_NAME, is_active=True, scope_unit_id__in=group_ids
        )
        .select_related("user")
        .order_by("scope_unit_id", "user__last_name", "user__first_name", "pk")
    )
    if not rows:
        return {}
    enrolled = set(
        StudentAcademicRecord.objects.filter(
            organization=organization,
            is_active=True,
            status="enrolled",
            group_id__in={row.scope_unit_id for row in rows},
            student_id__in={row.user_id for row in rows},
        ).values_list("student_id", "group_id")
    )
    out: dict = {}
    for row in rows:
        out.setdefault(row.scope_unit_id, []).append(
            LeadInfo(
                user_id=row.user_id,
                username=row.user.username,
                name=_display_name(row.user),
                not_in_group=(row.user_id, row.scope_unit_id) not in enrolled,
            )
        )
    return out


def broken_lead_memberships(organization):
    """Qaydaya UYĞUN OLMAYAN aktiv starosta sətirləri (``repair_group_leads`` əmri üçün).

    Qaytarır: ``[(membership, problem)]`` — ``problem`` ∈ ``no_scope`` / ``scope_not_group`` /
    ``not_in_group`` / ``duplicate``.
    """
    Membership = _model("organizations", "Membership")
    StudentAcademicRecord = _model("registrar", "StudentAcademicRecord")
    rows = list(
        Membership.objects.filter(organization=organization, role__name=LEAD_ROLE_NAME, is_active=True)
        .select_related("user", "scope_unit")
        .order_by("scope_unit_id", "-updated_at", "pk")
    )
    enrolled = set(
        StudentAcademicRecord.objects.filter(
            organization=organization, is_active=True, status="enrolled", student_id__in={r.user_id for r in rows}
        ).values_list("student_id", "group_id")
    )
    problems = []
    seen_groups: set = set()
    for row in rows:
        unit = row.scope_unit
        if unit is None:
            problems.append((row, "no_scope"))
        elif unit.unit_type != OrgUnitType.GROUP or not unit.is_active:
            problems.append((row, "scope_not_group"))
        elif (row.user_id, unit.pk) not in enrolled:
            problems.append((row, "not_in_group"))
        elif unit.pk in seen_groups:
            problems.append((row, "duplicate"))
        else:
            seen_groups.add(unit.pk)
    return problems


def student_groups(organization, user_id) -> list:
    """Tələbənin aktiv qeydiyyatlı qeydlərinin qrupları (repair əmri üçün)."""
    StudentAcademicRecord = _model("registrar", "StudentAcademicRecord")
    return list(
        StudentAcademicRecord.objects.filter(
            organization=organization,
            student_id=user_id,
            is_active=True,
            status="enrolled",
            group__isnull=False,
            group__is_active=True,
        )
        .select_related("group")
        .order_by("pk")
    )


__all__ = [
    "GroupLeadError",
    "LEAD_ROLE_NAME",
    "LeadInfo",
    "assign_group_lead",
    "broken_lead_memberships",
    "group_lead_map",
    "remove_group_lead",
    "student_groups",
]
