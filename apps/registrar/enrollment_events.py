"""Tələbə jurnala yazılanda ``enrollments_activated`` siqnalı (sahib 2026-11-16).

Sahib: «qiymətləndirilmiş nəticəsi olan hər tələbənin nəticəsi öz səhifəsində görünsün, yeni jurnallarında da».
İmtahan balı jurnala yalnız cəhd bitəndə / yoxlananda / imtahan yenidən sinxronlaşanda yazılırdı — tələbə imtahandan
SONRA jurnala düşəndə (bərpa olunmuş qiyabi, yeni seçmə jurnalı, alt qrupa yerləşdirmə, qrupa sonradan gəlmə) balı
heç vaxt ora gəlmirdi. Registrar exams-ı import etmir (``scripts/module_deps.py``) — yalnız siqnal göndərir,
abunəçi (``apps.exams.services.enrollment_result_sync``) nəticəni yazır.

Mənbələr: ``Enrollment`` ``post_save`` (yaradılma və ya ``status`` yazısı ilə ``enrolled``) və toplu INSERT yolu
(:func:`announce` — ``services._insert_enrollments``; ``bulk_create`` ``post_save`` vermir). Siqnal commit-dən SONRA,
bir tranzaksiyada toplanmış sətirlər bir dəfə göndərilir.
"""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def _subject_ids(enrollments) -> dict:
    """``{offering_id: subject_id}`` — keşdəki açılışdan, yoxdursa BİR sorğu (tranzaksiya / RLS konteksti daxilində)."""
    from .models import CourseOffering

    known, missing = {}, set()
    for enrollment in enrollments:
        offering = enrollment._state.fields_cache.get("offering")
        if offering is not None:
            known[str(enrollment.offering_id)] = str(offering.subject_id)
        else:
            missing.add(enrollment.offering_id)
    if missing:
        for pk, subject_id in CourseOffering.objects.filter(pk__in=missing).values_list("pk", "subject_id"):
            known[str(pk)] = str(subject_id)
    return known


def announce(enrollments) -> None:
    """Aktiv (``enrolled``) qeydiyyatlar üçün commit-dən sonra ``enrollments_activated`` göndər (best-effort)."""
    from .models import Enrollment

    active = [
        row
        for row in enrollments or ()
        if getattr(row, "status", None) == Enrollment.Status.ENROLLED and getattr(row, "offering_id", None)
    ]
    if not active:
        return
    try:
        subjects = _subject_ids(active)
    except Exception:  # noqa: BLE001 — qeydiyyat yazısı heç vaxt sınmır; bərpa: audit_exam_results əmri
        logger.exception("enrollment_events: subject lookup failed")
        return
    by_org: dict = {}
    for row in active:
        offering_id = str(row.offering_id)
        by_org.setdefault(str(row.organization_id), set()).add(
            (str(row.student_id), offering_id, subjects.get(offering_id, ""))
        )

    def _send():
        from .signals import enrollments_activated

        for organization_id, rows in by_org.items():
            try:
                enrollments_activated.send(sender=Enrollment, organization_id=organization_id, rows=sorted(rows))
            except Exception:  # noqa: BLE001 — qeydiyyat yazısı heç vaxt sınmır; bərpa: audit_exam_results əmri
                logger.exception("enrollment_events: enrollments_activated failed (org=%s)", organization_id)

    transaction.on_commit(_send)


def enrollment_saved(sender, instance, created=False, update_fields=None, raw=False, **kwargs):
    """``post_save``: yeni sətir və ya ``status`` yazısı → ``enrolled`` olubsa siqnal (digər yazılar səssiz)."""
    if raw:
        return
    if not created and update_fields is not None and "status" not in update_fields:
        return  # qayıb saatı, alt qrup işarəsi və s. — nəticəyə təsir etmir
    announce([instance])


__all__ = ["announce", "enrollment_saved"]
