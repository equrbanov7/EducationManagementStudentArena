"""«İmtahan şansı ver» əməlinin RƏSMİ qeydi — səbəb növü, əsas (əmr №/tarix), qeyd (sahib 2026-10-18).

Sahib: «Granting a re-attempt must target concrete student(s) and require a reason type». Səbəb siyahısı
sabitdir (``ExamChanceReason``):

* **25% müraciəti** — yalnız həmin fənn üzrə ödənişi TƏSDİQLƏNMİŞ və BURAXILMIŞ 25% müraciəti olan tələbəyə;
  müraciət qeydə bağlanır və ``admitted`` → ``exam_granted`` olur;
* **Universitet güzəşti** — əmr / sərəncam № + tarix + qeyd məcburidir;
* **Texniki problem**, **Apellyasiya qərarı**, **Digər** — qeyd məcburidir.

Yazılı, test və praktiki (kod) imtahanlar üçün eynidir — imtahan növü qeydə snapshot kimi düşür. Exams
modulu registrar-ı çağırır (əksinə yox): imtahan ``exam`` lüğəti kimi gəlir (id, başlıq, növ, kateqoriya,
fənn). Qeyd append-only ``ExamChanceGrant`` sətridir və tələbənin 25% izində görünür.
"""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from . import retake_decisions
from .models import ExamChanceGrant, ExamChanceReason, Subject
from .retake_services import actor_label

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


def validate(*, organization, exam, students, reason, reference_number="", reference_date=None, note="") -> dict:
    """Səbəbin tələblərini yoxla; ``{"reason", "reference_number", "reference_date", "note", "applications"}``."""
    if reason not in ExamChanceReason.values:
        raise ValidationError(pgettext(_CTX, "Cəhdin əsasını seçin."))
    students = [s for s in students if getattr(s, "pk", None)]
    if not students:
        raise ValidationError(pgettext(_CTX, "Ən azı bir tələbə seçilməlidir."))
    needs_reference, needs_note = REQUIREMENTS[reason]
    number = str(reference_number or "").strip()[:80]
    date = _clean_date(reference_date)
    text = str(note or "").strip()[:2000]
    if needs_reference and (not number or date is None):
        raise ValidationError(pgettext(_CTX, "Universitet güzəşti üçün əmr / sərəncam nömrəsi və tarixi məcburidir."))
    if needs_note and len(text) < NOTE_MIN:
        raise ValidationError(pgettext(_CTX, "Bu səbəb üçün qeyd məcburidir (ən azı {n} simvol).").format(n=NOTE_MIN))
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
        "applications": applications,
    }


@transaction.atomic
def record(*, organization, exam, students, cleaned, extra, actor, request=None) -> list:
    """Hər tələbə üçün bir append-only qeyd; 25% səbəbində müraciət ``exam_granted`` olur."""
    subject_id = exam.get("subject_id")
    if subject_id and not Subject.objects.filter(pk=subject_id, organization=organization).exists():
        subject_id = None
    rows = []
    for student in students:
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
            application=application,
            extra_attempts=max(1, int(extra or 1)),
            granted_by=actor,
            granted_by_name=actor_label(actor),
        )
        if application is not None:
            retake_decisions.mark_exam_granted(application=application, actor=actor, grant=grant, request=request)
        rows.append(grant)
    return rows


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
