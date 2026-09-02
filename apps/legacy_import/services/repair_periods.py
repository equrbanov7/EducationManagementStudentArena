"""P0-3 təmiri: tenant-ın CARİ akademik dövrü (``AcademicPeriod.is_current``).

Qüsur (2026-09-02 auditi).  Hədəfdə ``is_current=True`` olan HEÇ BİR dövr yoxdur
və bugünkü tarixi əhatə edən dövr də yoxdur (ən son dövr 2026-08-31-də bitir).
Ölçülmüş UI təsiri: tələbənin «Fənlərim» bölməsi
``build_student_subjects_context`` içində ``is_current=True`` axtarır, tapmayanda
``-start_date`` üzrə sonuncuya düşür — o isə 2025/2026 **Yay**-dır (mənbədə
``semestr_jurnal.id=13`` məhz odur), yəni demək olar boş semestr.

Niyə faza bunu YAZMIR.  ``journal_periods`` (V9) qəsdən heç bir dövrü cari elan
etmir: cari dövr **tenant-ın öz təqvim qərarıdır**, mənbə bayrağı isə köçürmə
anındakı vəziyyəti göstərir və bir gün sonra köhnəlir.  Legacy bayraq itmir —
``legacy_journal_period_current_flag`` INFO issue-su kimi ledger-dədir və bu
modul onu məhz oradan oxuyur.  Yəni qərar sənədləşdirilmiş şəkildə operatora
verilir, təxminlə yazılmır.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .rehearsal_authorizer import ACADEMIC_PERIOD_MODEL_LABEL as PERIOD_MODEL_LABEL

AUDIT_REASON = "legacy_repair:current_period"
PERIOD_ENTITY_TYPE = "academic_period"
CURRENT_FLAG_RULE = "legacy_journal_period_current_flag"

#: ``rehearsal_journal_periods_phase._SEASONS`` ilə EYNİ pəncərələr — yeni il
#: yaradılanda dövr sərhədləri köçürülmüş dövrlərlə eyni resepti izləyir.
SEASONS = (
    ("Payız", (9, 15), (1, 31), 0, 1),
    ("Yaz", (2, 1), (6, 30), 1, 1),
    ("Yay", (7, 1), (8, 31), 1, 1),
)


@dataclass(frozen=True)
class PeriodRow:
    period: object
    offerings: int
    enrollments: int
    legacy_current: bool

    def as_row(self):
        period = self.period
        return (
            str(period.pk)[:8],
            period.academic_year,
            period.name,
            period.start_date,
            period.end_date,
            "BƏLİ" if period.is_current else "",
            "BƏLİ" if self.legacy_current else "",
            self.offerings,
            self.enrollments,
        )


TABLE_HEADERS = ("id", "il", "fəsil", "başlanğıc", "son", "cari", "legacy cari", "açılış", "yazılış")


def legacy_current_period_pks(organization) -> set[str]:
    """Mənbədə ``is_current='1'`` olan semestrlərin HƏDƏF açarları (ledger-dən)."""

    legacy_pks = set(
        LegacyMigrationIssue.objects.filter(
            organization=organization, entity_type=PERIOD_ENTITY_TYPE, rule_code=CURRENT_FLAG_RULE
        ).values_list("legacy_pk", flat=True)
    )
    if not legacy_pks:
        return set()
    return {
        str(target_pk)
        for target_pk in LegacyEntityMap.objects.filter(
            organization=organization,
            entity_type=PERIOD_ENTITY_TYPE,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label=PERIOD_MODEL_LABEL,
            legacy_pk__in=sorted(legacy_pks),
        ).values_list("target_pk", flat=True)
    }


def period_rows(organization) -> list[PeriodRow]:
    """Bütün dövrlər + hər birinin yükü (açılış/yazılış) — qərar üçün sübut."""

    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    legacy_current = legacy_current_period_pks(organization)
    periods = list(period_model.objects.filter(organization=organization).order_by("start_date", "name"))
    # Sadə, deterministik sayım (iki qısa sorğu — annotate/GROUP BY tələsi yoxdur).
    offerings: dict[str, int] = {}
    for period_id in offering_model.objects.filter(organization=organization).values_list("period_id", flat=True):
        offerings[str(period_id)] = offerings.get(str(period_id), 0) + 1
    enrollments: dict[str, int] = {}
    for period_id in enrollment_model.objects.filter(organization=organization).values_list(
        "offering__period_id", flat=True
    ):
        enrollments[str(period_id)] = enrollments.get(str(period_id), 0) + 1
    return [
        PeriodRow(
            period=period,
            offerings=offerings.get(str(period.pk), 0),
            enrollments=enrollments.get(str(period.pk), 0),
            legacy_current=str(period.pk) in legacy_current,
        )
        for period in periods
    ]


def containing_period(rows: list[PeriodRow], today: datetime.date):
    return next((row.period for row in rows if row.period.start_date <= today <= row.period.end_date), None)


def select_period(rows: list[PeriodRow], *, selector: str, today: datetime.date):
    """Hansı dövr cari olmalıdır → (dövr, səbəb).  Heç nə yazmır."""

    selector = str(selector or "").strip()
    if selector:
        for row in rows:
            period = row.period
            if selector in (str(period.pk), f"{period.academic_year} {period.name}", period.name):
                return period, "explicit_selector"
        return None, "selector_not_found"
    inside = containing_period(rows, today)
    if inside is not None:
        return inside, "contains_today"
    legacy = next((row.period for row in rows if row.legacy_current), None)
    if legacy is not None:
        return legacy, "legacy_is_current_flag"
    return (rows[-1].period if rows else None), "latest_period" if rows else "no_periods"


def create_year(organization, academic_year: str) -> list:
    """``2026/2027`` üçün üç fəsli yarat (varsa toxunma) — cari elan ETMİR."""

    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    from core.constants import AcademicPeriodType

    start_year = int(str(academic_year).strip()[:4])
    created = []
    for name, start_md, end_md, start_shift, end_shift in SEASONS:
        period, was_created = period_model.objects.get_or_create(
            organization=organization,
            name=name,
            academic_year=f"{start_year}/{start_year + 1}",
            defaults={
                "period_type": AcademicPeriodType.SEMESTER,
                "start_date": datetime.date(start_year + start_shift, *start_md),
                "end_date": datetime.date(start_year + end_shift, *end_md),
                "is_current": False,
                "is_active": True,
            },
        )
        if was_created:
            created.append(period)
    return created


def set_current(organization, period, *, actor) -> bool:
    """``is_current`` bayrağını qoy; model özü digərlərini söndürür.  İdempotent."""

    from apps.audit.public import log_action
    from core.constants import AuditAction

    if period.is_current:
        return False
    previous = list(
        django_apps.get_model("organizations", "AcademicPeriod")
        .objects.filter(organization=organization, is_current=True)
        .values_list("name", "academic_year")
    )
    period.is_current = True
    period.save(update_fields=["is_current"])
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=period,
        old_values={"is_current": [f"{name} {year}" for name, year in previous]},
        new_values={"is_current": f"{period.name} {period.academic_year}"},
        reason=AUDIT_REASON,
    )
    return True


def today() -> datetime.date:
    return timezone.localdate()


__all__ = [
    "AUDIT_REASON",
    "CURRENT_FLAG_RULE",
    "PeriodRow",
    "TABLE_HEADERS",
    "containing_period",
    "create_year",
    "legacy_current_period_pks",
    "period_rows",
    "select_period",
    "set_current",
    "today",
]
