"""Bölgünün təsdiqi: status keçidi + offering sinxronu + bildiriş + audit.

Spec §4.3 və §7.1. Təsdiq İDEMPOTENTDİR: təkrar çağırış yeni offering yaratmır,
mövcud olanları yeniləyir və HEÇ NƏ SİLMİR (jurnal tarixi toxunulmazdır).

2026-09-25: açılış yazısı :mod:`.offering_sync`-ə köçdü — plan təsdiqi, müəllim
təyinatı və bu təsdiq EYNİ yolu işlədir (qaydalar :mod:`.offering_rules`-da).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from ..constants import TaskStatus
from ..models import TeacherAssignment
from . import offering_sync
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
    """Offering sinxronuna düşən sətirlər: fənn + semestr + qrup + kontakt saatı.

    Audit 2026-09-10 P1-7 (düzəliş 2026-09-12): sətirlər ``prefetch_related("groups")``
    ilə gəlir. Ölçmə göstərdi ki, Django 5.2-də ``row.groups.exists()`` də prefetch
    keşini oxuyur (1 və 5 sətir → eyni 4 sorğu); ``row.groups.all()`` isə keşdən
    oxumanın AÇIQ və versiyadan asılı olmayan formasıdır — ona görə bu yazılıb.
    """
    result = []
    for row in rows:
        if not (row.subject_id and row.period_id):
            continue
        if not row.groups.all():
            continue
        result.append(row)
    return result


def sync_offerings(task, *, actor=None, request=None) -> dict:
    """Sətir × qrup → ``registrar.CourseOffering`` (yaradılır/yenilənir, SİLİNMİR).

    Şərtlər (spec §7.1): ``row.subject`` + ``row.period`` + qrup dolu olmalıdır
    (boş ``period`` tədris ili + fəsildən törədilir); xüsusi/fənnsiz sətirlər
    ``skipped`` sayılır. Jurnal sahibi MÜHAZİRƏÇİdir (spec §11.3), amma «Fənn
    təhvili» və ya cədvəl redaktoru ilə qoyulmuş FƏRQLİ müəllim ƏZİLMİR; saat qrup
    başınadır; yeni/boş açılışa qrupun aktiv tələbələri yazılır — bax
    :mod:`.offering_rules` / :mod:`.offering_sync`.

    Köhnə hesabat açarları saxlanılır (``created/updated/skipped/instructor_blocked/
    offering_ids``); ``skipped`` = dəyişməyən açılış + sinxrona düşməyən sətir.
    """
    report = offering_sync.sync_task_offerings(task, actor=actor, request=request, create=True)
    report["skipped"] += report["rows_skipped"]
    return report


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
    # Audit 2026-09-13 tests F-T1: təsdiq də eyni zəncir qapısından keçir —
    # göndərilməmiş TŞ qaralaması burada da «distributed» ola bilməz.
    from .workflow import ensure_distribution_stage

    ensure_distribution_stage(task)
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
            "offerings": offering_sync.compact(sync),
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
