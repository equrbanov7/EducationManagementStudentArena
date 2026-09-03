"""Bölgünün təsdiqi: status keçidi + offering sinxronu + bildiriş + audit.

Spec §4.3 və §7.1. Təsdiq İDEMPOTENTDİR: təkrar çağırış yeni offering yaratmır,
mövcud olanları yeniləyir və HEÇ NƏ SİLMİR (jurnal tarixi toxunulmazdır).
"""

from __future__ import annotations

import logging

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import CONTACT_TOTAL_FIELDS, Activity, TaskStatus
from ..models import TeacherAssignment
from .assignments import balance_for_rows
from .scoping import WorkloadDenied, ensure_can_distribute

logger = logging.getLogger(__name__)


def distribution_readiness(task) -> dict:
    """Bölgü təsdiqə hazırdırmı — sətir-sətir qalıq xülasəsi."""
    rows = list(task.rows.all().prefetch_related("groups"))
    balance = balance_for_rows(rows)
    incomplete = []
    for row in rows:
        info = balance.get(str(row.pk), {})
        if info.get("has_teaching") and not info.get("teaching_complete"):
            incomplete.append(
                {
                    "row_id": str(row.pk),
                    "subject": row.subject_label,
                    "activities": {
                        key: value for key, value in (info.get("activities") or {}).items() if not value["is_complete"]
                    },
                }
            )
    vacant_hours = int(
        TeacherAssignment.objects.filter(row__task=task, teacher__isnull=True).aggregate(total=Sum("hours"))["total"]
        or 0
    )
    return {
        "is_ready": not incomplete,
        "incomplete_rows": incomplete,
        "row_count": len(rows),
        "vacant_hours": vacant_hours,
        "sync_candidates": len(_syncable_rows(rows)),
    }


def _syncable_rows(rows) -> list:
    """Offering sinxronuna düşən sətirlər: fənn + semestr + qrup + kontakt saatı."""
    result = []
    for row in rows:
        if not (row.subject_id and row.period_id):
            continue
        if not row.groups.exists():
            continue
        result.append(row)
    return result


def _instructor_for_row(row):
    """Jurnal sahibi: MÜHAZİRƏÇİ, yoxdursa ilk (vakant olmayan) təyinat (spec §11.3)."""
    assignments = list(row.assignments.select_related("teacher").order_by("activity", "created_at"))
    lecture = [a for a in assignments if a.activity == Activity.LECTURE and a.teacher_id]
    if lecture:
        return lecture[0].teacher
    others = [a for a in assignments if a.teacher_id]
    return others[0].teacher if others else None


def _write_offering(CourseOffering, *, organization, row, group, instructor, lesson_hours):
    """Bir açılışı yaradır/yeniləyir; müəllim DB qapısından keçmirsə ONSUZ yazır.

    ⚠️ REGİSTRAR QAPISI: ``registrar_guard_active_member`` trigger-i
    (`registrar/0041`) ``CourseOffering.instructor`` üçün həmin istifadəçinin
    aktiv üzvlükdə ``grade.input`` (və ya ``grade.*`` / ``*``) daşımasını TƏLƏB
    EDİR. Köçürülmüş tenantlarda müəllim rolu bəzən bu açarı daşımır — belə halda
    BÜTÜN bölgü təsdiqi geri qayıtmamalıdır: açılış MÜƏLLİMSİZ yaradılır və
    hesabatda ``instructor_blocked`` kimi görünür (jurnal sahibi sonradan
    «Fənn təhvili» ilə təyin edilir).

    Qaytarır: ``(outcome, offering, instructor_blocked)``.
    """
    from django.db import IntegrityError, transaction

    lookup = {
        "organization": organization,
        "subject_id": row.subject_id,
        "period_id": row.period_id,
        "group": group,
    }
    existing = CourseOffering.objects.filter(**lookup).first()

    if existing is None:
        for candidate in (instructor, None):
            try:
                with transaction.atomic():
                    offering = CourseOffering.objects.create(
                        **lookup,
                        instructor=candidate,
                        lesson_hours=lesson_hours,
                        is_active=True,
                    )
                return "created", offering, bool(candidate is None and instructor is not None)
            except IntegrityError:
                if candidate is None:
                    raise
                logger.warning(
                    "workload: instructor %s rejected by registrar guard (subject=%s)",
                    getattr(instructor, "pk", None),
                    row.subject_id,
                )
        return "skipped", None, True

    changed = []
    if instructor is not None and existing.instructor_id != getattr(instructor, "pk", None):
        existing.instructor = instructor
        changed.append("instructor")
    if lesson_hours and existing.lesson_hours != lesson_hours:
        existing.lesson_hours = lesson_hours
        changed.append("lesson_hours")
    if not changed:
        return "skipped", existing, False
    try:
        with transaction.atomic():
            existing.save(update_fields=changed + ["updated_at"])
        return "updated", existing, False
    except IntegrityError:
        if "instructor" not in changed:
            raise
        existing.refresh_from_db()
        rest = [field for field in changed if field != "instructor"]
        if not rest:
            return "skipped", existing, True
        with transaction.atomic():
            existing.save(update_fields=rest + ["updated_at"])
        return "updated", existing, True


def sync_offerings(task, *, actor=None, request=None) -> dict:
    """Sətir × qrup → ``registrar.CourseOffering`` (yaradılır/yenilənir, SİLİNMİR).

    Şərtlər (spec §7.1): ``row.subject`` + ``row.period`` + qrup dolu olmalıdır;
    xüsusi sətirlər (Təcrübə, Buraxılış işi, fənnsiz) ``skipped`` sayılır.
    Jurnal sahibi: MÜHAZİRƏÇİ, yoxdursa ilk vakant-olmayan təyinat (spec §11.3).
    """
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    counters = {"created": 0, "updated": 0, "skipped": 0, "instructor_blocked": 0}
    offering_ids: list[str] = []
    rows = list(task.rows.all().prefetch_related("groups", "assignments__teacher"))
    for row in rows:
        if not (row.subject_id and row.period_id):
            counters["skipped"] += 1
            continue
        groups = list(row.groups.all())
        if not groups:
            counters["skipped"] += 1
            continue
        instructor = _instructor_for_row(row)
        lesson_hours = sum(int(getattr(row, field, 0) or 0) for field in CONTACT_TOTAL_FIELDS)
        for group in groups:
            outcome, offering, blocked = _write_offering(
                CourseOffering,
                organization=task.organization,
                row=row,
                group=group,
                instructor=instructor,
                lesson_hours=lesson_hours,
            )
            counters[outcome] += 1
            if blocked:
                counters["instructor_blocked"] += 1
            if offering is not None:
                offering_ids.append(str(offering.pk))
    return {**counters, "offering_ids": offering_ids}


def _notify_teachers(task) -> int:
    """Hər müəllimə «Dərs yükü təyin edildi» bildirişi (fənn + cəmi saat)."""
    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import create_notification
    except Exception:  # pragma: no cover — bildiriş modulu yoxdursa axın dayanmır
        logger.warning("workload: notifications unavailable")
        return 0

    totals: dict = {}
    assignments = TeacherAssignment.objects.filter(row__task=task, teacher__isnull=False).select_related(
        "teacher", "row", "row__subject"
    )
    for assignment in assignments:
        bucket = totals.setdefault(assignment.teacher, {"hours": 0, "subjects": set()})
        bucket["hours"] += int(assignment.hours or 0)
        bucket["subjects"].add(assignment.row.subject_label)

    sent = 0
    for teacher, payload in totals.items():
        subjects = sorted(payload["subjects"])
        head = subjects[0] if subjects else ""
        if len(subjects) > 1:
            head = f"{head} + {len(subjects) - 1}"
        try:
            create_notification(
                recipient=teacher,
                # `InAppNotification.title` = CharField(max_length=255) — fənn adları
                # uzun ola bildiyi üçün başlıq kəsilir (mətnin özü `message`-dədir).
                title=f"Dərs yükü təyin edildi: {head} — {payload['hours']} saat"[:255],
                message=(
                    f"{task.academic_year} tədris ili üçün dərs yükünüz təsdiqləndi. "
                    f"Fənn sayı: {len(subjects)}, cəmi {payload['hours']} saat. "
                    "«Dərs yüküm» bölməsindən baxa bilərsiniz."
                ),
                link="/accounts/profile/?section=my-workload",
                notification_type=NotificationType.ASSIGNMENT,
                metadata={
                    "event": "workload_assigned",
                    "task_id": str(task.pk),
                    "academic_year": task.academic_year,
                    "hours": payload["hours"],
                },
                organization=task.organization,
            )
            sent += 1
        except Exception:  # noqa: BLE001 — bildiriş axını bölgünü dayandırmır
            logger.warning("workload: notification failed for teacher %s", teacher.pk, exc_info=True)
    return sent


@transaction.atomic
def confirm_distribution(*, task, actor, allow_vacant: bool = True, request=None) -> dict:
    """Bölgünü təsdiqlə → ``distributed`` + offering sinxronu + bildirişlər."""
    ensure_can_distribute(actor, task.chair_id)
    # `APPROVED` — F2 zəncirinin çıxışı: dekanlıq təsdiqindən sonra kafedra
    # bölgüyə başlayır; heç bir təyinat edilməyibsə status hələ `approved`-dur.
    if task.status not in (
        TaskStatus.DRAFT,
        TaskStatus.APPROVED,
        TaskStatus.DISTRIBUTING,
        TaskStatus.AMENDED,
    ):
        raise WorkloadDenied("workload.not_confirmable", "Bu statusda bölgü təsdiqlənə bilməz.")

    readiness = distribution_readiness(task)
    if not readiness["is_ready"]:
        raise WorkloadDenied(
            "workload.distribution_incomplete",
            "Bütün dərs sətirləri tam bölünməlidir (qalan saatlar «Vakant» kimi də yazıla bilər).",
        )
    if not allow_vacant and readiness["vacant_hours"]:
        raise WorkloadDenied("workload.vacant_not_allowed", "Vakant saatlar qalıb.")

    task.status = TaskStatus.DISTRIBUTED
    task.distributed_by = getattr(actor, "user", None)
    task.distributed_at = timezone.now()
    task.save(update_fields=["status", "distributed_by", "distributed_at", "updated_at"])

    sync = sync_offerings(task, actor=actor, request=request)
    notified = _notify_teachers(task)

    log_action(
        AuditAction.UPDATE,
        user=getattr(actor, "user", None),
        organization=task.organization,
        obj=task,
        new_values={
            "status": TaskStatus.DISTRIBUTED.value,
            "offerings_created": sync["created"],
            "offerings_updated": sync["updated"],
            "notified_teachers": notified,
            "vacant_hours": readiness["vacant_hours"],
        },
        reason="workload.distribution_confirmed",
        request=request,
        resource_type="workload.TeachingTask",
        resource_id=str(task.pk),
        resource_repr=f"{task.chair_id} · {task.academic_year}",
    )
    return {"status": task.status, "sync": sync, "notified": notified, "readiness": readiness}


__all__ = ["confirm_distribution", "distribution_readiness", "sync_offerings"]
