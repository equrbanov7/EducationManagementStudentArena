"""Heç bir fəndə iştirakı / balı olmayan tələbələri dondurmaq (sahib 2026-11-08).

Sahib: «hansısa tələbənin heç bir fəndən i/e, balı yoxdursa demək oxumur, midterm belə yoxdursa demək ki yoxdur, onu
jurnalda göstərməyək» + «dondurmaq lazımdır».

AKTİVLİK (tələbə üzrə, açıq dövrlərin — cari və əvvəlcədən açılmış — BÜTÜN yazılışları, statusundan asılı olmayaraq;
qrup köçürməsində qeydlər köhnə yazılışda qalır):

* jurnal xanası: «i/e» (iştirak), üzrlü qayıb və ya bal;
* komponent balı (midterm və s.) > 0.

Yalnız «q/b» yazılmış tələbə aktiv SAYILMIR (sahibin qaydası).

QORUYUCULAR (bunlar dondurulmur, sayı çıxır):

* ``skipped_recent`` — hesab son :data:`RECENT_DAYS` gündə yaradılıb (yeni gələn);
* ``skipped_no_evidence`` — tələbənin heç bir jurnalında başqa tələbəyə də qeyd yazılmayıb (müəllim jurnalı hələ
  yazmır — bu tələbənin yox, jurnalın problemidir);
* ``skipped_staff`` — superadmin / heyət hesabı.

TƏTBİQ: tələbənin açıq dövrlərdəki ``enrolled`` yazılışları ``suspended`` olur (jurnaldan, imtahan siyahısından çıxır;
xanalar SİLİNMİR — :mod:`apps.registrar.enrollment_suspension` ilə eyni status) və hesab bloklanır (RİM «Blokla» ilə
eyni). Hər tələbə üçün bir audit sətri. ``--undo`` yalnız bu əmrin dondurduğunu (hələ ``suspended`` olan yazılışları və
bu əmrin blokladığı hesabı) geri qaytarır.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .account_deletion import block_account, unblock_account

REASON = "Sahib 2026-11-08: heç bir fəndə i/e, bal və midterm yoxdur — tələbə dondurulur (jurnalda göstərilmir)"
UNDO_REASON = "Sahib 2026-11-08: aktivliyi olmayan tələbənin dondurulmasının geri qaytarılması"
RESOURCE = "accounts.inactive_student_freeze"
RECENT_DAYS = 14


def _model(name):
    return django_apps.get_model("registrar", name)


def _open_q(prefix: str = "") -> Q:
    """Cari və ya gələcək (aktiv) dövr — :func:`apps.registrar.journal_hygiene.open_period_q` ilə eyni."""
    today = timezone.localdate()
    return Q(**{f"{prefix}offering__period__is_active": True}) & (
        Q(**{f"{prefix}offering__period__is_current": True}) | Q(**{f"{prefix}offering__period__start_date__gt": today})
    )


def _mark_activity_q() -> Q:
    return Q(status__in=("present", "excused")) | Q(score__isnull=False)


def candidates(organization, skipped=None):
    """``(tələbə id → [enrolled yazılış id-ləri], saylar)`` — dondurulacaq tələbələr (yazmır).

    ``skipped`` (siyahı) verilərsə ``skipped_no_evidence`` tələbələrinin id-ləri ona əlavə olunur.
    """
    Enrollment = _model("Enrollment")
    LessonMark = _model("LessonMark")
    ComponentScore = _model("ComponentScore")
    enrolled = (
        Enrollment.objects.filter(organization=organization, status=Enrollment.Status.ENROLLED)
        .filter(_open_q())
        .exclude(offering__assessment_scheme__is_published=True)
        .values_list("pk", "student_id", "offering_id")
    )
    by_student: dict = {}
    offerings_of: dict = {}
    for pk, student_id, offering_id in enrolled:
        by_student.setdefault(student_id, []).append(pk)
        offerings_of.setdefault(student_id, set()).add(offering_id)
    marks = LessonMark.objects.filter(organization=organization).filter(_open_q("lesson__"))
    active = set(marks.filter(_mark_activity_q()).values_list("enrollment__student_id", flat=True).distinct())
    active |= set(
        ComponentScore.objects.filter(organization=organization, score__gt=0)
        .filter(_open_q("enrollment__"))
        .values_list("enrollment__student_id", flat=True)
        .distinct()
    )
    written = set(marks.values_list("lesson__offering_id", flat=True).distinct())
    counts = {"students_active": 0, "skipped_no_evidence": 0, "skipped_recent": 0, "skipped_staff": 0}
    idle = {student_id: ids for student_id, ids in by_student.items() if student_id not in active}
    counts["students_active"] = len(by_student) - len(idle)
    recent_cutoff = timezone.now() - timedelta(days=RECENT_DAYS)
    users = get_user_model().objects.in_bulk(list(idle))
    result = {}
    for student_id, ids in idle.items():
        user = users.get(student_id)
        if user is None or user.is_superuser or user.is_staff:
            counts["skipped_staff"] += 1
        elif user.date_joined and user.date_joined >= recent_cutoff:
            counts["skipped_recent"] += 1
        elif not offerings_of[student_id] & written:
            counts["skipped_no_evidence"] += 1
            if skipped is not None:
                skipped.append(student_id)
        else:
            result[student_id] = sorted(ids)
    return result, counts


def skipped_report(organization) -> list:
    """``[(tələbə id, qrup id | None)]`` — jurnalına heç kimə yazılmamış (``skipped_no_evidence``) tələbələr."""
    skipped: list = []
    candidates(organization, skipped=skipped)
    Record = _model("StudentAcademicRecord")
    groups = dict(
        Record.objects.filter(organization=organization, student_id__in=skipped, status="enrolled")
        .order_by("student_id", "created_at")
        .values_list("student_id", "group_id")
    )
    return [(student_id, groups.get(student_id)) for student_id in sorted(skipped)]


def run(*, organization, actor, counts, undo=False, report=None) -> None:
    if undo:
        _undo(organization=organization, actor=actor, counts=counts)
        return
    Enrollment = _model("Enrollment")
    targets, guard_counts = candidates(organization)
    counts.update(guard_counts)
    users = get_user_model().objects.in_bulk(list(targets))
    for student_id in sorted(targets):
        user = users[student_id]
        ids = list(
            Enrollment.objects.select_for_update()
            .filter(pk__in=targets[student_id], status=Enrollment.Status.ENROLLED)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        Enrollment.objects.filter(pk__in=ids).update(status=Enrollment.Status.SUSPENDED, updated_at=timezone.now())
        blocked = user.is_active
        if blocked:
            block_account(user, actor=actor, reason=REASON)
        counts["students_frozen"] += 1
        counts["enrollments_suspended"] += len(ids)
        counts["accounts_blocked" if blocked else "accounts_already_blocked"] += 1
        if report is not None:
            report.append(student_id)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=user,
            old_values={"status": "enrolled", "is_active": blocked},
            new_values={"status": "suspended", "is_active": False},
            changes={"enrollment_ids": [str(pk) for pk in ids], "blocked": blocked},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(user.pk),
        )


def _undo(*, organization, actor, counts) -> None:
    Enrollment = _model("Enrollment")
    AuditLog = django_apps.get_model("audit", "AuditLog")
    rows = AuditLog.objects.filter(
        organization=organization, resource_type=RESOURCE, changes__has_key="blocked"
    ).order_by("created_at")
    users = get_user_model().objects.in_bulk([int(row.resource_id) for row in rows])
    for row in rows:
        changes = row.changes or {}
        restored = Enrollment.objects.filter(
            pk__in=changes.get("enrollment_ids") or [], status=Enrollment.Status.SUSPENDED
        ).update(status=Enrollment.Status.ENROLLED, updated_at=timezone.now())
        counts["undo_enrollments_restored"] += restored
        user = users.get(int(row.resource_id))
        if changes.get("blocked") and user is not None and not user.is_active:
            unblock_account(user, actor=actor, reason=UNDO_REASON)
            counts["undo_accounts_unblocked"] += 1
        counts["undo_students"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=user,
            old_values={"status": "suspended"},
            new_values={"status": "enrolled"},
            changes={"enrollment_ids": changes.get("enrollment_ids") or []},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=row.resource_id,
        )
