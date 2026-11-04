"""«Alt qrup tələbələri» bölməsindən əlavə — HƏDƏF JURNAL axtarışı (sahib 2026-11-05, yalnız OXU).

Sahib: bölmədən də alt qrupa tələbə əlavə etmək mümkün olsun. YENİ YAZI YOLU YOXDUR: modal jurnal seçəndən sonra
jurnal modalının RƏSMİ endpoint-lərini işlədir (``registrar:journal_guest_group_search`` /
``journal_guest_student_search`` / ``journal_guest_add`` → :func:`guest_roster.add_guest_student` +
:func:`subgroup_placement.journal_modal_check` kredit / tutum qapısı). Bu modul yalnız seçilə bilən jurnalları verir:

* aktorun ``journal.roster`` əhatəsi (:mod:`apps.registrar.guest_roster` — eyni qayda): unit rolu yalnız öz
  alt-ağacındakı qrupların jurnallarını, təşkilat miqyaslı rol / superadmin hamısını (qrupsuz intensiv kurs daxil);
* yalnız AKTİV CARİ dövr (``guest_roster.period_allows_roster`` ilə eyni meyar), bağlanmış jurnal və səviyyə
  qrupunun jurnalı (siyahısı səviyyə idarəetməsindən dəyişir) çıxarılır;
* axtarış — qrup, fənn (ad / kod), müəllim (dözümlü).

Endpoint-in özü yenə hər şeyi yoxlayır (404 / 409); bu siyahı yalnız rahatlıqdır.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q
from django.utils.translation import pgettext

from core.search_text import tolerant_q

from . import guest_roster
from .exam_eligibility import _LOCKED_STATUSES
from .models import CourseFormat, CourseOffering, LanguageLevelCohort

CTX = "registrar.subgroup_students"
_SEARCH_FIELDS = (
    "subject__name",
    "subject__code",
    "group__name",
    "instructor__first_name",
    "instructor__last_name",
    "instructor__username",
)


def can_add(user, organization) -> bool:
    """Aktor ümumiyyətlə alt qrupdan əlavə edə bilərmi (``journal.roster`` struktur əhatəsi)."""
    return organization is not None and guest_roster.can_manage_roster(user, organization)


def journal_queryset(user, organization, query=""):
    """Seçilə bilən hədəf jurnallar (sıralı)."""
    if not can_add(user, organization):
        return CourseOffering.objects.none()
    queryset = CourseOffering.objects.filter(
        organization=organization, period__is_current=True, period__is_active=True
    ).exclude(Q(assessment_scheme__is_published=True) | Q(assessment_scheme__approval_status__in=_LOCKED_STATUSES))
    queryset = queryset.exclude(
        Exists(LanguageLevelCohort.objects.filter(organization=organization, offering_id=OuterRef("pk")))
    )
    # ``unit_in_scope(..., None)`` yalnız superadmin / təşkilat miqyaslı əhatədə doğrudur.
    if not guest_roster.unit_in_scope(user, organization, None):
        groups = guest_roster.scoped_group_queryset(user, organization)
        queryset = queryset.filter(group_id__in=groups.values("pk"))
    condition = tolerant_q(query, _SEARCH_FIELDS) if query else None
    if condition is not None:
        queryset = queryset.filter(condition)
    return queryset.select_related("subject", "group", "instructor", "period").order_by(
        "group__name", "subject__name", "pk"
    )


def journal_label(offering) -> str:
    """«G1 · Fizika (FIZ101) · Müəllim» — qrupsuz intensiv kursda «İntensiv kurs»."""
    if offering.group is not None:
        target = offering.group.name
    elif offering.course_format == CourseFormat.INTENSIVE:
        target = pgettext(CTX, "İntensiv kurs")
    else:
        target = "—"
    subject = f"{offering.subject.name} ({offering.subject.code})" if offering.subject.code else offering.subject.name
    teacher = ""
    if offering.instructor is not None:
        teacher = (offering.instructor.get_full_name() or "").strip() or offering.instructor.get_username()
    return " · ".join(part for part in (target, subject, teacher) if part)


def search(user, organization, query="", *, offset=0, limit=20) -> tuple[list, bool]:
    """``EMSSearchableSelect`` müqaviləsi: ``([{id, text}], has_more)``."""
    window = list(journal_queryset(user, organization, query)[offset : offset + limit + 1])
    results = [{"id": str(item.pk), "text": journal_label(item)} for item in window[:limit]]
    return results, len(window) > limit


__all__ = ["can_add", "journal_label", "journal_queryset", "search"]
