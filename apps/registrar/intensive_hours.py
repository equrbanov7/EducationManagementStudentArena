"""İntensiv kursun saatını dəyişmək — registrar tərəfi (sahib 2026-11-25).

Dərs yükü modulu (``apps.workload.services.intensive_hours``) intensiv kursun saatını ləğv etmədən dəyişir
(real hal: 3 dərs keçilib, mühazirə 5 + seminar 5 → mühazirə 10 + seminar 5). Burada YALNIZ iki şey var:

* :func:`held_hours` — jurnalda keçilmiş saat növ üzrə (passiv dərs SAYILMIR — :mod:`.passive_lessons`);
* :func:`set_course_hours` — açılışın ``lesson_hours``-u (saat həddi #6 və «Kurs tamamlandı» ondan oxunur).

Qeydiyyatlara, dərslərə, xanalara toxunulmur. Qaydalar (icazə, hədd, keçilmiş saatdan az olmamaq) dərs yükü
servisindədir; bu funksiyalar yalnız intensiv açılışı qəbul edir.
"""

from __future__ import annotations

from django.db.models import Sum
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction

from .models import CourseFormat, CourseOffering, Lesson
from .passive_lessons import counted_q

_CTX = "registrar.intensive"


def _ensure_intensive(offering) -> None:
    if offering is None or offering.course_format != CourseFormat.INTENSIVE:
        raise ValueError("not an intensive offering")


def held_hours(offering) -> dict:
    """``{"lecture": N, "seminar": N, "lab": N}`` — passiv olmayan dərslərin saat cəmi (``Lesson.kind`` üzrə)."""
    _ensure_intensive(offering)
    rows = (
        Lesson.objects.filter(offering_id=offering.pk)
        .filter(counted_q())
        .values("kind")
        .annotate(total=Sum("hours"))
        .order_by()
    )
    result = {"lecture": 0, "seminar": 0, "lab": 0}
    for row in rows:
        result[row["kind"]] = result.get(row["kind"], 0) + int(row["total"] or 0)
    return result


def set_course_hours(*, offering, hours: int, by_user, reason: str = "") -> int:
    """Açılışın ``lesson_hours``-unu yaz (sətir kilidlənir); köhnə dəyəri qaytarır. Audit — registrar izi."""
    _ensure_intensive(offering)
    locked = CourseOffering.objects.select_for_update().get(pk=offering.pk)
    old = int(locked.lesson_hours or 0)
    hours = int(hours)
    if old == hours:
        return old
    locked.lesson_hours = hours
    locked.save(update_fields=["lesson_hours", "updated_at"])
    offering.lesson_hours = hours
    log_action(
        AuditAction.UPDATE,
        user=by_user,
        organization=locked.organization,
        obj=locked,
        old_values={"lesson_hours": old},
        new_values={"lesson_hours": hours},
        reason=" ".join(str(reason or "").split())[:255],
        resource_type="registrar.CourseOffering",
        resource_id=str(locked.pk),
        resource_repr=f"{locked.subject.code} · {pgettext(_CTX, 'İntensiv')}",
    )
    return old


__all__ = ["held_hours", "set_course_hours"]
