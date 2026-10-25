"""TƏK səhv imtahan cəhdinin tam silinməsi — sahibin 2026-10-25 tapşırığı.

Sahib: «Şirməmməd üçün olan son imtahan nəticəsini də sil, onunla bağlı olanı, o səhvən olub. Onu əsas götürmə. Sil o
nəticəni». ``trial_exam_purge`` bütöv sınaq imtahanını silir; bu modul isə YALNIZ bir tələbənin bir cəhdini (imtahan və
digər tələbələrin cəhdləri qalır). Yalnız ``purge_exam_attempt`` idarə əmrindən (prod-da ``prod-data-ops.yml``) çağırılır.

Silinən (bir tranzaksiyada): cəhd + cavablar (+ fayllar), reyestr sətirləri (``ExamGradeEvent`` — organizations 0073
dar istisnası: ``emsarena.attempt_purge`` = cəhdin id-si), proktorinq / nəzarət hadisələri, cihaz qeydi, kodlaşdırma
göndərişləri, bu cəhdin apellyasiyaları (+ bəndlər, qərar yazıları, sənədlər), bal düzəlişləri, cavab açarı
kreditləri, cəhdə / apellyasiyalara / jurnal yazısına işarə edən bildirişlər. Bilet (``FinalExamTicket.attempt``)
SET_NULL ilə qalır. Cavab açarı düzəlişinin özü, PIN, şans qeydləri — imtahan səviyyəsindədir, toxunulmur.

Jurnal izləri (``trial_exam_purge``-un yolu ilə):

* **Midterm** — cəhdin avtomatik yazdığı «Midterm» xanası (``ComponentScore.exam_source.attempt_id``) silinir, sonra
  eyni tələbə + fənn üzrə BAŞQA rəsmi midterm cəhdi varsa ``sync_midterm_attempt`` (bildirişsiz) onu yenidən yazır;
* **Final** — ``FinalGrade.exam_score``-un imtahana bağlantısı yoxdur; iz körpünün qaydası ilə yoxlanılır
  (``registrar.exam_result_trace``: cəhd rəsmi idi + jurnaldakı bal cəhdin balına bərabərdir). İz bu cəhdindirsə:
  başqa rəsmi final cəhdi varsa ``sync_attempt_to_journal`` onu yazır, yoxdursa bal boşaldılır.

Rədd halları (``blockers`` — heç nə yazılmır): ``journal_locked`` (midterm xanası bağlanmış jurnalda),
``retake_links`` (25% müraciətinin append-only hadisəsi bu cəhdə işarə edir; ``allow_retake_links`` ilə izlər qalır).
Audit tarixçəsi SAXLANILIR (+ bir yekun audit sətri — həm də ``--latest`` təkrar qaçışının idempotentlik işarəsi).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.db.models import F, Q

from apps.exams.services import trial_exam_purge as trial
from apps.exams.services.trial_exam_purge import PurgeRefused, _model

AUDIT_RESOURCE_TYPE = "exams.exam_attempt_purge"
_SET_FLAG = "SELECT set_config('emsarena.attempt_purge', %s, true)"

#: Mətn sahələri (stdout-da ilk gəlir; dəyərlər ``[0-9A-Za-z_.:-]`` ilə məhdudlaşdırılır).
INFO_KEYS = ("attempt_id", "exam_slug", "exam_type", "category", "status", "started")

#: Sayların sırası (stdout sətri və audit sətri eyni açarlarla).
COUNT_KEYS = (
    "attempt_found",
    "already_purged",
    "is_latest",
    "student_attempts",
    "same_exam_other_attempts",
    "answers",
    "answer_files",
    "grade_events",
    "proctoring_logs",
    "supervision_incidents",
    "attempt_devices",
    "coding_submissions",
    "appeals",
    "appeal_items",
    "appeal_decision_records",
    "appeal_documents",
    "score_adjustments",
    "key_correction_credits",
    "tickets_unlinked",
    "notifications",
    "journal_midterm_from_attempt",
    "journal_midterm_prior_values",
    "journal_midterm_restore",
    "journal_locked",
    "journal_final_from_attempt",
    "journal_final_restore",
    "journal_final_cleared",
    "appeal_ledger_rows_kept",
    "retake_links",
    "audit_rows_kept",
)


@dataclass
class AttemptPurgePlan:
    attempt: object
    info: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    blockers: list = field(default_factory=list)
    appeal_ids: list = field(default_factory=list)
    notification_ids: list = field(default_factory=list)
    file_names: list = field(default_factory=list)
    journal_rows: list = field(default_factory=list)
    component_score_ids: list = field(default_factory=list)
    midterm_sources: list = field(default_factory=list)
    final_expected: object = None
    final_source: object = None
    next_same_exam_start: object = None

    @property
    def exam(self):
        return self.attempt.exam


def _category(exam) -> str:
    value = str(getattr(exam, "exam_type_extended", "") or "").strip()
    return value if value in ("final", "midterm") else "other"


def _attempts(organization, user):
    from apps.exams.models import ExamAttempt

    return ExamAttempt.objects.filter(user=user, exam__organization=organization).select_related(
        "exam", "exam__organization", "user"
    )


def _purged_started_at(organization, user):
    """Əvvəl silinmiş cəhdlərin ən son başlanğıcı (audit sətrindən) — ``--latest``-in idempotentliyi üçün."""
    latest = None
    rows = _model("audit.AuditLog").objects.filter(
        resource_type=AUDIT_RESOURCE_TYPE, organization=organization, changes__student_id=user.pk
    )
    for changes in rows.values_list("changes", flat=True):
        try:
            started = datetime.datetime.fromisoformat(str((changes or {}).get("started_at")))
        except ValueError:
            continue
        latest = started if latest is None or started > latest else latest
    return latest


def find_attempt(*, organization, user, attempt_id=None, latest=False):
    """→ ``(cəhd | None, artıq_silinib: bool)``.

    ``latest`` — tələbənin təşkilatdakı ƏN SON cəhdi (``started_at``, sonra ``pk``). Ən son cəhd artıq bu əmrlə
    silinibsə (audit işarəsi) heç nə qaytarılmır — ikinci qaçış növbəti (qanuni) cəhdi SİLMƏSİN."""
    queryset = _attempts(organization, user)
    if latest:
        attempt = queryset.order_by(F("started_at").desc(nulls_last=True), "-pk").first()
        purged = _purged_started_at(organization, user)
        if purged is not None and (attempt is None or attempt.started_at is None or attempt.started_at <= purged):
            return None, True
        return attempt, False
    attempt = queryset.filter(pk=attempt_id).first()
    if attempt is not None:
        return attempt, False
    gone = _model("audit.AuditLog").objects.filter(
        resource_type=AUDIT_RESOURCE_TYPE, organization=organization, resource_id=str(attempt_id)
    )
    return None, gone.exists()


# ── toplama (yazısız) ────────────────────────────────────────────────────────
def build_plan(attempt, *, allow_retake_links=False) -> AttemptPurgePlan:
    from apps.exams.models import (
        CodingSubmission,
        ExamAnswer,
        ExamAnswerFile,
        ExamGradeEvent,
        FinalAttemptDevice,
        FinalExamTicket,
        ProctoringLog,
        SupervisionIncident,
    )

    plan = AttemptPurgePlan(attempt=attempt)
    exam = attempt.exam
    plan.info = {
        "attempt_id": str(attempt.pk),
        "exam_slug": exam.slug or "-",
        "exam_type": exam.exam_type or "-",
        "category": _category(exam),
        "status": attempt.status or "-",
        "started": attempt.started_at.date().isoformat() if attempt.started_at else "-",
    }
    c = plan.counts
    c["attempt_found"] = 1
    _collect_siblings(plan)
    c["answers"] = ExamAnswer.objects.filter(attempt=attempt).count()
    files = list(ExamAnswerFile.objects.filter(answer__attempt=attempt).exclude(file="").values_list("file", flat=True))
    paints = ExamAnswer.objects.filter(attempt=attempt).exclude(paint_image="").exclude(paint_image__isnull=True)
    files += list(paints.values_list("paint_image", flat=True))
    c["answer_files"] = len(files)
    plan.file_names.extend(files)
    c["grade_events"] = ExamGradeEvent.objects.filter(attempt=attempt).count()
    c["proctoring_logs"] = ProctoringLog.objects.filter(exam_attempt=attempt).count()
    c["supervision_incidents"] = SupervisionIncident.objects.filter(attempt=attempt).count()
    c["attempt_devices"] = FinalAttemptDevice.objects.filter(attempt=attempt).count()
    c["coding_submissions"] = CodingSubmission.objects.filter(attempt=attempt).count()
    c["tickets_unlinked"] = FinalExamTicket.objects.filter(attempt=attempt).count()
    _collect_appeals(plan)
    _collect_midterm(plan)
    _collect_final(plan)
    _collect_retake_links(plan, allow_retake_links=allow_retake_links)
    _collect_notifications(plan)
    c["audit_rows_kept"] = _audit_rows(attempt)
    return plan


def _collect_siblings(plan):
    attempt = plan.attempt
    others = _attempts(attempt.exam.organization, attempt.user).exclude(pk=attempt.pk)
    later = Q(started_at__gt=attempt.started_at) | Q(started_at=attempt.started_at, pk__gt=attempt.pk)
    c = plan.counts
    c["student_attempts"] = others.count() + 1
    c["same_exam_other_attempts"] = others.filter(exam_id=attempt.exam_id).count()
    c["is_latest"] = int(attempt.started_at is None or not others.filter(later).exists())
    plan.next_same_exam_start = (
        others.filter(later, exam_id=attempt.exam_id).order_by("started_at", "pk").values_list("started_at", flat=True)
    ).first()


def _collect_appeals(plan):
    attempt = plan.attempt
    plan.appeal_ids = list(_model("appeals.Appeal").objects.filter(attempt=attempt).values_list("pk", flat=True))
    c = plan.counts
    c["appeals"] = len(plan.appeal_ids)
    c["appeal_items"] = _model("appeals.AppealItem").objects.filter(appeal_id__in=plan.appeal_ids).count()
    records = _model("appeals.AppealDecisionRecord").objects.filter(appeal_id__in=plan.appeal_ids)
    c["appeal_decision_records"] = records.count()
    documents = list(records.exclude(document="").values_list("document", flat=True))
    c["appeal_documents"] = len(documents)
    plan.file_names.extend(documents)
    c["score_adjustments"] = _model("appeals.ScoreAdjustment").objects.filter(attempt=attempt).count()
    c["key_correction_credits"] = _model("appeals.KeyCorrectionCredit").objects.filter(attempt=attempt).count()
    # Jurnalın apellyasiya ledger-i (``ExamScoreEntry``) dəyişməzdir — qalır, yalnız sayılır.
    notes = [f"Rəqəmsal apellyasiya #{pk}" for pk in plan.appeal_ids]
    entries = _model("registrar.ExamScoreEntry").objects.filter(kind="appeal", note__in=notes) if notes else None
    c["appeal_ledger_rows_kept"] = entries.count() if entries is not None else 0


def _collect_midterm(plan):
    """Cəhdin avtomatik yazdığı «Midterm» xanaları (``trial_exam_purge._collect_journal``-un tək cəhd variantı)."""
    from apps.exams.models import ExamAttempt
    from apps.exams.services.midterm_journal_sync import official_attempts

    attempt = plan.attempt
    rows = list(
        _model("registrar.ComponentScore")
        .objects.filter(exam_source__attempt_id=attempt.pk)
        .values(
            "pk",
            "component_id",
            "component__name",
            "component__offering_id",
            "component__offering__subject_id",
            "enrollment__student_id",
        )
    )
    plan.journal_rows = rows
    plan.component_score_ids = [row["pk"] for row in rows]
    c = plan.counts
    c["journal_midterm_from_attempt"] = len(rows)
    offering_ids = {row["component__offering_id"] for row in rows}
    c["journal_midterm_prior_values"] = trial._prior_values(
        attempt.exam, [{"pk": attempt.pk, "user_id": attempt.user_id}], offering_ids
    )
    locked = _model("registrar.AssessmentScheme").objects.filter(offering_id__in=offering_ids)
    locked = set(
        locked.filter(Q(is_published=True) | Q(approval_status="approved")).values_list("offering_id", flat=True)
    )
    c["journal_locked"] = sum(1 for row in rows if row["component__offering_id"] in locked)
    if c["journal_locked"]:
        plan.blockers.append("journal_locked")
    sources = []
    for user_id, subject_id in {(r["enrollment__student_id"], r["component__offering__subject_id"]) for r in rows}:
        queryset = ExamAttempt.objects.filter(user_id=user_id, exam__subject_id=subject_id).exclude(pk=attempt.pk)
        sources.extend(official_attempts(queryset))
    plan.midterm_sources = sources
    c["journal_midterm_restore"] = len(sources)


def _official_final_percent(attempt):
    """Cəhd jurnalın yekun balının RƏSMİ mənbəyidirsə ``(faiz, qovulub)``, yoxsa ``None`` (körpünün qaydaları)."""
    from apps.exams.services import journal_sync

    exam = attempt.exam
    if not exam.subject_id or journal_sync.final_grade_skip_reason(exam) is not None:
        return None
    if attempt.is_trial or not attempt.is_finished:
        return None
    if journal_sync._superseded_by_later_final_attempt(attempt, exam.subject_id):
        return None  # jurnaldakı bal sonrakı cəhdindir
    expelled = getattr(attempt, "supervision_status", "") == "removed"
    percent = 0 if expelled else journal_sync._attempt_percent(attempt)
    if percent is None or percent is journal_sync.PERCENT_PENDING:
        return None
    return percent, expelled


def _final_source(attempt):
    """Eyni tələbə + fənn üzrə ən son BAŞQA rəsmi (bitmiş, sınaq olmayan, silinməmiş) final cəhdi."""
    from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
    from apps.exams.models import ExamAttempt
    from apps.exams.services.access_policy import FINAL_EXAM_CATEGORY

    return (
        ExamAttempt.objects.filter(
            user_id=attempt.user_id,
            exam__subject_id=attempt.exam.subject_id,
            exam__exam_type_extended=FINAL_EXAM_CATEGORY,
            exam__is_deleted=False,
            is_trial=False,
            status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .exclude(pk=attempt.pk)
        .select_related("exam", "exam__organization", "user")
        .order_by(F("started_at").desc(nulls_last=True), "-pk")
        .first()
    )


def _collect_final(plan):
    from apps.registrar.public import exam_result_trace

    attempt = plan.attempt
    official = _official_final_percent(attempt)
    if official is None:
        return
    percent, expelled = official
    exam = attempt.exam
    trace = exam_result_trace.final_exam_trace(
        student=attempt.user,
        subject_id=exam.subject_id,
        organization=exam.organization,
        score_percent=percent,
        is_expelled=expelled,
        attempt=attempt,
    )
    if not trace["matches"]:
        return  # jurnaldakı bal bu cəhdin deyil (əl ilə daxiletmə / 25% / qeydiyyat yoxdur) — toxunulmur
    plan.final_expected = trace["expected"]
    plan.final_source = _final_source(attempt)
    plan.counts["journal_final_from_attempt"] = 1
    plan.counts["journal_final_restore"] = int(plan.final_source is not None)
    plan.counts["journal_final_cleared"] = int(plan.final_source is None)


def _collect_retake_links(plan, *, allow_retake_links):
    attempt = plan.attempt
    events = _model("registrar.RetakeApplicationEvent").objects.filter(
        organization_id=attempt.exam.organization_id,
    )
    links = events.filter(Q(metadata__attempt_id=attempt.pk) | Q(metadata__attempt_id=str(attempt.pk))).count()
    plan.counts["retake_links"] = links
    if links and not allow_retake_links:
        plan.blockers.append("retake_links")


def _collect_notifications(plan):
    attempt = plan.attempt
    model = _model("notifications.InAppNotification")
    match = Q(metadata__attempt_id=attempt.pk) | Q(metadata__attempt_id=str(attempt.pk))
    if plan.appeal_ids:
        match |= Q(metadata__appeal_id__in=plan.appeal_ids)
    found = set(model.objects.filter(match).values_list("pk", flat=True))
    # «Yeni imtahan cəhdi» (müəllimə) / «Nəticə yoxlanıldı» (tələbəyə) — imtahan + tələbə, bu cəhdin pəncərəsində.
    task = model.objects.filter(
        metadata__task_kind="exam", metadata__task_id=attempt.exam_id, metadata__student_id=attempt.user_id
    )
    if attempt.started_at is not None:
        task = task.filter(created_at__gte=attempt.started_at)
    if plan.next_same_exam_start is not None:
        task = task.filter(created_at__lt=plan.next_same_exam_start)
    found |= set(task.values_list("pk", flat=True))
    found |= trial._journal_notifications(model, plan, since=attempt.started_at)
    plan.notification_ids = sorted(found)
    plan.counts["notifications"] = len(found)


def _audit_rows(attempt) -> int:
    from django.contrib.contenttypes.models import ContentType

    from apps.exams.models import ExamAttempt

    content_type = ContentType.objects.get_for_model(ExamAttempt)
    return _model("audit.AuditLog").objects.filter(content_type=content_type, object_id=str(attempt.pk)).count()


# ── tətbiq ───────────────────────────────────────────────────────────────────
def apply_purge(attempt, *, reason: str, allow_retake_links=False) -> AttemptPurgePlan | None:
    """Bir tranzaksiyada sil (cəhd sətri kilid kökü). Rədd → ``PurgeRefused``; cəhd artıq yoxdursa ``None``."""
    from apps.exams.models import (
        CodingSubmission,
        ExamAttempt,
        FinalAttemptDevice,
        ProctoringLog,
        SupervisionIncident,
    )

    with transaction.atomic():
        locked = (
            ExamAttempt.objects.select_for_update(of=("self",))
            .select_related("exam", "exam__organization", "user")
            .filter(pk=attempt.pk)
            .first()
        )
        if locked is None:
            return None  # idempotent: paralel / əvvəlki qaçış artıq silib
        plan = build_plan(locked, allow_retake_links=allow_retake_links)
        if plan.blockers:
            raise PurgeRefused(plan)
        if plan.counts.get("grade_events"):
            # organizations 0073: append-only qoruyucusu YALNIZ bayraqdakı cəhdin sətirlərinə icazə verir.
            with connection.cursor() as cursor:
                cursor.execute(_SET_FLAG, [str(locked.pk)])
                cursor.execute("DELETE FROM exams_examgradeevent WHERE attempt_id = %s", [locked.pk])
                cursor.execute(_SET_FLAG, [""])
        _model("notifications.InAppNotification").objects.filter(pk__in=plan.notification_ids).delete()
        _model("registrar.ComponentScore").objects.filter(pk__in=plan.component_score_ids).delete()
        _model("appeals.KeyCorrectionCredit").objects.filter(attempt=locked).delete()
        _model("appeals.ScoreAdjustment").objects.filter(attempt=locked).delete()
        _model("appeals.Appeal").objects.filter(pk__in=plan.appeal_ids).delete()
        SupervisionIncident.objects.filter(attempt=locked).delete()
        ProctoringLog.objects.filter(exam_attempt=locked).delete()
        FinalAttemptDevice.objects.filter(attempt=locked).delete()
        CodingSubmission.objects.filter(attempt=locked).delete()
        exam = locked.exam
        locked.delete()  # cavablar, fayl sətirləri — CASCADE; bilet — SET_NULL
        _restore_journal(locked, plan)
        _audit(exam, locked, plan, reason)
        transaction.on_commit(lambda: trial._after_commit(exam.pk, plan.file_names))
    return plan


def _restore_journal(attempt, plan):
    """Silinmədən SONRA: midterm xanasına / yekun bala başqa rəsmi cəhdi yaz, yoxdursa yekun balı boşalt."""
    from apps.exams.services.journal_sync import sync_attempt_to_journal
    from apps.exams.services.midterm_journal_sync import sync_midterm_attempt
    from apps.registrar.public import exam_result_trace

    written = 0
    for source in plan.midterm_sources:
        status, _row = sync_midterm_attempt(source, notify=False)
        written += int(status == "written")
    plan.counts["journal_midterm_restore"] = written
    if plan.final_expected is None:
        return
    restored = sync_attempt_to_journal(plan.final_source) if plan.final_source is not None else None
    is_final_grade = getattr(getattr(restored, "_meta", None), "model_name", "") == "finalgrade"
    plan.counts["journal_final_restore"] = int(is_final_grade)
    cleared = False
    if not is_final_grade:
        exam = attempt.exam
        cleared = exam_result_trace.clear_exam_result(
            student=attempt.user,
            subject_id=exam.subject_id,
            organization=exam.organization,
            expected_score=plan.final_expected,
        )
    plan.counts["journal_final_cleared"] = int(cleared)


def _audit(exam, attempt, plan, reason):
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.DELETE,
        user=None,
        organization=exam.organization,
        obj=exam,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(plan.info["attempt_id"]),
        resource_repr=f"{exam.slug}#{plan.info['attempt_id']}",
        old_values={"attempt_id": int(plan.info["attempt_id"]), "exam_slug": exam.slug, "status": attempt.status},
        changes={
            "verb": "purge_exam_attempt",
            "student_id": attempt.user_id,
            "exam_id": exam.pk,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "counts": {key: plan.counts.get(key, 0) for key in COUNT_KEYS},
        },
        reason=reason,
    )


__all__ = [
    "AUDIT_RESOURCE_TYPE",
    "COUNT_KEYS",
    "INFO_KEYS",
    "AttemptPurgePlan",
    "PurgeRefused",
    "apply_purge",
    "build_plan",
    "find_attempt",
]
