"""«İmtahan şansı ver» əməlinin RƏSMİ qeydi — səbəb növü, əsas (əmr №/tarix), qeyd (sahib 2026-10-18).

Sahib: «Granting a re-attempt must target concrete student(s) and require a reason type». Səbəb siyahısı
sabitdir (``ExamChanceReason``):

* **25% müraciəti** — yalnız həmin fənn üzrə ödənişi TƏSDİQLƏNMİŞ və BURAXILMIŞ 25% müraciəti olan tələbəyə;
  müraciət qeydə bağlanır və ``admitted`` → ``exam_granted`` olur;
* **Universitet güzəşti** — əmr / sərəncam № + tarix + qeyd məcburidir;
* **Texniki problem**, **Apellyasiya qərarı**, **Digər** — qeyd məcburidir.

2026-10-24 (sahib): HƏR səbəb üçün əsas SƏNƏD (əmr / sərəncam / ərizə — PDF və ya şəkil, 10 MB) məcburidir.
Fayl bir dəfə yazılır; eyni təqdimatda seçilmiş bütün tələbələrin qeydləri həmin yolu paylaşır.

Yazılı, test və praktiki (kod) imtahanlar üçün eynidir — imtahan növü qeydə snapshot kimi düşür. Exams
modulu registrar-ı çağırır (əksinə yox): imtahan ``exam`` lüğəti kimi gəlir (id, başlıq, növ, kateqoriya,
fənn). Qeyd append-only ``ExamChanceGrant`` sətridir və tələbənin 25% izində görünür.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core import superadmin_waiver

from . import retake_decisions, retake_files
from .models import ExamChanceGrant, ExamChanceReason, Subject
from .retake_services import actor_label, clean_upload

_CTX = "registrar.retake"

NOTE_MIN = 10

#: Səbəb → (əmr №/tarix məcburidir?, qeyd məcburidir?)
REQUIREMENTS = {
    ExamChanceReason.RETAKE_25: (False, False),
    ExamChanceReason.UNIVERSITY: (True, True),
    ExamChanceReason.TECHNICAL: (False, True),
    ExamChanceReason.APPEAL: (False, True),
    ExamChanceReason.OTHER: (False, True),
}


def grantable_applications(*, organization, student_ids) -> dict:
    """``student_id`` → «25% müraciəti» səbəbi ilə şans verilə bilən müraciətlər (tək sorğu)."""
    return retake_decisions.grantable_applications(organization=organization, student_ids=student_ids)


def reason_choices() -> list:
    return [(value, label) for value, label in ExamChanceReason.choices]


def _clean_date(raw):
    if isinstance(raw, datetime.date):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise ValidationError(pgettext(_CTX, "Əmr tarixi düzgün deyil.")) from None


def _clean_document(document):
    """Əsas sənəd məcburidir; uzantı / ölçü / imza-MIME yoxlaması 25% qəbzi ilə eynidir (``clean_upload``)."""
    if not document or not getattr(document, "name", ""):
        raise ValidationError(
            pgettext(_CTX, "Əsas sənədi (əmr / sərəncam / ərizə) yükləyin — sənədsiz cəhd hüququ verilmir.")
        )
    clean_upload(document)
    if hasattr(document, "seek"):
        document.seek(0)
    return document


def validate(
    *,
    organization,
    exam,
    students,
    reason,
    reference_number="",
    reference_date=None,
    note="",
    document=None,
    actor=None,
) -> dict:
    """Səbəbin tələblərini yoxla; ``{"reason", "reference_number", "reference_date", "note", "document",
    "applications"}``.

    ``actor`` superadmindirsə (sahib 2026-10-27) sənəd / əmr / qeyd İSTƏYƏ BAĞLIDIR: boş qeyd avtomatik
    «Superadmin düzəlişi — sənədsiz» mətni, boş əmr — «SA-…» nömrəsi + bu gün ilə dolur (25% müraciəti qaydası qalır).
    """
    if reason not in ExamChanceReason.values:
        raise ValidationError(pgettext(_CTX, "Cəhdin əsasını seçin."))
    students = [s for s in students if getattr(s, "pk", None)]
    if not students:
        raise ValidationError(pgettext(_CTX, "Ən azı bir tələbə seçilməlidir."))
    needs_reference, needs_note = REQUIREMENTS[reason]
    number = str(reference_number or "").strip()[:80]
    date = _clean_date(reference_date)
    text = str(note or "").strip()[:2000]
    waived = superadmin_waiver.waives(actor) and not (document and getattr(document, "name", ""))
    if waived:
        text = superadmin_waiver.stamp(text, actor)[:2000]
        if needs_reference:
            number, date = number or superadmin_waiver.order_number(), date or superadmin_waiver.order_date()
    if needs_reference and (not number or date is None):
        raise ValidationError(pgettext(_CTX, "Universitet güzəşti üçün əmr / sərəncam nömrəsi və tarixi məcburidir."))
    if needs_note and len(text) < NOTE_MIN:
        raise ValidationError(pgettext(_CTX, "Bu səbəb üçün qeyd məcburidir (ən azı {n} simvol).").format(n=NOTE_MIN))
    document = None if waived else _clean_document(document)
    applications: dict = {}
    if reason == ExamChanceReason.RETAKE_25:
        if exam.get("category") != "final":
            raise ValidationError(pgettext(_CTX, "25% müraciəti yalnız yekun (final) imtahan üçün cəhd hüququ verir."))
        grantable = retake_decisions.grantable_applications(
            organization=organization, student_ids=[s.pk for s in students]
        )
        missing = []
        for student in students:
            match = next(
                (a for a in grantable.get(student.pk, []) if a.subject_id == exam.get("subject_id")),
                None,
            )
            if match is None:
                missing.append((student.get_full_name() or "").strip() or student.username)
            else:
                applications[student.pk] = match
        if missing:
            raise ValidationError(
                pgettext(
                    _CTX,
                    "Bu fənn üzrə ödənişi təsdiqlənmiş və buraxılmış 25% müraciəti yoxdur: {names}.",
                ).format(names=", ".join(missing[:5]))
            )
    return {
        "reason": reason,
        "reference_number": number,
        "reference_date": date,
        "note": text,
        "document": document,
        "applications": applications,
    }


@transaction.atomic
def record(*, organization, exam, students, cleaned, extra, actor, request=None) -> list:
    """Hər tələbə üçün bir append-only qeyd; 25% səbəbində müraciət ``exam_granted`` olur."""
    subject_id = exam.get("subject_id")
    if subject_id and not Subject.objects.filter(pk=subject_id, organization=organization).exists():
        subject_id = None
    document = cleaned.get("document")
    document_name = str(getattr(document, "name", "") or "")[:255]
    rows = []
    with retake_files.discard_on_error():
        for student in students:
            rows.append(
                _record_one(
                    organization=organization,
                    exam=exam,
                    student=student,
                    subject_id=subject_id,
                    cleaned=cleaned,
                    extra=extra,
                    actor=actor,
                    request=request,
                    # Fayl ilk sətirdə storage-ə yazılır; qalanları eyni yolu paylaşır (təkrar nüsxə yox).
                    document=rows[0].document.name if rows else document,
                    document_name=document_name,
                )
            )
    return rows


def _record_one(*, organization, exam, student, subject_id, cleaned, extra, actor, request, document, document_name):
    application = cleaned["applications"].get(student.pk)
    grant = ExamChanceGrant.objects.create(
        organization=organization,
        student=student,
        subject_id=subject_id,
        exam_id=int(exam["id"]),
        exam_title=str(exam.get("title") or "")[:300],
        exam_type=str(exam.get("exam_type") or "")[:20],
        exam_category=str(exam.get("category") or "")[:20],
        reason=cleaned["reason"],
        reference_number=cleaned["reference_number"],
        reference_date=cleaned["reference_date"],
        note=cleaned["note"],
        document=document or "",
        document_name=document_name,
        application=application,
        extra_attempts=max(1, int(extra or 1)),
        granted_by=actor,
        granted_by_name=actor_label(actor),
    )
    if not isinstance(document, str):
        retake_files.track(grant.document)
    if application is not None:
        retake_decisions.mark_exam_granted(application=application, actor=actor, grant=grant, request=request)
    return grant


def recent(*, organization, limit=15) -> list:
    return list(
        ExamChanceGrant.objects.filter(organization=organization)
        .select_related("student", "application")
        .order_by("-created_at")[:limit]
    )


def totals(*, organization) -> dict:
    from django.db.models import Count, Sum

    data = ExamChanceGrant.objects.filter(organization=organization).aggregate(
        n=Count("id"), students=Count("student_id", distinct=True), attempts=Sum("extra_attempts")
    )
    return {"count": data["n"] or 0, "students": data["students"] or 0, "attempts": data["attempts"] or 0}


__all__ = [
    "NOTE_MIN",
    "REQUIREMENTS",
    "grantable_applications",
    "reason_choices",
    "recent",
    "record",
    "totals",
    "validate",
]
