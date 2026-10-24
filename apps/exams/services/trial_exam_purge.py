"""Sınaq (real olmayan) imtahanın tam silinməsi — sahibin 2026-10-21 tapşırığı.

Sahib: «233IT ing üçün Cloud-dan sınaq midterm etdik, real deyildi — onu silmək lazımdır. Hamıdan, nəticədə,
examdə silinsin gərək». Adi «Zibil qutusu» axını (``retention.py``) akademik cəhd tarixçəsini QƏSDƏN qoruyur;
bu modul yalnız sahibin açıq tapşırığı ilə, ``purge_trial_exam`` idarə əmrindən (prod-da yalnız
``prod-data-ops.yml``) çağırılır.

Silinən (bir tranzaksiyada): cəhdlər + cavablar (+ fayllar), proktorinq/nəzarət hadisələri (zal pozuntuları),
zal cihaz qeydləri, kodlaşdırma göndərişləri, apellyasiyalar (+ bəndlər, qərar yazıları, sənədlər, bal
düzəlişləri), cavab açarı düzəlişləri (+ kreditlər), final/midterm biletləri, PIN-lər, əlavə cəhd hüquqları,
canlı sessiyalar, imtahandan AVTOMATİK yazılmış jurnal «Midterm» xanaları (``ComponentScore.exam_source``) və
imtahana / cəhdlərə / apellyasiyalara işarə edən bildirişlər. İmtahanın özü layihənin yumşaq silməsi ilə
(``is_deleted`` — bütün siyahılardan çıxır) bağlanır. Audit tarixçəsi SAXLANILIR (+ bir yekun audit sətri).

Rədd halları (``blockers`` — ``apply`` heç nə yazmır):

* ``final_exam`` — final kateqoriyası ``FinalGrade`` / ``ResitRecord`` / ``ExamScoreEntry`` yazır, onların
  imtahana bağlantısı yoxdur → təhlükəsiz geri alınmır;
* ``grade_events`` — ``ExamGradeEvent`` DB səviyyəsində append-only-dir; 2026-10-21-dən dar istisna var (organizations
  0071): imtahan əvvəl ``is_deleted`` işarələnir, sonra ``SET LOCAL emsarena.trial_exam_purge = 'on'`` ilə silinir;
* ``retake_links`` — 25% müraciətinə bağlı izlər (append-only) imtahana bağlıdır
  (``allow_retake_links`` ilə: izlər qalır, qalan hər şey silinir);

2026-10-24 (sahib, «JS Loop»): müraciətə BAĞLI OLMAYAN «İmtahan şansı» qeydləri (``ExamChanceGrant``,
``application`` boş) sınaq imtahanının bir hissəsidir — onlar da silinir (registrar 0097: append-only
qoruyucusuna dar istisna, ``chance_grants_deleted``) və artıq rədd səbəbi deyil.
* ``journal_locked`` — avtomatik xana bağlanmış (dərc olunmuş) jurnaldadır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

AUDIT_RESOURCE_TYPE = "exams.trial_exam_purge"
_MIDTERM_AUTO_AUDIT = "registrar.grade.midterm-auto"
#: Metadata-sız imtahan bildirişlərinin ümumi keçidləri (``org_scoped_link`` onları ``?next=%2F…`` kimi kodlayır).
_GENERIC_EXAM_LINKS = (
    "assigned-exams",
    "/exams/final/",
    "/exams/midterm/",
    "%2Fexams%2Ffinal%2F",
    "%2Fexams%2Fmidterm%2F",
)
_EMPTY_SCORE = "—"

#: Sayların sırası (stdout sətri və audit sətri eyni açarlarla).
COUNT_KEYS = (
    "exam_found",
    "exam_deleted_before",
    "attempts",
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
    "key_corrections",
    "key_correction_credits",
    "tickets",
    "sessions_kept",
    "pins",
    "attempt_grants",
    "live_sessions",
    "journal_component_scores_from_exam",
    "journal_prior_values",
    "journal_restored_from_other_exam",
    "journal_locked",
    "final_grades_from_exam",
    "chance_grants",
    "chance_grants_deleted",
    "retake_links",
    "notifications",
    "audit_rows_kept",
)


#: Yalnız məlumat / rədd üçün (bu modul onları SİLMİR) — ``has_data`` bunları saymır.
_INFO_KEYS = frozenset(
    {
        "exam_found",
        "exam_deleted_before",
        "audit_rows_kept",
        "sessions_kept",
        "journal_prior_values",
        "journal_restored_from_other_exam",
        "journal_locked",
        "final_grades_from_exam",
        "chance_grants",
        "retake_links",
    }
)


def _model(label):
    return django_apps.get_model(*label.split("."))


@dataclass
class PurgePlan:
    exam: object
    counts: dict = field(default_factory=dict)
    blockers: list = field(default_factory=list)
    attempt_ids: list = field(default_factory=list)
    appeal_ids: list = field(default_factory=list)
    component_score_ids: list = field(default_factory=list)
    notification_ids: list = field(default_factory=list)
    file_names: list = field(default_factory=list)
    chance_grant_ids: list = field(default_factory=list)
    affected_user_ids: set = field(default_factory=set)
    journal_rows: list = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return any(self.counts.get(key) for key in COUNT_KEYS if key not in _INFO_KEYS)


def find_exam(*, organization, slug: str):
    """Soft-deleted daxil — ikinci qaçış eyni imtahanı tapır (idempotentlik)."""
    from apps.exams.models import Exam

    return Exam.objects.select_related("organization").filter(organization=organization, slug=slug).first()


# ── toplama (yazısız) ────────────────────────────────────────────────────────
def build_plan(exam, *, allow_retake_links=False) -> PurgePlan:
    from apps.exams.models import (
        CodingSubmission,
        ExamAnswer,
        ExamAnswerFile,
        ExamAttempt,
        ExamGradeEvent,
        ExamStudentPin,
        FinalAttemptDevice,
        FinalExamTicket,
        ProctoringLog,
        StudentExamAttemptGrant,
        SupervisionIncident,
    )

    plan = PurgePlan(exam=exam)
    c = plan.counts
    c["exam_found"] = 1
    c["exam_deleted_before"] = int(bool(exam.is_deleted))
    attempts = list(ExamAttempt.objects.filter(exam=exam).values("pk", "user_id", "started_at"))
    plan.attempt_ids = [row["pk"] for row in attempts]
    ids = plan.attempt_ids
    plan.affected_user_ids = {row["user_id"] for row in attempts}
    c["attempts"] = len(ids)
    c["answers"] = ExamAnswer.objects.filter(attempt_id__in=ids).count()
    files = list(
        ExamAnswerFile.objects.filter(answer__attempt_id__in=ids).exclude(file="").values_list("file", flat=True)
    )
    paints = ExamAnswer.objects.filter(attempt_id__in=ids).exclude(paint_image="").exclude(paint_image__isnull=True)
    files += list(paints.values_list("paint_image", flat=True))
    c["answer_files"] = len(files)
    plan.file_names.extend(files)
    c["grade_events"] = ExamGradeEvent.objects.filter(attempt_id__in=ids).count()
    c["proctoring_logs"] = ProctoringLog.objects.filter(exam_attempt_id__in=ids).count()
    c["supervision_incidents"] = SupervisionIncident.objects.filter(Q(exam=exam) | Q(attempt_id__in=ids)).count()
    c["attempt_devices"] = FinalAttemptDevice.objects.filter(attempt_id__in=ids).count()
    c["coding_submissions"] = CodingSubmission.objects.filter(Q(exam=exam) | Q(attempt_id__in=ids)).count()
    _collect_appeals(plan, ids)
    tickets = FinalExamTicket.objects.filter(exam=exam)
    c["tickets"] = tickets.count()
    # Zal oturumu imtahandan ASILI DEYİL (bir oturumda bir neçə imtahan) — oturum saxlanılır, yalnız bilet silinir.
    c["sessions_kept"] = tickets.exclude(session__isnull=True).values("session_id").distinct().count()
    pins = ExamStudentPin.objects.filter(exam=exam)
    grants = StudentExamAttemptGrant.objects.filter(exam=exam)
    c["pins"] = pins.count()
    c["attempt_grants"] = grants.count()
    plan.affected_user_ids |= set(tickets.values_list("student_id", flat=True))
    plan.affected_user_ids |= set(pins.values_list("student_id", flat=True))
    plan.affected_user_ids |= set(grants.values_list("student_id", flat=True))
    c["live_sessions"] = _model("live_exam.LiveSession").objects.filter(exam=exam).count()
    _collect_journal(plan, attempts)
    _collect_registrar_links(plan, ids, allow_retake_links=allow_retake_links)
    _collect_notifications(plan)
    c["audit_rows_kept"] = _audit_rows(exam, ids)
    return plan


def _collect_appeals(plan, attempt_ids):
    Appeal = _model("appeals.Appeal")
    exam = plan.exam
    appeals = Appeal.objects.filter(Q(exam=exam) | Q(attempt_id__in=attempt_ids))
    plan.appeal_ids = list(appeals.values_list("pk", flat=True))
    c = plan.counts
    c["appeals"] = len(plan.appeal_ids)
    c["appeal_items"] = _model("appeals.AppealItem").objects.filter(appeal_id__in=plan.appeal_ids).count()
    records = _model("appeals.AppealDecisionRecord").objects.filter(appeal_id__in=plan.appeal_ids)
    c["appeal_decision_records"] = records.count()
    documents = list(records.exclude(document="").values_list("document", flat=True))
    c["appeal_documents"] = len(documents)
    plan.file_names.extend(documents)
    c["score_adjustments"] = _model("appeals.ScoreAdjustment").objects.filter(attempt_id__in=attempt_ids).count()
    c["key_corrections"] = _model("appeals.AnswerKeyCorrection").objects.filter(exam=exam).count()
    c["key_correction_credits"] = (
        _model("appeals.KeyCorrectionCredit")
        .objects.filter(Q(attempt_id__in=attempt_ids) | Q(correction__exam=exam))
        .count()
    )
    plan.affected_user_ids |= set(appeals.values_list("student_id", flat=True))


def _journal_scores(exam, attempt_ids):
    ComponentScore = _model("registrar.ComponentScore")
    match = Q(exam_source__exam_id=exam.pk)
    if attempt_ids:
        match |= Q(exam_source__attempt_id__in=list(attempt_ids))
    return ComponentScore.objects.filter(exam_source__isnull=False).filter(match)


def _collect_journal(plan, attempts):
    from apps.exams.services.journal_sync import final_grade_skip_reason

    exam = plan.exam
    rows = list(
        _journal_scores(exam, plan.attempt_ids).values(
            "pk",
            "component_id",
            "component__name",
            "component__offering_id",
            "component__offering__subject_id",
            "enrollment__student_id",
        )
    )
    plan.component_score_ids = [row["pk"] for row in rows]
    c = plan.counts
    c["journal_component_scores_from_exam"] = len(rows)
    offering_ids = {row["component__offering_id"] for row in rows}
    c["journal_prior_values"] = _prior_values(exam, attempts, offering_ids)
    c["journal_restored_from_other_exam"] = len(_other_official_attempts(exam, rows))
    Scheme = _model("registrar.AssessmentScheme")
    locked = Scheme.objects.filter(offering_id__in=offering_ids).filter(
        Q(is_published=True) | Q(approval_status="approved")
    )
    locked_offerings = set(locked.values_list("offering_id", flat=True))
    c["journal_locked"] = sum(1 for row in rows if row["component__offering_id"] in locked_offerings)
    if c["journal_locked"]:
        plan.blockers.append("journal_locked")
    # Final kateqoriyası FinalGrade-ə imtahan bağlantısı OLMADAN yazır — burada geri alınmır.
    is_final = final_grade_skip_reason(exam) is None and bool(exam.subject_id)
    c["final_grades_from_exam"] = int(is_final)
    if is_final:
        plan.blockers.append("final_exam")
    plan.journal_rows = rows


def _other_official_attempts(exam, rows) -> list:
    """Boşaldılacaq xananın sahibinin BAŞQA (silinməyən) imtahandan rəsmi test midterm cəhdi varsa — həmin cəhd.

    Sınaq imtahanı onu «sonrakı cəhd» kimi əvəzləmişdi (``superseded``); silinmədən sonra jurnal onun balını
    yenidən alır (``midterm_journal_sync`` — eyni qayda, eyni audit)."""
    from apps.exams.models import ExamAttempt
    from apps.exams.services.midterm_journal_sync import official_attempts

    found = []
    for user_id, subject_id in {(r["enrollment__student_id"], r["component__offering__subject_id"]) for r in rows}:
        queryset = ExamAttempt.objects.filter(user_id=user_id, exam__subject_id=subject_id).exclude(exam=exam)
        found.extend(official_attempts(queryset))
    return found


def _prior_values(exam, attempts, offering_ids) -> int:
    """Avtomatik yazıdan ƏVVƏL xanada bal olubmu (audit izinin ilk sətrinin «old»-u) — xana yenə də boşaldılır."""
    if not attempts or not offering_ids:
        return 0
    user_by_source = {f"exam_attempt:{row['pk']}": row["user_id"] for row in attempts}
    AuditLog = _model("audit.AuditLog")
    first: dict = {}
    rows = AuditLog.objects.filter(
        resource_type=_MIDTERM_AUTO_AUDIT, resource_id__in=[str(pk) for pk in offering_ids]
    ).order_by("created_at", "pk")
    for audit in rows.only("resource_id", "changes", "created_at"):
        for change in audit.changes if isinstance(audit.changes, list) else []:
            user_id = user_by_source.get(str((change or {}).get("source", "")))
            if user_id is not None:
                first.setdefault((audit.resource_id, user_id), change.get("old"))
    return sum(1 for old in first.values() if old not in (None, "", _EMPTY_SCORE))


def _collect_registrar_links(plan, attempt_ids, *, allow_retake_links):
    exam = plan.exam
    grants = _model("registrar.ExamChanceGrant").objects.filter(organization_id=exam.organization_id, exam_id=exam.pk)
    plan.counts["chance_grants"] = grants.count()
    # Müraciətə bağlı olmayan şans qeydləri sınaq imtahanı ilə birlikdə silinir (registrar 0097).
    loose = grants.filter(application__isnull=True)
    plan.chance_grant_ids = [str(pk) for pk in loose.values_list("pk", flat=True)]
    plan.counts["chance_grants_deleted"] = len(plan.chance_grant_ids)
    plan.file_names.extend(name for name in loose.exclude(document="").values_list("document", flat=True) if name)
    plan.affected_user_ids |= set(loose.values_list("student_id", flat=True))
    events = _model("registrar.RetakeApplicationEvent").objects.filter(organization_id=exam.organization_id)
    event_match = Q(metadata__exam_id=exam.pk)
    if attempt_ids:
        event_match |= Q(metadata__attempt_id__in=list(attempt_ids))
    links = grants.exclude(application__isnull=True).count() + events.filter(event_match).count()
    plan.counts["retake_links"] = links
    if links and not allow_retake_links:
        plan.blockers.append("retake_links")


def _collect_notifications(plan):
    InAppNotification = _model("notifications.InAppNotification")
    exam = plan.exam
    ids = plan.attempt_ids
    match = (
        Q(metadata__exam_id=exam.pk)
        | Q(metadata__exam_id=str(exam.pk))
        | Q(metadata__task_kind="exam", metadata__task_id=exam.pk)
        | Q(link__contains=exam.slug)
    )
    if ids:
        match |= Q(metadata__attempt_id__in=ids)
    if plan.appeal_ids:
        match |= Q(metadata__appeal_id__in=plan.appeal_ids)
    found = set(InAppNotification.objects.filter(match).values_list("pk", flat=True))
    found |= _title_notifications(InAppNotification, plan)
    found |= _journal_notifications(InAppNotification, plan)
    plan.notification_ids = sorted(found)
    plan.counts["notifications"] = len(found)


def _title_notifications(model, plan) -> set:
    """PIN/təyinat/xatırlatma bildirişləri metadata-sız gedir (ümumi keçid + mətndə imtahanın adı).

    Eyni adlı BAŞQA imtahan varsa bu uyğunlaşdırma edilmir (yanlış bildirişi silməmək üçün)."""
    from apps.exams.models import Exam

    exam = plan.exam
    title = str(exam.title or "").strip()
    if not title or not plan.affected_user_ids:
        return set()
    if Exam.objects.filter(organization_id=exam.organization_id, title=title).exclude(pk=exam.pk).exists():
        return set()
    link_match = Q()
    for fragment in _GENERIC_EXAM_LINKS:
        link_match |= Q(link__contains=fragment)
    rows = model.objects.filter(
        link_match,
        organization_id=exam.organization_id,
        recipient_id__in=plan.affected_user_ids,
        notification_type="exam",
        created_at__gte=exam.created_at,
        message__contains=title,
    )
    return set(rows.values_list("pk", flat=True))


def _journal_notifications(model, plan) -> set:
    """Avtomatik midterm yazısının «Midterm balı yazıldı: N» bildirişi (yalnız həmin sətirdən ibarət olanlar)."""
    rows = plan.journal_rows
    if not rows:
        return set()
    exam = plan.exam
    names_by_key: dict = {}
    for row in rows:
        names_by_key.setdefault((str(row["component__offering_id"]), row["enrollment__student_id"]), set()).add(
            row["component__name"]
        )
    candidates = model.objects.filter(
        metadata__event="journal_update",
        metadata__offering_id__in=sorted({key[0] for key in names_by_key}),
        recipient_id__in={key[1] for key in names_by_key},
        created_at__gte=exam.created_at,
    ).only("pk", "metadata", "recipient_id", "message")
    found = set()
    for note in candidates:
        names = names_by_key.get((str((note.metadata or {}).get("offering_id")), note.recipient_id))
        lines = [line for line in str(note.message or "").splitlines() if line.strip()]
        if names and lines and all(any(line.startswith(f"{name} ") for name in names) for line in lines):
            found.add(note.pk)
    return found


def _audit_rows(exam, attempt_ids) -> int:
    from django.contrib.contenttypes.models import ContentType

    from apps.exams.models import Exam, ExamAttempt

    AuditLog = _model("audit.AuditLog")
    match = Q(content_type=ContentType.objects.get_for_model(Exam), object_id=str(exam.pk))
    if attempt_ids:
        match |= Q(
            content_type=ContentType.objects.get_for_model(ExamAttempt), object_id__in=[str(i) for i in attempt_ids]
        )
    return AuditLog.objects.filter(match).count()


# ── tətbiq ───────────────────────────────────────────────────────────────────
class PurgeRefused(Exception):
    def __init__(self, plan):
        super().__init__(",".join(plan.blockers))
        self.plan = plan


def apply_purge(exam, *, reason: str, allow_retake_links=False) -> PurgePlan:
    """Bir tranzaksiyada sil (imtahan sətri kilid kökü). Rədd halında heç nə yazılmır → ``PurgeRefused``."""
    from apps.exams.models import (
        CodingSubmission,
        Exam,
        ExamAttempt,
        ExamStudentPin,
        FinalAttemptDevice,
        FinalExamTicket,
        ProctoringLog,
        StudentExamAttemptGrant,
        SupervisionIncident,
    )

    with transaction.atomic():
        locked = Exam.objects.select_for_update().select_related("organization").get(pk=exam.pk)
        list(ExamAttempt.objects.select_for_update().filter(exam=locked).order_by("pk").values_list("pk", flat=True))
        plan = build_plan(locked, allow_retake_links=allow_retake_links)
        if plan.blockers:
            raise PurgeRefused(plan)
        if not plan.has_data and locked.is_deleted:
            return plan  # idempotent: artıq təmizdir — audit sətri də yazılmır
        ids = plan.attempt_ids
        # İmtahan ƏVVƏLCƏ silinmiş işarələnir — reyestr triggerinin dar istisnası (organizations 0071) bunu yoxlayır.
        locked.is_deleted = True
        locked.deleted_at = locked.deleted_at or timezone.now()
        locked.is_active = False
        locked.save(update_fields=["is_deleted", "deleted_at", "is_active"])
        if plan.counts.get("grade_events") and ids:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = 'on'")
                cursor.execute("DELETE FROM exams_examgradeevent WHERE attempt_id = ANY(%s)", [list(ids)])
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = 'off'")
        if plan.chance_grant_ids:
            # registrar 0097: append-only qoruyucusu yalnız bayraq + silinmiş imtahan + müraciətsiz sətirə icazə verir.
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = 'on'")
                cursor.execute(
                    "DELETE FROM registrar_examchancegrant WHERE id::text = ANY(%s) AND application_id IS NULL",
                    [plan.chance_grant_ids],
                )
                cursor.execute("SET LOCAL emsarena.trial_exam_purge = 'off'")
        _model("notifications.InAppNotification").objects.filter(pk__in=plan.notification_ids).delete()
        _model("registrar.ComponentScore").objects.filter(pk__in=plan.component_score_ids).delete()
        _model("appeals.KeyCorrectionCredit").objects.filter(
            Q(attempt_id__in=ids) | Q(correction__exam=locked)
        ).delete()
        _model("appeals.ScoreAdjustment").objects.filter(attempt_id__in=ids).delete()
        _model("appeals.AnswerKeyCorrection").objects.filter(exam=locked).delete()
        _model("appeals.Appeal").objects.filter(pk__in=plan.appeal_ids).delete()
        _model("live_exam.LiveSession").objects.filter(exam=locked).delete()
        FinalExamTicket.objects.filter(exam=locked).delete()
        ExamStudentPin.objects.filter(exam=locked).delete()
        StudentExamAttemptGrant.objects.filter(exam=locked).delete()
        SupervisionIncident.objects.filter(Q(exam=locked) | Q(attempt_id__in=ids)).delete()
        ProctoringLog.objects.filter(exam_attempt_id__in=ids).delete()
        FinalAttemptDevice.objects.filter(attempt_id__in=ids).delete()
        CodingSubmission.objects.filter(Q(exam=locked) | Q(attempt_id__in=ids)).delete()
        ExamAttempt.objects.filter(pk__in=ids).delete()  # cavablar, fayl sətirləri — CASCADE
        _restore_other_sources(locked, plan)
        _audit(locked, plan, reason)
        transaction.on_commit(lambda: _after_commit(locked.pk, plan.file_names))
    return plan


def _restore_other_sources(exam, plan):
    """Boşaldılmış xanaya başqa imtahanın rəsmi cəhdini yenidən yaz (bildirişsiz; körpü heç vaxt istisna atmır)."""
    from apps.exams.services.midterm_journal_sync import sync_midterm_attempt

    written = 0
    for attempt in _other_official_attempts(exam, plan.journal_rows):
        status, _row = sync_midterm_attempt(attempt, notify=False)
        written += int(status == "written")
    plan.counts["journal_restored_from_other_exam"] = written


def _audit(exam, plan, reason):
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.DELETE,
        user=None,
        organization=exam.organization,
        obj=exam,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(exam.pk),
        resource_repr=exam.slug,
        old_values={"title": exam.title, "slug": exam.slug, "attempt_ids": plan.attempt_ids},
        changes={"verb": "purge_trial_exam", "counts": {key: plan.counts.get(key, 0) for key in COUNT_KEYS}},
        reason=reason,
    )


def _after_commit(exam_pk, file_names):
    """Fayllar YALNIZ commit-dən sonra silinir (rollback-də fayl itməsin); keş best-effort."""
    from django.core.files.storage import default_storage

    failed = 0
    for name in file_names:
        try:
            default_storage.delete(name)
        except Exception:  # noqa: BLE001 — yetim fayl bazanı sındırmır
            failed += 1
    if failed:
        logger.warning("trial_exam_purge: %d stored file(s) could not be deleted", failed)
    try:
        from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache

        invalidate_exam_metadata_cache(exam_pk)
        invalidate_exam_question_ids_cache(exam_pk)
    except Exception:  # noqa: BLE001 — keş öz TTL-i ilə düşür
        logger.warning("trial_exam_purge: cache invalidation failed for exam %s", exam_pk, exc_info=True)


__all__ = ["AUDIT_RESOURCE_TYPE", "COUNT_KEYS", "PurgePlan", "PurgeRefused", "apply_purge", "build_plan", "find_exam"]
