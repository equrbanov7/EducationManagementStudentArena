"""Tələbənin real «təhsil vəziyyəti» + hesab aktivləşdirməsi — reyestr üçün (sahib 2026-10-02).

Problem. Köçürmədə bütün ``StudentAcademicRecord``-lar ``enrolled`` qaldı (köhnə sistem məzunla xaric
olunanı ayırmırdı — bax ``legacy_import/services/rehearsal_sar_archive.py``), ona görə reyestr HAMINI
«Aktiv» göstərirdi: prod-da 2416 arxiv (məzun/xaric) hesab və oxu müddəti çoxdan bitmiş ~1500 «aktiv»
tələbə daxil.

Həll — rəsmi statusu DƏYİŞMƏDƏN, SQL-də hesablanan vəziyyət (filtr / KPI / badge bir sorğuda):

* rəsmi status ``graduated`` / ``expelled`` / ``academic_leave`` → olduğu kimi;
* hesab arxivdədir (``access_state=archived``: köhnə sistemdə «azad edilib») → ``archived`` (məzun və ya xaric);
* qəbul ili köçürmə sentinelidir (1950) → ``year_unknown``;
* qəbul ili + proqramın müddəti (ECTS/60 il) ≤ cari tədris ilinin başlanğıcı → ``period_ended``
  (oxu müddəti bitib — çox güman məzundur, rəsmiləşdirilməlidir);
* qalan hamı → ``studying`` (həqiqətən oxuyur).

Hesab aktivləşdirməsi (``account_state``): öz parolunu qurub + e-poçtu təsdiqli → ``activated``; hələ
ilkin paroldadır → ``initial``; qalan (məs. arxiv) → ``other``.
"""

from __future__ import annotations

from django.db.models import Case, CharField, Count, ExpressionWrapper, F, IntegerField, Q, Value, When
from django.utils import timezone

#: Köçürmənin «qəbul ili bilinmir» sentineli (``legacy_import`` ARCHIVE_FALLBACK_ADMISSION_YEAR ilə EYNİ;
#: tətbiqlər arası private import olmasın deyə təkrarlanır).
UNKNOWN_ADMISSION_YEAR = 1950

#: Reyestr filtri / KPI sırası.
STUDY_STATES = ("studying", "period_ended", "year_unknown", "archived", "academic_leave", "expelled", "graduated")
ACCOUNT_STATES = ("activated", "initial")
_OFFICIAL = ("graduated", "expelled", "academic_leave")


def current_academic_year_start(now=None) -> int:
    """Tədris ili sentyabrda başlayır: 2026-10 → 2026, 2027-03 → 2026."""
    now = now or timezone.localtime()
    return now.year if now.month >= 9 else now.year - 1


def annotate_study_state(records, *, now=None):
    """``StudentAcademicRecord`` querysetinə ``study_state`` və ``account_state`` əlavə edir."""
    year_start = current_academic_year_start(now)
    ects = Case(When(program__ects_total__gt=0, then=F("program__ects_total")), default=Value(240))
    # Tam ədəd bölməsi: (240 + 59) / 60 = 4 il, (120 + 59) / 60 = 2 il.
    records = records.annotate(
        study_end_year=ExpressionWrapper(F("admission_year") + (ects + 59) / 60, output_field=IntegerField())
    )
    return records.annotate(
        study_state=Case(
            When(status__in=_OFFICIAL, then=F("status")),
            When(student__profile__access_state="archived", then=Value("archived")),
            When(admission_year=UNKNOWN_ADMISSION_YEAR, then=Value("year_unknown")),
            When(study_end_year__lte=year_start, then=Value("period_ended")),
            default=Value("studying"),
            output_field=CharField(),
        ),
        account_state=Case(
            When(student__profile__password_change_required=True, then=Value("initial")),
            When(student__profile__email_verified=True, then=Value("activated")),
            default=Value("other"),
            output_field=CharField(),
        ),
    )


def study_state_counts(records) -> dict:
    """Annotasiya olunmuş querysetdən vəziyyət + aktivləşdirmə sayları (BİR aqreqat sorğusu)."""
    aggregates = {f"state_{key}": Count("id", filter=Q(study_state=key)) for key in STUDY_STATES}
    aggregates.update({f"account_{key}": Count("id", filter=Q(account_state=key)) for key in ACCOUNT_STATES})
    totals = records.aggregate(**aggregates)
    return {key: value or 0 for key, value in totals.items()}


__all__ = [
    "ACCOUNT_STATES",
    "STUDY_STATES",
    "UNKNOWN_ADMISSION_YEAR",
    "annotate_study_state",
    "current_academic_year_start",
    "study_state_counts",
]
