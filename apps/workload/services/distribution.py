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

_NOTIFY_CTX = "workload.notify"


def distribution_readiness(task, *, rows=None, balance=None) -> dict:
    """Bölgü təsdiqə hazırdırmı — sətir-sətir qalıq xülasəsi.

    ``rows``/``balance`` — çağıran tapşırığın BÜTÜN sətirlərini (süzgəcsiz, ``groups`` prefetch ilə) artıq
    yükləyibsə ötürür (PERF-1 F-09: `rows` endpoint-i eyni sətirləri iki dəfə oxuyurdu). ``subject``
    select_related — natamam sətrin `subject_label`-i sətir başına sorğu açmasın.
    """
    if rows is None:
        rows = list(task.rows.all().select_related("subject").prefetch_related("groups"))
        balance = None
    if balance is None:
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


def teacher_loads(task) -> dict:
    """Müəllim → bölgü imzası (sətir, fəaliyyət, saat, saathesabı) — təsdiqdən ƏVVƏL götürülür.

    Yenidən təsdiqdə (``confirm_distribution(loads_before=…)``) yalnız imzası dəyişən / yeni müəllimə
    bildiriş getsin deyə (sahib 2026-10-17 «yeni müəllimlərə bildiriş getsin»)."""
    loads: dict = {}
    rows = TeacherAssignment.objects.filter(row__task=task, teacher__isnull=False).values_list(
        "teacher_id", "row_id", "activity", "hours", "is_hourly_paid"
    )
    for teacher_id, row_id, activity, hours, hourly in rows:
        loads.setdefault(teacher_id, []).append((str(row_id), str(activity), int(hours or 0), bool(hourly)))
    return {teacher_id: tuple(sorted(items)) for teacher_id, items in loads.items()}


def changed_teacher_ids(task, before: dict) -> set:
    """``before``-dan sonra bölgüsü YENİ yaranan və ya dəyişən müəllimlər (yükü tam götürülən sayılmır)."""
    return {teacher_id for teacher_id, sig in teacher_loads(task).items() if before.get(teacher_id) != sig}


def _notify_teachers(task, only: set | None = None) -> int:
    """Hər müəllimə «Dərs yükü təyin edildi» bildirişi (fənn + cəmi saat); ``only`` — yalnız bu müəllimlər."""
    if only is not None and not only:
        return 0
    try:
        from apps.notifications.models import NotificationType
        from apps.notifications.public import LText, create_notification
    except Exception:  # pragma: no cover — bildiriş modulu yoxdursa axın dayanmır
        logger.warning("workload: notifications unavailable")
        return 0

    totals: dict = {}
    assignments = TeacherAssignment.objects.filter(row__task=task, teacher__isnull=False).select_related(
        "teacher", "row", "row__subject"
    )
    if only is not None:
        assignments = assignments.filter(teacher_id__in=only)
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
                # Mətn oxuyanın dilində göstərilir (``LText`` — bax `apps/notifications/i18n.py`); `title` sütunu
                # (255) üçün kəsmə crud-dadır, mətnin özü `message`-dədir.
                title=LText(
                    "Dərs yükü təyin edildi: %(head)s — %(hours)d saat", _NOTIFY_CTX, head=head, hours=payload["hours"]
                ),
                message=LText(
                    "%(year)s tədris ili üçün dərs yükünüz təsdiqləndi. Fənn sayı: %(count)d, cəmi %(hours)d saat. "
                    "«Dərs yüküm» bölməsindən baxa bilərsiniz.",
                    _NOTIFY_CTX,
                    year=task.academic_year,
                    count=len(subjects),
                    hours=payload["hours"],
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
def confirm_distribution(
    *, task, actor, allow_vacant: bool = True, request=None, notify: bool = True, loads_before: dict | None = None
) -> dict:
    """Bölgünü təsdiqlə → ``distributed`` + offering sinxronu + bildirişlər.

    ``notify=False`` — heç kimə bildiriş yoxdur. ``loads_before`` (:func:`teacher_loads`, dəyişiklikdən ƏVVƏL) —
    əmr/idxal yolu: əvvəl bölünmüş sənədin yenidən təsdiqində kafedranın bütün müəllimlərinə təkrar «Dərs yükü
    təyin edildi» GETMİR, yalnız bölgüsü yeni yaranan / dəyişən müəllimə bir dəfə gedir (sahib 2026-10-17);
    ilk təsdiq (``distributed_at`` boş) hamıya bildirir. UI yolu defoltla hamıya bildirir."""
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

    if loads_before is not None:
        task.refresh_from_db(fields=["distributed_at"])  # çağıranın nüsxəsi köhnəlmiş ola bilər
    targeted = changed_teacher_ids(task, loads_before) if (loads_before is not None and task.distributed_at) else None

    task.status = TaskStatus.DISTRIBUTED
    task.distributed_by = getattr(actor, "user", None)
    task.distributed_at = timezone.now()
    task.save(update_fields=["status", "distributed_by", "distributed_at", "updated_at"])

    sync = sync_offerings(task, actor=actor, request=request)
    notified = _notify_teachers(task, only=targeted) if notify else 0

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


__all__ = ["changed_teacher_ids", "confirm_distribution", "distribution_readiness", "sync_offerings", "teacher_loads"]
