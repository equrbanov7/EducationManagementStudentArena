"""Cədvəlin TOPLU dərci — qaralamadan canlı ``ScheduleSlot``-a (BİR transaksiya).

Avtomatik cədvəl generatoru (``apps.timetable``) qaralamanı öz cədvəllərində
saxlayır; «Dərc et» anında bu modul çağırılır və:

1. **icazə** — hər açılış aktorun ``schedule.manage`` əhatəsində olmalıdır
   (``schedule_manage.scoped_offerings``), əks halda HEÇ NƏ yazılmır (403);
2. **yoxlama** — yeni slotlar eyni semestrin QALAN canlı slotları ilə (müəllim /
   qrup / auditoriya) və öz aralarında toqquşmamalıdır. Axın mühazirəsi
   (``stream`` açarı eyni olan slotlar) eyni müəllim + eyni otaqla bir neçə
   qrupu birlikdə tutur — bu, toqquşma sayılmır;
3. **əvəzləmə** — həmin açılışların köhnə slotları YUMŞAQ silinir
   (``is_deleted``; layihə qaydası — heç nə bazadan getmir), yeniləri toplu yaradılır;
4. **audit** — bir xülasə sətri (mənbə, yaradılan/silinən say, slot id-ləri);
5. **bildiriş** — ``on_commit``-də HƏR ALICIYA BİR bildiriş (müəllimlər + qrupların
   aktiv tələbələri), slot başına yox.

SLOTUN MÜƏLLİMİ (2026-09-25, bölünmüş tədris): generator hər sətir üçün dərsi aparan
müəllimi (``teacher_id``) bilir. O, açılışın jurnal sahibindən FƏRQLİDİRSƏ
``ScheduleSlot.instructor``-a yazılır, EYNİDİRSƏ NULL qalır (jurnal sahibi dəyişəndə slot
onu izləsin). Toqquşma yoxlaması hər iki tərəfdə EFFEKTİV müəllimlə aparılır
(``schedule.effective_instructor_id``); yazılan müəllim AKTİV ``grade.input`` üzvü
olmalıdır (PostgreSQL qoruyucusu 0082 ilə eyni qayda — əks halda 400, heç nə yazılmır).

``group_buildings`` isə generatorun otaq təklifi üçün qrupun korpus defoltunu
(``campus``) oxuyur — registrar-ın daxili modulu kənara açılmasın deyə buradan verilir.
"""

from __future__ import annotations

import datetime
import logging

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import campus, schedule_conflicts, schedule_manage, schedule_slot_teachers
from apps.registrar.models import AcademicStatus, ScheduleSlot, SlotKind, StudentAcademicRecord, WeekType
from apps.registrar.schedule import effective_instructor_id, stored_instructor_id

logger = logging.getLogger(__name__)

_CTX = "registrar.schedule_publish"
_RESOURCE_TYPE = "registrar.ScheduleSlot"
_EVENT = "schedule_published"


class PublishError(Exception):
    """Dərc rədd edildi — ``errors`` (məs. ``conflicts`` siyahısı) UI-a gedir."""

    def __init__(self, code: str, message: str, errors=None, status: int = 400):
        errors = dict(errors or {})
        super().__init__(code, message, errors, status)
        self.code = code
        self.message = message
        self.errors = errors
        self.status = status


def group_buildings(organization, groups) -> dict:
    """``{group_id: korpus adı}`` — ``Organization.settings["campuses"]`` xəritəsindən."""
    return {str(group.pk): campus.default_building_for_group(organization, group) for group in groups}


def _time(value):
    if isinstance(value, datetime.time):
        return value
    try:
        return datetime.time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _clean(slot) -> dict | None:
    weekday = int(slot.get("weekday") or 0)
    start, end = _time(slot.get("start_time")), _time(slot.get("end_time"))
    week_type = str(slot.get("week_type") or WeekType.ALL)
    kind = str(slot.get("kind") or SlotKind.LECTURE)
    if not 1 <= weekday <= 7 or start is None or end is None or end <= start:
        return None
    if week_type not in dict(WeekType.choices) or kind not in dict(SlotKind.choices):
        return None
    return {
        "offering_id": str(slot.get("offering_id") or ""),
        "weekday": weekday,
        "start_time": start,
        "end_time": end,
        "week_type": week_type,
        "kind": kind,
        "room": str(slot.get("room") or "").strip()[:64],
        # «12» / 12 / None → pk (müqayisə və yazı eyni tipdə getsin); yararsız dəyər → None (jurnal sahibi).
        "teacher_id": schedule_slot_teachers.user_pk(slot.get("teacher_id")),
        "stream": str(slot.get("stream") or ""),
    }


def _overlap(a, b) -> bool:
    return (
        a["weekday"] == b["weekday"]
        and schedule_conflicts.time_ranges_overlap(a["start_time"], a["end_time"], b["start_time"], b["end_time"])
        and schedule_conflicts.week_types_overlap(a["week_type"], b["week_type"])
    )


def _conflict_row(kind, new, other, offerings, labels) -> dict:
    offering = offerings.get(new["offering_id"])
    return {
        "kind": kind,
        "kind_label": schedule_conflicts.kind_label(kind),
        "offering_id": new["offering_id"],
        "subject": getattr(getattr(offering, "subject", None), "name", "") or "",
        "group": getattr(getattr(offering, "group", None), "name", "") or "",
        "weekday": new["weekday"],
        "start_time": new["start_time"].strftime("%H:%M"),
        "week_type": new["week_type"],
        "other": labels.get(id(other), ""),
    }


def find_conflicts(*, organization, period, rows, offerings, replaced_ids) -> list[dict]:
    """Yeni slotların canlı cədvəllə və öz aralarında toqquşmaları (heç nə yazmır)."""
    existing = []
    labels = {}
    queryset = (
        ScheduleSlot.objects.filter(organization=organization, is_parked=False, offering__period=period)
        .exclude(offering_id__in=list(replaced_ids))
        .select_related("offering", "offering__subject", "offering__group")
    )
    for slot in queryset:
        row = {
            "weekday": slot.weekday,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "week_type": slot.week_type,
            "room": (slot.room or "").strip().lower(),
            "teacher_id": effective_instructor_id(slot),
            "group_id": slot.offering.group_id,
            "stream": "",
        }
        labels[id(row)] = "%s · %s" % (
            getattr(slot.offering.subject, "name", "") or "",
            getattr(slot.offering.group, "name", "") or "",
        )
        existing.append(row)
    found = []
    prepared = []
    for new in rows:
        offering = offerings.get(new["offering_id"])
        prepared.append(
            {
                **new,
                "room": new["room"].lower(),
                "teacher_id": new["teacher_id"] or getattr(offering, "instructor_id", None),
                "group_id": getattr(offering, "group_id", None),
            }
        )
    for index, new in enumerate(prepared):
        others = existing + prepared[index + 1 :]
        for other in others:
            if not _overlap(new, other):
                continue
            same_stream = bool(new["stream"]) and new["stream"] == other.get("stream")
            if new["group_id"] and new["group_id"] == other["group_id"]:
                found.append(_conflict_row(schedule_conflicts.KIND_GROUP, rows[index], other, offerings, labels))
            elif new["teacher_id"] and new["teacher_id"] == other["teacher_id"] and not same_stream:
                found.append(_conflict_row(schedule_conflicts.KIND_TEACHER, rows[index], other, offerings, labels))
            elif new["room"] and new["room"] == other["room"] and not same_stream:
                found.append(_conflict_row(schedule_conflicts.KIND_ROOM, rows[index], other, offerings, labels))
    return found


def _recipients(organization, offerings, teacher_ids):
    from django.contrib.auth import get_user_model

    teacher_ids = {pk for pk in teacher_ids if pk}
    teacher_ids |= {o.instructor_id for o in offerings if o.instructor_id}
    teachers = list(get_user_model().objects.filter(pk__in=teacher_ids))
    group_ids = {o.group_id for o in offerings if o.group_id}
    students = [
        record.student
        for record in StudentAcademicRecord.objects.filter(
            organization=organization, group_id__in=group_ids, status=AcademicStatus.ENROLLED
        ).select_related("student")
        if record.student_id and record.student_id not in teacher_ids
    ]
    unique_students = list({student.pk: student for student in students}.values())
    return teachers, unique_students


def _notify(organization, period, offerings, teacher_ids, created) -> int:
    from apps.notifications.public import create_notification_for_users

    teachers, students = _recipients(organization, offerings, teacher_ids)
    link = "%s?section=my-schedule" % reverse("accounts:profile")
    title = pgettext(_CTX, "Dərs cədvəli dərc edildi: %(period)s") % {"period": getattr(period, "name", "")}
    metadata = {"event": _EVENT, "period_id": str(getattr(period, "pk", "")), "slots": created}
    sent = 0
    if teachers:
        sent += len(
            create_notification_for_users(
                recipients=teachers,
                title=title,
                message=pgettext(_CTX, "Yeni həftəlik cədvəliniz hazırdır — dərslərinizi yoxlayın."),
                link=link,
                organization=organization,
                metadata=metadata,
            )
        )
    if students:
        sent += len(
            create_notification_for_users(
                recipients=students,
                title=title,
                message=pgettext(_CTX, "Qrupunuzun yeni həftəlik dərs cədvəli dərc olundu."),
                link=link,
                organization=organization,
                metadata=metadata,
            )
        )
    return sent


def publish_slots(
    *, actor, organization, period, offering_ids, slots, request=None, source: str = "", reason: str = ""
) -> dict:
    """``offering_ids`` açılışlarının canlı cədvəlini ``slots`` ilə əvəz et (bax modul şərhi)."""
    from core.audit import log_action
    from core.constants import AuditAction

    ids = sorted({str(pk) for pk in offering_ids if pk})
    offerings = {
        str(o.pk): o
        for o in schedule_manage.scoped_offerings(actor, organization, period=period)
        .filter(pk__in=ids)
        .select_related("subject", "group")
    }
    if len(offerings) != len(ids):
        raise PublishError(
            "permission_denied",
            pgettext(_CTX, "Bəzi açılışlar sizin səlahiyyət sahənizdən kənardadır — cədvəl dərc edilmədi."),
            status=403,
        )
    end_date = getattr(period, "end_date", None)
    if end_date and end_date < timezone.localdate():
        raise PublishError("period_closed", pgettext(_CTX, "Bu semestr bitib — cədvəl dərc edilə bilməz."))
    rows = []
    for raw in slots:
        row = _clean(raw)
        if row is None or row["offering_id"] not in offerings:
            raise PublishError("invalid", pgettext(_CTX, "Qaralamada yararsız slot var — yenidən yaradın."))
        row["instructor_id"] = stored_instructor_id(offerings[row["offering_id"]], row["teacher_id"])
        rows.append(row)
    overrides = {row["instructor_id"] for row in rows if row["instructor_id"]}
    if overrides - schedule_slot_teachers.authorized_teacher_ids(organization, overrides):
        raise PublishError(
            "invalid",
            pgettext(
                _CTX,
                "Qaralamadakı bəzi müəllimlərin bu təşkilatda aktiv müəllim üzvlüyü yoxdur — "
                "dərs yükünü yoxlayıb qaralamanı yenidən yaradın.",
            ),
        )
    conflicts = find_conflicts(
        organization=organization, period=period, rows=rows, offerings=offerings, replaced_ids=ids
    )
    if conflicts:
        raise PublishError(
            "conflict",
            pgettext(_CTX, "Dərc olunmadı: canlı cədvəllə %(count)s toqquşma var.") % {"count": len(conflicts)},
            errors={"conflicts": conflicts[:50]},
            status=409,
        )
    now = timezone.now()
    with transaction.atomic():
        old = ScheduleSlot.all_objects.filter(organization=organization, offering_id__in=ids, is_deleted=False)
        removed_ids = [str(pk) for pk in old.values_list("pk", flat=True)]
        old.update(is_deleted=True, deleted_at=now, is_parked=False, updated_at=now)
        created = ScheduleSlot.objects.bulk_create(
            [
                ScheduleSlot(
                    organization=organization,
                    offering_id=row["offering_id"],
                    weekday=row["weekday"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    room=row["room"],
                    week_type=row["week_type"],
                    kind=row["kind"],
                    created_by=actor if getattr(actor, "pk", None) else None,
                    instructor_id=row["instructor_id"],
                )
                for row in rows
            ]
        )
        summary = {
            "source": source,
            "period_id": str(getattr(period, "pk", "")),
            "offerings": len(ids),
            "created": len(created),
            "removed": len(removed_ids),
            "created_ids": [str(slot.pk) for slot in created],
            "removed_ids": removed_ids,
            "instructor_overrides": sum(1 for row in rows if row["instructor_id"]),
        }
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values=summary,
            reason=reason,
            request=request,
            resource_type=_RESOURCE_TYPE,
            resource_id=source or str(getattr(period, "pk", "")),
            resource_repr=pgettext(_CTX, "Cədvəlin toplu dərci"),
        )
        teacher_ids = {row["teacher_id"] for row in rows}
        offering_list = list(offerings.values())

        def _send():
            try:
                _notify(organization, period, offering_list, teacher_ids, len(created))
            except Exception:  # pragma: no cover — bildiriş dərci geri qaytarmır
                logger.exception("schedule publish notification failed")

        transaction.on_commit(_send)
    return {"created": len(created), "removed": len(removed_ids), "slot_ids": summary["created_ids"]}


__all__ = ["PublishError", "find_conflicts", "group_buildings", "publish_slots"]
