"""«Xarici nəticənin tanınması» — YAZI qatı: yoxlama, yaratma (+ fəndən azad), ləğv, sənəd girişi (2026-10-25).

Sahib: «Tələbə Erasmus-da və ya başqa universitetdə fənn keçmiş ola bilər — akademik nəticəni göstərə bilər
və o fəndən AZAD oluna».

YENİ MEXANİZM İCAD OLUNMUR:

* **Azadlıq** — :func:`subject_exempt.exempt_student` (``JournalHygieneDecision`` kateqoriya ``subject_exempt``,
  səbəb kodu ``external_recognition``): jurnal qeydiyyatı ``enrolled → dropped`` olur, ona görə jurnal, qayıb
  limiti, imtahana buraxılış / siyahısı, sorğu hədəfləri və «Fənlərim» onu artıq süzür. Jurnal bağlıdırsa və ya
  dövr keçibsə (siyahı qapısı, ``guest_roster.roster_block_reason``) qeydiyyata toxunulmur — tanınma yenə yazılır
  və transkriptdə həmin sətri əvəz edir.
* **Sənəd** — 25% / «İmtahan şansı» naxışı (``retake_services.clean_upload``: PDF/JPG/PNG, 10 MB, imza-MIME),
  qorunan media ``credit_recognition_documents/`` (:func:`check_document_access`).
* **Ləğv** — bir dəfə, səbəblə (≥10 simvol); bağlı azadlıq ``subject_exempt.restore_student`` ilə geri açılır
  (tələbə jurnala qayıdır). Hər iki əməl ``core.audit``-a yazılır (``registrar.credit_recognition``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from core import audit as audit_service
from core.constants import AuditAction

from . import credit_recognition_read as read
from . import credit_source, guest_roster, retake_files, subject_exempt
from .models import Enrollment, ExternalCreditRecognition, RecognitionProgram
from .retake_services import actor_label, clean_upload

_CTX = "registrar.recognition"
AUDIT_RESOURCE = "registrar.credit_recognition"
REVOKE_REASON_MIN = 10
FOREIGN_CREDIT_MAX = Decimal("60")
PROGRAM_NAME_MAX = 150
_LIMITS = {
    "institution": 255,
    "country": 100,
    "foreign_subject": 300,
    "foreign_grade": 32,
    "study_period": 100,
}


class RecognitionError(Exception):
    """İstifadəçiyə göstərilən xəta (kod + mesaj + HTTP statusu) — ``MovementError`` naxışı."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(code, message, status)
        self.code = code
        self.message = message
        self.status = status


def _text(raw, limit) -> str:
    return " ".join(str(raw or "").split())[:limit]


def _required_texts(data) -> dict:
    labels = {
        "institution": pgettext(_CTX, "Qurum (universitet)"),
        "country": pgettext(_CTX, "Ölkə"),
        "foreign_subject": pgettext(_CTX, "Xarici fənnin adı"),
        "foreign_grade": pgettext(_CTX, "Xarici qiymət"),
        "study_period": pgettext(_CTX, "Təhsil müddəti / semestr"),
    }
    cleaned = {}
    for key, limit in _LIMITS.items():
        value = _text(data.get(key), limit)
        if not value:
            raise RecognitionError("required", pgettext(_CTX, "«%(field)s» doldurulmalıdır.") % {"field": labels[key]})
        cleaned[key] = value
    return cleaned


def _foreign_credit(raw) -> Decimal:
    try:
        value = Decimal(str(raw or "").strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        value = None
    if value is None or not value.is_finite() or value <= 0 or value > FOREIGN_CREDIT_MAX:
        raise RecognitionError(
            "foreign_credit", pgettext(_CTX, "Xarici kredit 0-dan böyük rəqəm olmalıdır (ən çox 60).")
        )
    return value.quantize(Decimal("0.01"))


def _score(raw) -> int:
    floor = read.pass_score()
    text = str(raw or "").strip()
    if not text.isdigit() or not floor <= int(text) <= 100:
        raise RecognitionError(
            "recognized_score",
            pgettext(_CTX, "Bizim şkalada qarşılıq %(floor)s–100 arası tam bal olmalıdır (tanınma keçmiş nəticəyədir).")
            % {"floor": floor},
        )
    return int(text)


def _document(document):
    if not document or not getattr(document, "name", ""):
        raise RecognitionError(
            "document_required",
            pgettext(_CTX, "Əsas sənədi yükləyin (transkript, Learning Agreement və ya əmr) — sənədsiz tanınma olmur."),
        )
    try:
        clean_upload(document)
    except ValidationError as exc:
        raise RecognitionError("document_invalid", " ".join(exc.messages)) from None
    if hasattr(document, "seek"):
        document.seek(0)
    return document


def validate(*, organization, student_id, data, document) -> dict:
    """Formanın bütün sahələri — xəta :class:`RecognitionError` (400 / 404 / 409)."""
    program = str(data.get("program") or "").strip()
    if program not in RecognitionProgram.values:
        raise RecognitionError("program", pgettext(_CTX, "Proqramı seçin."))
    program_name = _text(data.get("program_name"), PROGRAM_NAME_MAX)
    if program == RecognitionProgram.OTHER and not program_name:
        raise RecognitionError(
            "program_name",
            pgettext(_CTX, "«Digər» seçilibsə proqramın / səbəbin adını yazın (məs. yay məktəbi, onlayn kurs)."),
        )
    cleaned = {"program": program, "program_name": program_name, **_required_texts(data)}
    cleaned["foreign_credit"] = _foreign_credit(data.get("foreign_credit"))
    cleaned["recognized_score"] = _score(data.get("recognized_score"))
    cleaned["note"] = str(data.get("note") or "").strip()[:2000]
    enrollment = (
        Enrollment.objects.filter(
            organization=organization, student_id=student_id, pk=_uuid_or_none(data.get("enrollment"))
        )
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering__subject", "offering__period")
        .first()
    )
    if enrollment is None:
        raise RecognitionError("enrollment", pgettext(_CTX, "Bizim fənni (jurnal qeydiyyatını) seçin."), status=404)
    if ExternalCreditRecognition.objects.filter(
        organization=organization,
        student_id=student_id,
        subject_id=enrollment.offering.subject_id,
        period_id=enrollment.offering.period_id,
        revoked_at__isnull=True,
    ).exists():
        raise RecognitionError(
            "duplicate",
            pgettext(_CTX, "Bu fənn üzrə bu semestrdə qüvvədə olan tanınma artıq var — əvvəlcə onu ləğv edin."),
            status=409,
        )
    cleaned["enrollment"] = enrollment
    cleaned["document"] = _document(document)
    return cleaned


def _uuid_or_none(raw):
    import uuid

    try:
        return uuid.UUID(str(raw or "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _exempt(enrollment, recognition_ref, cleaned, actor, request):
    """Açıq jurnalda «Fəndən azad» qərarı (``external_recognition``); bağlı / keçmiş dövrdə ``None``."""
    offering = enrollment.offering
    if enrollment.status != Enrollment.Status.ENROLLED or guest_roster.roster_block_reason(offering):
        return None
    draft = ExternalCreditRecognition(program=cleaned["program"], program_name=cleaned["program_name"])
    reason = pgettext(_CTX, "Xarici nəticə tanınıb: %(program)s · %(institution)s · %(subject)s") % {
        "program": draft.program_label,
        "institution": cleaned["institution"],
        "subject": cleaned["foreign_subject"],
    }
    result = subject_exempt.exempt_student(
        offering=offering,
        enrollment_id=enrollment.pk,
        actor=actor,
        reason=reason,
        request=request,
        reason_code=subject_exempt.RECOGNITION_REASON_CODE,
        evidence_extra={"recognition": recognition_ref, "recognized_score": cleaned["recognized_score"]},
    )
    return result["decision_id"]


def create(*, organization, student_id, cleaned, actor, request=None) -> dict:
    """Tanınma + (mümkünsə) fəndən azad + audit — bir tranzaksiya; xətada yüklənmiş fayl silinir."""
    import uuid

    enrollment = cleaned["enrollment"]
    document = cleaned["document"]
    recognition_id = uuid.uuid4()
    with transaction.atomic(), retake_files.discard_on_error():
        enrollment = (
            Enrollment.objects.select_for_update(of=("self",))
            .select_related("offering__subject", "offering__period", "offering__organization")
            .get(pk=enrollment.pk)
        )
        if enrollment.status == Enrollment.Status.DROPPED:
            raise RecognitionError("enrollment", pgettext(_CTX, "Bizim fənni (jurnal qeydiyyatını) seçin."), status=409)
        credit = credit_source.credits_for_enrollments([enrollment], organization=organization).get(enrollment.pk)
        decision_id = _exempt(enrollment, str(recognition_id), cleaned, actor, request)
        recognition = ExternalCreditRecognition(
            id=recognition_id,
            organization=organization,
            student_id=student_id,
            subject_id=enrollment.offering.subject_id,
            period_id=enrollment.offering.period_id,
            enrollment=enrollment,
            exempt_decision_id=decision_id,
            program=cleaned["program"],
            program_name=cleaned["program_name"],
            institution=cleaned["institution"],
            country=cleaned["country"],
            foreign_subject=cleaned["foreign_subject"],
            foreign_credit=cleaned["foreign_credit"],
            foreign_grade=cleaned["foreign_grade"],
            study_period=cleaned["study_period"],
            recognized_score=cleaned["recognized_score"],
            credit=int(credit or getattr(enrollment.offering.subject, "ects", 0) or 0),
            note=cleaned["note"],
            document_name=str(getattr(document, "name", "") or "")[:255],
            created_by=actor if getattr(actor, "pk", None) else None,
            created_by_name=actor_label(actor),
        )
        recognition.document.save(recognition.document_name or "document", document, save=False)
        retake_files.track(recognition.document)
        recognition.save()
        _audit(recognition, actor, request, action=AuditAction.CREATE, reason=recognition.note)
    return {"recognition": recognition, "exempted": decision_id is not None}


def revoke(*, organization, recognition_id, actor, reason, request=None, allowed_students=None) -> dict:
    """Bir dəfəlik ləğv: azadlıq geri açılır (tələbə jurnala qayıdır), sətir ``revoked_*`` ilə bağlanır."""
    text = " ".join(str(reason or "").split())[:2000]
    if len(text) < REVOKE_REASON_MIN:
        raise RecognitionError(
            "reason", pgettext(_CTX, "Ləğvin səbəbini yazın (ən azı %(n)s simvol).") % {"n": REVOKE_REASON_MIN}
        )
    with transaction.atomic():
        recognition = (
            ExternalCreditRecognition.objects.select_for_update(of=("self",))
            .select_related("exempt_decision__enrollment__offering")
            .filter(organization=organization, pk=_uuid_or_none(recognition_id))
            .first()
        )
        if recognition is None or (allowed_students is not None and recognition.student_id not in allowed_students):
            raise RecognitionError("not_found", pgettext(_CTX, "Tanınma tapılmadı."), status=404)
        if recognition.revoked_at is not None:
            raise RecognitionError("already_revoked", pgettext(_CTX, "Bu tanınma artıq ləğv edilib."), status=409)
        decision = recognition.exempt_decision
        restored = False
        if decision is not None and decision.reverted_at is None:
            try:
                subject_exempt.restore_student(
                    offering=decision.enrollment.offering,
                    decision_id=decision.pk,
                    actor=actor,
                    reason=pgettext(_CTX, "Xarici nəticənin tanınması ləğv edildi: %(reason)s") % {"reason": text},
                    request=request,
                    allow_recognition=True,
                )
            except subject_exempt.HygieneError as exc:
                raise RecognitionError(exc.code, exc.message, status=exc.status) from None
            restored = True
        recognition.revoked_at = timezone.now()
        recognition.revoked_by = actor if getattr(actor, "pk", None) else None
        recognition.revoked_by_name = actor_label(actor)
        recognition.revoke_reason = text
        recognition.save(update_fields=["revoked_at", "revoked_by", "revoked_by_name", "revoke_reason", "updated_at"])
        _audit(recognition, actor, request, action=AuditAction.UPDATE, reason=text, revoked=True)
    return {"recognition": recognition, "restored": restored}


def _audit(recognition, actor, request, *, action, reason, revoked=False):
    audit_service.log_action(
        action=action,
        user=actor if getattr(actor, "pk", None) else None,
        organization=recognition.organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(recognition.pk),
        resource_repr=f"{recognition.subject_id}@{recognition.period_id} · {recognition.recognized_score}",
        new_values={
            "student_id": recognition.student_id,
            "subject_id": str(recognition.subject_id),
            "period_id": str(recognition.period_id),
            "program": recognition.program,
            "program_name": recognition.program_name,
            "recognized_score": recognition.recognized_score,
            "credit": recognition.credit,
            "exempt_decision_id": str(recognition.exempt_decision_id or ""),
            "revoked": revoked,
        },
        reason=reason or "",
    )


def check_document_access(user, path: str) -> bool:
    """Qorunan media: tələbənin özü, superadmin, açar sahibi (tələbə əhatəsində). Default DENY."""
    if not path or not getattr(user, "is_authenticated", False):
        return False
    try:
        recognition = ExternalCreditRecognition.objects.select_related("organization").get(document=path)
    except (ExternalCreditRecognition.DoesNotExist, ExternalCreditRecognition.MultipleObjectsReturned):
        return False
    if recognition.student_id == user.pk:
        return True
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return read.student_in_scope(user, recognition.organization, recognition.student_id)


__all__ = [
    "AUDIT_RESOURCE",
    "REVOKE_REASON_MIN",
    "RecognitionError",
    "check_document_access",
    "create",
    "revoke",
    "validate",
]
