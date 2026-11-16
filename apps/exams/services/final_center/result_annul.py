"""final_center — imtahan nəticəsinin ləğvi və bərpası (sahib 2026-11-16 / 2026-11-17).

Sahib 2026-11-16: «imtahandan uzaqlaşdırılmış tələbələrin midterm nəticəsi ləğv olmalıdır, qeyd kimi də düşməlidir»;
«bəzən nəzarətçi uzaqlaşdırana kimi tələbə “Bitir” vurur, bal sistemə düşür — o balı izahat yazılaraq ləğv
etmək, “köçürdü” və ya başqa səbəb kimi qeyd etmək olmalıdır».

Sahib 2026-11-17: ləğv nəticələr siyahısından da edilir — səbəb siyahıdan, izahat, hadisə tarixi, istəyə görə sənəd,
təsdiq pəncərəsi ilə; «səhv də ola bilər» — ləğv geri qaytarılır («Bərpa et», öz təsdiq pəncərəsi ilə), əvvəlki
bal və jurnal dəyəri qayıdır. Hər iki əməl audit-ə yazılır.

Ləğv = cəhd ``supervision_status="removed"`` olur (jurnal körpüsü bunu 0 bal kimi yazır — midterm də, final də).
Qeyd ``ExamResultAnnulment`` sətridir (kim, səbəb, izahat, tarix, sənəd, əvvəlki status); tələbənin ekranındakı
qeyd üçün ``SupervisionIncident(teacher_action="result_annulled")`` hadisəsi də yazılır (siyahı səhifələri onu
əlavə sorğusuz oxuyur). Bərpada hadisə ``result_annul_restored`` olur (silinmir), ``result_restored`` hadisəsi və
``restored_*`` sahələri əlavə olunur, cəhd ləğvdən ƏVVƏLKİ statusuna qayıdır, jurnal yenidən sinxronlaşır.
Cəhd heç vaxt SİLİNMİR (cavablar qalır).
"""

from __future__ import annotations

import logging
import os

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.domain.result_annulment import ANNUL_DOCUMENT_EXTENSIONS, ExamResultAnnulment
from apps.exams.models import ExamAttempt, SupervisionIncident
from core.audit import log_action
from core.constants import AuditAction

from .tickets import TicketStateError

logger = logging.getLogger(__name__)

ANNUL_ACTION = "result_annulled"
RESTORED_INCIDENT_ACTION = "result_annul_restored"
RESTORE_ACTION = "result_restored"

ANNUL_REMOVED = "removed"
ANNUL_CHEATING = "cheating"
ANNUL_DEVICE = "forbidden_device"
ANNUL_IMPERSONATION = "impersonation"
ANNUL_OTHER = "other"

ANNUL_REASONS = (
    (ANNUL_CHEATING, pgettext_lazy("exams.final_center.annul", "Köçürmə")),
    (ANNUL_DEVICE, pgettext_lazy("exams.final_center.annul", "Qadağan olunmuş vasitədən istifadə (telefon və s.)")),
    (ANNUL_IMPERSONATION, pgettext_lazy("exams.final_center.annul", "İmtahanı başqası verib")),
    (ANNUL_REMOVED, pgettext_lazy("exams.final_center.annul", "İmtahandan uzaqlaşdırıldığına görə")),
    (ANNUL_OTHER, pgettext_lazy("exams.final_center.annul", "Digər səbəb")),
)
_REASON_LABELS = dict(ANNUL_REASONS)

#: Sənəd ölçüsü — ``apps.exams.validators.validate_file_size`` ilə eyni hədd.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
NOTE_MAX = 1000


def reason_label(key: str) -> str:
    return str(_REASON_LABELS.get(key, key or ""))


def display_reason(annulment) -> str:
    """Tələbəyə / siyahıya göstərilən mətn: «Səbəb: izahat»."""
    return f"{reason_label(annulment.reason_key)}: {annulment.note}"[:NOTE_MAX]


def active_annulment(attempt):
    """Cəhdin AKTİV (bərpa olunmamış) ləğv qeydi və ya ``None``."""
    if attempt is None or not getattr(attempt, "pk", None):
        return None
    return ExamResultAnnulment.objects.filter(attempt_id=attempt.pk, restored_at__isnull=True).first()


def annul_incident(attempt):
    """Geri uyğunluq (PR #366): cəhdin aktiv ləğv qeydi və ya ``None``."""
    return active_annulment(attempt)


def is_annulled(attempt) -> bool:
    if attempt is None or not getattr(attempt, "pk", None):
        return False
    return ExamResultAnnulment.objects.filter(attempt_id=attempt.pk, restored_at__isnull=True).exists()


def _clean_note(note, *, required_message):
    note = (note or "").strip()
    if not note:
        raise TicketStateError(required_message)
    return note[:NOTE_MAX]


def _clean_incident_date(value):
    """Hadisə tarixi: verilməyibsə bu gün; gələcək tarix qəbul edilmir."""
    today = timezone.localdate()
    if value in (None, ""):
        return today
    if isinstance(value, str):
        from datetime import date

        try:
            value = date.fromisoformat(value.strip())
        except ValueError:
            raise TicketStateError(pgettext("exams.final_center.error", "Tarix düzgün deyil.")) from None
    if value > today:
        raise TicketStateError(pgettext("exams.final_center.error", "Hadisə tarixi gələcəkdə ola bilməz."))
    return value


def _check_document(document):
    if not document:
        return None
    ext = os.path.splitext(getattr(document, "name", "") or "")[1].lower()
    if ext not in ANNUL_DOCUMENT_EXTENSIONS:
        raise TicketStateError(
            pgettext("exams.final_center.error", "Sənəd PDF, şəkil (PNG/JPG) və ya Word faylı olmalıdır.")
        )
    if (getattr(document, "size", 0) or 0) > MAX_DOCUMENT_BYTES:
        raise TicketStateError(pgettext("exams.final_center.error", "Sənəd 10 MB-dan böyük ola bilməz."))
    # Layihənin ümumi yükləmə qapısı: MIME + məzmun imzası (adı .pdf olan istənilən fayl keçməsin).
    from django.core.exceptions import ValidationError

    from core.upload_security import validate_uploaded_file

    try:
        validate_uploaded_file(document, allowed_extensions=ANNUL_DOCUMENT_EXTENSIONS, max_size_mb=10)
    except ValidationError:
        raise TicketStateError(
            pgettext("exams.final_center.error", "Sənəd PDF, şəkil (PNG/JPG) və ya Word faylı olmalıdır.")
        ) from None
    return document


def _lock_attempt(attempt):
    """Cəhd sətrini ``FOR UPDATE`` ilə kilidlə və vəziyyəti bazadan təzələ (iki paralel əməl iki qeyd yaratmasın)."""
    row = (
        ExamAttempt.objects.select_for_update(of=("self",))
        .filter(pk=attempt.pk)
        .values("status", "supervision_status")
        .first()
    )
    if row is None:
        raise TicketStateError(pgettext("exams.final_center.error", "Bu biletdə imtahan cəhdi yoxdur."))
    attempt.status = row["status"]
    attempt.supervision_status = row["supervision_status"]


def _score_snapshot(attempt):
    """Audit üçün ləğvdən əvvəlki faiz (hesablana bilmirsə ``None`` — əməliyyatı dayandırmır)."""
    try:
        return round(float(attempt.score_percent), 2)
    except Exception:  # noqa: BLE001 — audit köməkçisidir
        logger.warning("result_annul: score snapshot failed for attempt %s", attempt.pk, exc_info=True)
        return None


def _sync_journal(attempt, by):
    """Ləğv / bərpadan sonra jurnal xanası.

    Midterm-də rəsmi cəhd = ən yüksək bal (``pick_official``): ləğv edilən cəhd rəsmi idisə, onun yerinə eyni xanaya
    yazılan DİGƏR cəhd rəsmi olur, bərpada isə əksinə — ona görə həmin xananın YENİ rəsmi cəhdi də yazılır (yoxsa
    köhnə yüksək bal jurnalda qalardı). Final-da rəsmi = ən son cəhd, ləğv olunan cəhdin öz yazısı kifayətdir."""
    from apps.exams.services.journal_sync import sync_attempt_to_journal

    sync_attempt_to_journal(attempt, actor=by)  # heç vaxt istisna atmır
    try:
        with transaction.atomic():  # savepoint: xəta çağıranın tranzaksiyasını «aborted» qoymasın
            _sync_midterm_official(attempt, by)
    except Exception:  # noqa: BLE001 — körpü heç vaxt ləğv/bərpa əməlini sındırmır
        logger.exception("result_annul: midterm official resync failed for attempt %s", attempt.pk)


def _sync_midterm_official(attempt, by):
    from apps.exams.services import midterm_journal_sync
    from apps.exams.services.journal_sync import sync_attempt_to_journal
    from apps.exams.services.journal_sync_scope import has_same_target

    if not midterm_journal_sync.is_auto_midterm_exam(attempt.exam):
        return
    same_student = ExamAttempt.objects.filter(
        user_id=attempt.user_id, exam__organization_id=attempt.exam.organization_id
    )
    for official in midterm_journal_sync.official_attempts(same_student):
        if official.pk != attempt.pk and has_same_target(attempt, [official]):
            sync_attempt_to_journal(official, actor=by)


def annul_attempt_result(
    attempt,
    by,
    *,
    reason_key: str,
    note: str,
    incident_date=None,
    document=None,
    request=None,
    sync_journal: bool = True,
) -> bool:
    """Bitmiş cəhdin nəticəsini ləğv et → ``True`` (yeni ləğv) / ``False`` (artıq ləğv olunub).

    Səbəb + izahat MƏCBURİDİR; hadisə tarixi (defolt bu gün) və sənəd istəyə bağlıdır. Cəhd bitməyibsə —
    əvvəlcə tələbə imtahandan çıxarılmalıdır (``remove_student``).
    """
    if reason_key not in _REASON_LABELS:
        raise TicketStateError(pgettext("exams.final_center.error", "Ləğv səbəbi seçilməyib."))
    note = _clean_note(
        note, required_message=pgettext("exams.final_center.error", "İzahat yazılmadan nəticə ləğv edilə bilməz.")
    )
    incident_date = _clean_incident_date(incident_date)
    document = _check_document(document)
    if attempt is None:
        raise TicketStateError(pgettext("exams.final_center.error", "Bu biletdə imtahan cəhdi yoxdur."))
    if getattr(attempt, "is_trial", False):
        raise TicketStateError(pgettext("exams.final_center.error", "Sınaq cəhdinin nəticəsi jurnala düşmür."))
    if not attempt.is_finished:
        raise TicketStateError(
            pgettext("exams.final_center.error", "İmtahan hələ davam edir — əvvəlcə tələbəni imtahandan çıxarın.")
        )

    with transaction.atomic():
        _lock_attempt(attempt)
        if not attempt.is_finished:
            raise TicketStateError(
                pgettext("exams.final_center.error", "İmtahan hələ davam edir — əvvəlcə tələbəni imtahandan çıxarın.")
            )
        if ExamResultAnnulment.objects.filter(attempt_id=attempt.pk, restored_at__isnull=True).exists():
            return False
        old_status = attempt.supervision_status
        score_before = _score_snapshot(attempt)
        annulment = ExamResultAnnulment(
            organization_id=attempt.exam.organization_id,
            attempt=attempt,
            reason_key=reason_key,
            note=note,
            incident_date=incident_date,
            previous_supervision_status=old_status or "active",
            annulled_by=by if getattr(by, "pk", None) else None,
        )
        if document:
            annulment.document = document
        annulment.save()
        if old_status != "removed":
            attempt.supervision_status = "removed"
            attempt.save(update_fields=["supervision_status"])
        SupervisionIncident.objects.create(
            organization=attempt.exam.organization,
            exam=attempt.exam,
            attempt=attempt,
            student=attempt.user,
            event_type="auto_submitted",
            severity="critical",
            metadata={
                "teacher_id": getattr(by, "pk", None),
                "teacher_username": getattr(by, "username", ""),
                "previous_status": old_status,
                "reason": ANNUL_ACTION,
                "reason_key": reason_key,
                "note": note,
                "display_reason": display_reason(annulment),
                "intervention_action": "annulled",
                "annulment_id": annulment.pk,
                "incident_date": incident_date.isoformat(),
                "document": bool(annulment.document),
            },
            violation_count_at_time=attempt.supervision_violation_count,
            teacher_action=ANNUL_ACTION,
        )
        log_action(
            AuditAction.UPDATE,
            user=by,
            organization=attempt.exam.organization,
            obj=attempt,
            old_values={"supervision_status": old_status, "score_percent": score_before},
            new_values={
                "supervision_status": "removed",
                "annulled": True,
                "reason_key": reason_key,
                "incident_date": incident_date.isoformat(),
                "annulment_id": annulment.pk,
                "document": bool(annulment.document),
            },
            reason=f"exam_result_annulled[{reason_key}]: {note}"[:500],
            request=request,
            resource_type="exams.ExamAttempt",
            resource_id=str(attempt.pk),
            resource_repr=getattr(attempt.exam, "title", ""),
        )
    if sync_journal:
        _sync_journal(attempt, by)  # 0 bal (qovulma qaydası)
    return True


def restore_attempt_result(attempt, by, *, note: str, request=None, sync_journal: bool = True) -> bool:
    """Ləğvi geri qaytar → ``True`` (bərpa olundu) / ``False`` (aktiv ləğv yoxdur).

    Cəhd ləğvdən ƏVVƏLKİ ``supervision_status``-a qayıdır (imtahan zamanı uzaqlaşdırılıb sonra ləğv edilibsə
    uzaqlaşdırma qalır — 0 bal davam edir), jurnal yenidən sinxronlaşır. Bərpa səbəbi MƏCBURİDİR.
    """
    note = _clean_note(
        note, required_message=pgettext("exams.final_center.error", "Bərpa səbəbi yazılmadan ləğv geri qaytarılmır.")
    )
    if attempt is None:
        raise TicketStateError(pgettext("exams.final_center.error", "Bu biletdə imtahan cəhdi yoxdur."))
    now = timezone.now()
    with transaction.atomic():
        _lock_attempt(attempt)
        annulment = (
            ExamResultAnnulment.objects.select_for_update()
            .filter(attempt_id=attempt.pk, restored_at__isnull=True)
            .first()
        )
        if annulment is None:
            return False
        old_status = attempt.supervision_status
        new_status = annulment.previous_supervision_status or "active"
        annulment.restored_at = now
        annulment.restored_by = by if getattr(by, "pk", None) else None
        annulment.restore_note = note
        annulment.save(update_fields=["restored_at", "restored_by", "restore_note"])
        if old_status != new_status:
            attempt.supervision_status = new_status
            attempt.save(update_fields=["supervision_status"])
        for incident in SupervisionIncident.objects.filter(attempt_id=attempt.pk, teacher_action=ANNUL_ACTION):
            meta = dict(incident.metadata) if isinstance(incident.metadata, dict) else {}
            meta.update({"restored_at": now.isoformat(), "restored_by": getattr(by, "pk", None)})
            incident.metadata = meta
            incident.teacher_action = RESTORED_INCIDENT_ACTION
            incident.save(update_fields=["metadata", "teacher_action"])
        SupervisionIncident.objects.create(
            organization=attempt.exam.organization,
            exam=attempt.exam,
            attempt=attempt,
            student=attempt.user,
            event_type="teacher_resumed",
            severity="info",
            metadata={
                "teacher_id": getattr(by, "pk", None),
                "teacher_username": getattr(by, "username", ""),
                "previous_status": old_status,
                "reason": RESTORE_ACTION,
                "note": note,
                "annulment_id": annulment.pk,
            },
            violation_count_at_time=attempt.supervision_violation_count,
            teacher_action=RESTORE_ACTION,
        )
        log_action(
            AuditAction.UPDATE,
            user=by,
            organization=attempt.exam.organization,
            obj=attempt,
            old_values={"supervision_status": old_status, "annulled": True, "annulment_id": annulment.pk},
            new_values={"supervision_status": new_status, "annulled": False},
            reason=f"exam_result_restored: {note}"[:500],
            request=request,
            resource_type="exams.ExamAttempt",
            resource_id=str(attempt.pk),
            resource_repr=getattr(attempt.exam, "title", ""),
        )
    if sync_journal:
        _sync_journal(attempt, by)  # əvvəlki bal qayıdır
    return True


__all__ = [
    "ANNUL_ACTION",
    "ANNUL_CHEATING",
    "ANNUL_DEVICE",
    "ANNUL_IMPERSONATION",
    "ANNUL_OTHER",
    "ANNUL_REASONS",
    "ANNUL_REMOVED",
    "RESTORED_INCIDENT_ACTION",
    "RESTORE_ACTION",
    "active_annulment",
    "annul_attempt_result",
    "annul_incident",
    "display_reason",
    "is_annulled",
    "reason_label",
    "restore_attempt_result",
]
