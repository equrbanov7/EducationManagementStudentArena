"""Tələbə hərəkəti — AKTOR qatı (icazə + scope + tutum + bildiriş + audit).

Domen məntiqi burada TƏKRARLANMIR: state maşını, qrup köçürməsi və ledger
yazısı :mod:`apps.registrar.movements`-dədir. Burada yalnız «kimin haqqı var,
nəyə toxuna bilər və nəticədən kim xəbər tutmalıdır» sualları cavablanır.

İKİQAT SƏLAHİYYƏT QAPISI (əsasnamə 5.5):

* ``student.movement``       — ƏMR yazmaq hüququ (bu səth);
* ``people.manage_academic`` — akademik qeydə TOXUNMAQ hüququ (mexanizm).

Hər ikisi tələb olunur. Səbəb: kataloqdan qrup köçürməsi apara bilən rol
(dekan) avtomatik XARİC ETMƏ əmri yazmamalıdır, əmr yazan rol da mexanizmə
çıxışsız qalmamalıdır.
"""

from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError

from core.audit import log_action
from core.constants import AuditAction

from ..rim.policy import RimAccessError
from .academic import load_record, scoped_groups_qs
from .permissions import PERM_MANAGE_ACADEMIC, PERM_MOVEMENT, PERM_REGISTRY_VIEW

_AUDIT_RESOURCE = "accounts.people.movement"

#: Bildirişin gövdəsində göstərilən maksimum səbəb uzunluğu.
_NOTIFY_REASON_CHARS = 240

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")


def _require(actor) -> None:
    if not actor.can_move_students:
        raise RimAccessError("permission_denied", "Tələbə hərəkəti əmri yazmaq üçün icazəniz yoxdur.")
    if not actor.can_manage_academic:
        raise RimAccessError(
            "permission_denied",
            "Akademik qeydə toxunmaq üçün `people.manage_academic` icazəsi də tələb olunur.",
        )


def parse_date(raw, *, field: str, required: bool = True):
    text = str(raw or "").strip()
    if not text:
        if required:
            raise RimAccessError(f"{field}_required", "Tarix məcburidir.", status=400)
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise RimAccessError(f"{field}_invalid", "Tarix tanınmadı (gg.aa.iiii formatını işlədin).", status=400)


def registry_records_qs(actor, *, request=None):
    """Reyestrin OXU dəsti — `student.registry_view` scope-u (fail-closed).

    ``academic.scoped_records_qs`` QƏSDƏN işlədilmir: o, İDARƏ scope-udur
    (`people.manage_academic`). Reyestrə baxan, amma əmr yaza bilməyən rol
    (dekan, koordinator) tarixçəni görməli, yazı səthini isə GÖRMƏMƏLİDİR.
    Əhatəsiz istifadəçi BOŞ dəst alır — bütün universitet DEYİL (§8/8).
    """
    from apps.registrar.models import StudentAcademicRecord

    organization = actor.organization
    if organization is None or not actor.can_view_registry:
        return StudentAcademicRecord.objects.none()
    scope = actor.scope_for(PERM_REGISTRY_VIEW, request=request)
    if not scope.has_structure_access:
        return StudentAcademicRecord.objects.none()
    records = StudentAcademicRecord.objects.filter(organization=organization)
    if not scope.is_org_wide:
        records = records.filter(scope.unit_subtree_q(path_field="group__path", id_field="group_id"))
    return records


def _uuid_or_none(raw):
    """Qeyri-UUID id `filter(pk=...)`-də ValidationError → 500 verirdi (QA 2026-09-05 STUDENT-MGMT-05)."""
    import uuid

    try:
        return uuid.UUID(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def load_registry_record(actor, record_id, *, request=None):
    """Reyestr sahəsindən akademik qeyd — yoxdursa 404 (mövcudluq sızmır)."""
    record_id = _uuid_or_none(record_id)
    if not record_id:
        raise RimAccessError("record_not_found", "Akademik qeyd tapılmadı.", status=404)
    record = (
        registry_records_qs(actor, request=request)
        .select_related("student", "student__profile", "program", "curriculum", "group", "organization")
        .filter(pk=record_id)
        .first()
    )
    if record is None:
        raise RimAccessError("record_not_found", "Akademik qeyd tapılmadı.", status=404)
    return record


def movement_kinds() -> list:
    """Dialoqun «Əməliyyatın növü» radio kartları (kataloqdan — TƏK mənbə)."""
    from apps.registrar.movements import RULES
    from core.ui import status_catalog

    rows = []
    for status in status_catalog.family("student_movement"):
        rule = RULES.get(status.key)
        if rule is None:  # pragma: no cover — kataloq ↔ qayda uyğunsuzluğu
            continue
        rows.append(
            {
                "key": status.key,
                "label": str(status.label),
                "tone": status.tone,
                "requires_group": rule.requires_group,
                "requires_program": rule.requires_program,
                "requires_form": rule.requires_form,
                "requires_until": rule.requires_until,
                "from_statuses": list(rule.from_statuses),
            }
        )
    return rows


def _target_group(actor, group_id, *, request):
    if not group_id:
        return None
    group_id = _uuid_or_none(group_id)
    group = scoped_groups_qs(actor, request=request).filter(pk=group_id).first() if group_id else None
    if group is None:
        raise RimAccessError("target_group_outside_scope", "Hədəf qrup sizin sahənizdə deyil.", status=404)
    return group


def _assert_capacity(actor, group) -> None:
    """Qrup tutumu — handoff §5/09 «qrup tutumu yoxlanılır»."""
    from ..student_groups import group_capacity, occupancy_map

    capacity = group_capacity(group)
    taken = occupancy_map(actor.organization, [group.pk]).get(str(group.pk), 0)
    if taken >= capacity:
        raise RimAccessError(
            "group_full",
            "«%s» qrupunda boş yer yoxdur (%d / %d)." % (group.name, taken, capacity),
            status=409,
        )


def _target_program(actor, program_id):
    if not program_id:
        return None
    from apps.registrar.models import Program

    program_id = _uuid_or_none(program_id)
    program = (
        Program.objects.filter(organization=actor.organization, pk=program_id, is_active=True).first()
        if program_id
        else None
    )
    if program is None:
        raise RimAccessError("target_program_not_found", "Hədəf ixtisas tapılmadı.", status=404)
    return program


def _notify(record, movement, *, organization) -> None:
    """Tələbə + proqram koordinatoru/dekan xəbərdar edilir (best-effort).

    Bildiriş DOMEN ƏMƏLİNİ BLOKLAMIR: hərəkət artıq yazılıb, bildirişin
    uğursuzluğu onu geri qaytarmamalıdır.
    """
    try:
        from apps.notifications.public import create_notification, create_notification_for_users

        title = str(movement.kind_label)
        body = "%s → %s · Əmr %s (%s)" % (
            movement.from_label or "—",
            movement.to_label or "—",
            movement.order_number,
            movement.order_date,
        )
        create_notification(
            recipient=record.student,
            title=title,
            message=body,
            organization=organization,
            metadata={"movement_id": str(movement.pk), "kind": movement.kind},
        )
        watchers = _programme_watchers(organization, record)
        if watchers:
            create_notification_for_users(
                recipients=watchers,
                title="%s — %s" % (title, record.student.get_full_name() or record.student.username),
                message=body,
                organization=organization,
                metadata={"movement_id": str(movement.pk), "kind": movement.kind},
            )
    except Exception:  # noqa: BLE001 — bildiriş domen əməlini bloklamır
        pass


def _programme_watchers(organization, record) -> list:
    """İxtisasın koordinatoru + fakültənin dekanı (aktiv üzvlüklər)."""
    from django.contrib.auth import get_user_model

    from apps.organizations.models import Membership

    group = record.group
    if group is None:
        return []
    unit_ids = [part for part in str(group.path or "").split("/") if part]
    if not unit_ids:
        return []
    user_ids = (
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            role__is_active=True,
            role__name__in=("program_coordinator", "dean"),
            scope_unit_id__in=unit_ids,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    if not user_ids:
        return []
    return list(get_user_model().objects.filter(pk__in=list(user_ids), is_active=True))


def create_movement(
    actor,
    *,
    record_id,
    kind,
    order_number,
    order_date,
    reason,
    request=None,
    target_group_id="",
    target_program_id="",
    target_form="",
    effective_until="",
    document=None,
) -> dict:
    """Hərəkət əmrini yazır və nəticəni UI müqaviləsində qaytarır."""
    from apps.registrar import movements as domain

    _require(actor)
    record = load_record(actor, record_id, request=request)

    try:
        rule = domain.rule_for(kind)
    except domain.MovementError as exc:  # naməlum növ → 500 deyil, JSON xəta (STUDENT-MGMT-04)
        raise RimAccessError(exc.code, str(exc.args[1] if len(exc.args) > 1 else exc), status=400) from exc
    group = _target_group(actor, target_group_id, request=request) if rule.requires_group or target_group_id else None
    if group is not None:
        _assert_capacity(actor, group)
    program = _target_program(actor, target_program_id) if rule.requires_program or target_program_id else None
    until = parse_date(effective_until, field="effective_until", required=rule.requires_until)

    period = record.organization.academic_periods.filter(is_current=True, is_active=True).first()
    previous_status = record.status
    previous_group = str(getattr(record.group, "name", "") or "")

    try:
        movement = domain.create_movement(
            record=record,
            kind=kind,
            order_number=order_number,
            order_date=parse_date(order_date, field="order_date"),
            reason=reason,
            actor=actor.user,
            period=period,
            new_group=group,
            new_program=program,
            new_form=str(target_form or "").strip(),
            effective_until=until,
            document=document,
        )
    except domain.MovementError as exc:
        raise RimAccessError(exc.code, exc.message, status=exc.status) from exc
    except ValidationError as exc:
        messages = getattr(exc, "messages", None) or [str(exc)]
        raise RimAccessError("movement_rejected", " ".join(str(item) for item in messages), status=409) from exc

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=actor.organization,
        obj=record,
        reason=movement.reason,
        request=request,
        resource_type=_AUDIT_RESOURCE,
        resource_id=str(record.pk),
        resource_repr=(record.student.get_full_name() or record.student.username).strip(),
        old_values={"status": previous_status, "group": previous_group},
        new_values={"status": record.status, "group": str(getattr(record.group, "name", "") or "")},
        changes={
            "action": "people.student_movement",
            "kind": movement.kind,
            "movement_id": str(movement.pk),
            # ⚠️ `str()` MƏCBURİDİR: lazy tərcümə proxy-si JSONField-ə düşsə
            # INSERT çökür və audit qatındakı `except` onu udur (layihə yaddaşı).
            "kind_label": str(movement.kind_label),
            "order_number": movement.order_number,
            "order_date": str(movement.order_date),
        },
    )
    _notify(record, movement, organization=actor.organization)
    return movement_row(movement)


def movement_row(movement) -> dict:
    """Ledger sətrinin UI müqaviləsi (cədvəl + tarixçə eyni formadan oxuyur)."""
    record = movement.record
    student = getattr(record, "student", None)
    return {
        "id": str(movement.pk),
        "record_id": str(movement.record_id),
        "kind": movement.kind,
        "kind_label": str(movement.kind_label),
        "student_name": (student.get_full_name() or student.username).strip() if student else "",
        "student_code": str(getattr(getattr(student, "profile", None), "institutional_identifier", "") or ""),
        "from_label": movement.from_label,
        "to_label": movement.to_label,
        "reason": movement.reason,
        "order_number": movement.order_number,
        "order_date": movement.order_date.isoformat() if movement.order_date else "",
        "effective_until": movement.effective_until.isoformat() if movement.effective_until else "",
        "actor_name": movement.actor_name,
        "has_document": bool(movement.document),
        "created_at": movement.created_at.isoformat() if movement.created_at else "",
        # Bərpa əmrindən sonra giriş avtomatik açılmır — səbəb registrar.movements-də.
        "access_notice": str(getattr(movement, "access_notice", "") or ""),
    }


def student_movements(actor, *, record_id, request=None) -> list:
    """Bir tələbənin hərəkət tarixçəsi (drawer «Hərəkət tarixçəsi» bloku)."""
    if not actor.can_view_registry:
        raise RimAccessError("permission_denied", "Tələbə reyestrinə baxış icazəniz yoxdur.")
    from apps.registrar import movements as domain

    record = load_registry_record(actor, record_id, request=request)
    return [movement_row(movement) for movement in domain.movements_for(record).select_related("record__student")]


__all__ = [
    "PERM_MANAGE_ACADEMIC",
    "PERM_MOVEMENT",
    "PERM_REGISTRY_VIEW",
    "create_movement",
    "load_registry_record",
    "movement_kinds",
    "movement_row",
    "parse_date",
    "registry_records_qs",
    "student_movements",
]
