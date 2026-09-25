"""Kabinetin «Ana səhifə»si (dashboard) üçün registrar məlumatı — TOPLU, oxu-yalnız.

NİYƏ AYRI MODUL (2026-09-25, sahibin şikayəti: «davamiyyət nəyin davamiyyətidir,
hansı fənnin qayıbı — heç aydın deyil»)?  Ana səhifə əvvəl rəqəmləri özü yığırdı:
bütün fənlərin qayıb saatlarını CƏMLƏYİB proqramın xam limitini («25%») yanına
yazırdı, «son qiymətlər»də köhnə semestrlərin arxiv komponentlərini göstərirdi,
dövrü isə yalnız ``is_current`` bayrağından götürürdü (2026-09-25-də başlıqda
«2025/2026 · Yaz semestri» görünürdü).  Qaydalar registrar-dadır — ana səhifə
onları TƏKRAR YAZMAMALIDIR, ona görə hesablama buraya, qaydaların yanına köçdü:

* **Dövr** — :func:`current_period`: TARİXƏ düşən dövr → yaxın gələcək dövr →
  bayraqlı (``is_current``) → ən son başlayan.  Bütün vidjetlər EYNİ dövrü alır.
* **Fənn sətirləri** — :func:`student_subjects`: ``gradebook.get_student_journal_summary``-nin
  güzgüsüdür (eyni yazılış dəsti, eyni ``entry_score_for``, eyni
  ``exam_eligibility.resolve``, eyni ``absence_limit`` həddi), fərq yalnız
  TOPLU oxumadadır: xülasə hər yazılış üçün komponent balı / sərbəst iş
  sayğacını ayrıca sorğulayır (fənn başına 1–3 sorğu), burada isə
  :func:`finals_batch.entry_batch` hamısını sabit sayda oxuyur.  Bərabərlik
  ``apps/accounts/tests/test_dashboard_student_teacher.py``-də yoxlanılır.
* **Dərs günləri** — :func:`lessons_on` / :func:`next_lesson_day`: həftəlik slot
  siyahısından konkret TARİXİN dərsləri (üst/alt həftə pariteti
  ``schedule.week_parity``-dən, dövrün tarix sərhədləri daxil).  «Növbəti dərs
  günü» cari həftə ilə məhdud DEYİL — cümə günü bazar ertəsini tapır.
* **Müəllim jurnalları** — :func:`teacher_offerings`: açılışlar + tələbə sayı +
  keçirilmiş saat (alt-sorğu annotasiyaları), açılış sayından asılı olmayan TƏK sorğu.
* **Aralıq qiymətləndirmə pəncərələri** — :func:`interim_windows`: rejim
  (:mod:`interim_assessment` — 2026/2027-dən TƏK Midterm, əvvəl K1–K3) +
  İmtahan Mərkəzinin pəncərələri, bir sorğu.
* **İdarəetmə sayğacları** — jurnal düzəlişləri, bağlama bildirişləri, aktiv
  tələbə sayı: ana səhifə modullarında ``apps.registrar.models``-ə birbaşa
  import qalmasın (``scripts/context_map.py`` ratchet-i).

Heç bir funksiya YAZMIR (komponent yaratmır, sxem ``get_or_create`` etmir).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.registrar import absence_limit, exam_eligibility, finals_batch, gradebook, interim_assessment, schedule
from apps.registrar.models import (
    ComponentKind,
    CourseOffering,
    Enrollment,
    JournalCloseNotice,
    JournalCorrection,
    KollokviumWindow,
    Lesson,
    StudentAcademicRecord,
    WeekType,
)

#: «Növbəti dərs günü» axtarışının üfüqü — iki həftə hər iki pariteti (üst/alt) örtür.
NEXT_DAY_HORIZON_DAYS = 14

#: Buraxılış statuslarının «risk» sırası — təhlükəli fənn siyahının başında.
STATUS_RISK_ORDER = {"barred": 0, "near": 1, "unknown": 2, "ok": 3, "frozen": 4}


# --------------------------------------------------------------------------- #
# Dövr
# --------------------------------------------------------------------------- #


def pick_current_period(periods, *, today):
    """Dövr siyahısından «indiki» dövrü seç (sorğusuz — test üçün ayrıca).

    Sıra: (1) TARİXƏ düşən dövr (bir neçəsi varsa bayraqlı, sonra ən gec
    başlayan); (2) aralıqda (tətil) — ən yaxın GƏLƏCƏK dövr: köhnəlmiş bayraq
    bitmiş semestri göstərməsin (sahibin 2026-09-25 ekranı); (3) ``is_current``
    bayrağı; (4) ən son başlayan dövr.
    """
    periods = [p for p in periods if p is not None]
    if not periods:
        return None
    containing = [p for p in periods if p.start_date <= today <= p.end_date]
    if containing:
        return max(containing, key=lambda p: (bool(p.is_current), p.start_date))
    upcoming = [p for p in periods if p.start_date > today]
    if upcoming:
        return min(upcoming, key=lambda p: p.start_date)
    flagged = [p for p in periods if p.is_current]
    if flagged:
        return max(flagged, key=lambda p: p.start_date)
    return max(periods, key=lambda p: p.start_date)


def current_period(organization, *, today=None):
    """Ana səhifənin dövrü — tarixə əsaslanan seçim, TƏK sorğu."""
    if organization is None:
        return None
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    periods = list(AcademicPeriod.objects.filter(organization=organization))
    return pick_current_period(periods, today=today or timezone.localdate())


def period_contains(period, day) -> bool:
    return period is not None and period.start_date <= day <= period.end_date


# --------------------------------------------------------------------------- #
# Tələbə
# --------------------------------------------------------------------------- #


def student_record(organization, user):
    """Tələbənin AKTİV akademik qeydi — deterministik (ilk pk, ``absence_limit`` ilə eyni qayda)."""
    if organization is None or user is None:
        return None
    return (
        StudentAcademicRecord.objects.filter(organization=organization, student=user, is_active=True)
        .select_related("program", "group")
        .order_by("pk")
        .first()
    )


def _interim_items(spec, components, scores) -> list:
    """Aralıq qiymətləndirmənin görünən xanaları — midterm: 1, kollokvium: K1–K3.

    Midterm rejimində yalnız «Midterm» adlı KOLLOKVIUM komponenti götürülür
    (``interim_components.display_components`` ilə eyni ad qaydası); köhnə kodun
    qoyduğu «Kollokvium N» qalıqları ana səhifədə göstərilmir — onların balı
    (varsa) onsuz da giriş balının içindədir.  Komponent hələ yaradılmayıbsa
    (müəllim jurnalı açmayıb) xana boş, tavan rejimdən gəlir.
    """
    interim = sorted((c for c in components if c.kind == ComponentKind.KOLLOKVIUM), key=lambda c: (c.order, c.name))
    if spec.is_midterm:
        key = interim_assessment.MIDTERM_COMPONENT_NAME.lower()
        primary = next((c for c in interim if c.name.strip().lower() == key), None)
        return [
            {
                "label": spec.label_for(0),
                "score": scores.get(primary.id) if primary is not None else None,
                "max": int(primary.max_score) if primary is not None else spec.max_score,
            }
        ]
    items = []
    for index in range(spec.count):
        component = interim[index] if index < len(interim) else None
        items.append(
            {
                "label": spec.label_for(index),
                "score": scores.get(component.id) if component is not None else None,
                "max": int(component.max_score) if component is not None else spec.max_score,
            }
        )
    return items


def _risk_key(row):
    allowed = row["allowed_hours"]
    used = (row["absence_hours"] / allowed) if allowed > 0 else Decimal("0")
    return (STATUS_RISK_ORDER.get(row["status"], 9), -used, row["subject_name"].lower())


def student_subjects(*, organization, record, period) -> dict:
    """Cari dövrün fənləri — davamiyyət + giriş balı + aralıq qiymətləndirmə (toplu).

    Qaytarır::

        {"limit_percent": int, "exempt": bool, "spec": InterimSpec,
         "rows": [{enrollment_id, offering_id, subject_name, absence_hours,
                   lesson_hours, allowed_hours, status, eligibility,
                   entry_score, entry_max, interim: [{label, score, max}]}]}

    ``rows`` RİSK sırasındadır (buraxılmayan → limitə yaxın → …).  Sorğu sayı
    fənn sayından ASILI DEYİL: yazılışlar (1) + komponentlər/ballar/sərbəst
    iş/dərs balları (``finals_batch.entry_batch``, ≤4) + donma (1–2) + məxrəc
    (yalnız ``lesson_hours`` boş olan açılış varsa, 1).
    """
    from apps.registrar.student_subjects_context import eligibility_status

    limit_percent = absence_limit.limit_percent_for_record(record)
    result = {
        "limit_percent": limit_percent,
        "exempt": bool(getattr(record, "national_athlete_exemption", False)),
        "spec": interim_assessment.spec_for_period(period, organization),
        "rows": [],
    }
    if record is None or period is None:
        return result
    enrollments = list(
        Enrollment.objects.filter(
            organization_id=record.organization_id, student_id=record.student_id, offering__period=period
        )
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering__subject", "offering__assessment_scheme")
        .order_by("offering__subject__name", "pk")
    )
    if not enrollments:
        return result
    offerings = {e.offering_id: e.offering for e in enrollments}
    # Məxrəc fallback-i (dərs saatlarının cəmi) YALNIZ `lesson_hours` təyin olunmayan açılışlar üçün.
    missing = [oid for oid, o in offerings.items() if not (o.lesson_hours or 0) > 0]
    hours_map = exam_eligibility.lesson_hours_map(missing) if missing else {}
    # Giriş balı (Midterm rejimində sillabus standartı) — davamiyyəti buraxılışla EYNİ saat/hədd.
    batch = finals_batch.student_entry_batch(enrollments, record, period, None, hours_map, organization)
    frozen = exam_eligibility.frozen_offering_ids(list(offerings))
    rows = []
    for enrollment in enrollments:
        offering = enrollment.offering
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        kwargs = batch.entry_kwargs(enrollment)
        entry = gradebook.entry_score_for(enrollment, cap, **kwargs)
        lesson_hours = exam_eligibility.lesson_hours_for(offering, hours_map=hours_map)
        allowed = Decimal(lesson_hours) * Decimal(limit_percent) / Decimal(100)
        eligibility = exam_eligibility.resolve(
            absence_hours=enrollment.absence_hours or 0,
            lesson_hours=lesson_hours,
            allowed_hours=allowed,
            limit_percent=limit_percent,
            exempt=result["exempt"],
            frozen=offering.id in frozen,
        )
        scores = {cs.component_id: cs.score for cs in kwargs["component_scores"]}
        rows.append(
            {
                "enrollment_id": enrollment.id,
                "offering_id": offering.id,
                "subject_name": getattr(offering.subject, "name", "") or "—",
                "absence_hours": Decimal(enrollment.absence_hours or 0),
                "lesson_hours": Decimal(lesson_hours),
                "allowed_hours": allowed,
                "status": eligibility_status(eligibility),
                "eligibility": eligibility,
                "entry_score": entry,
                "entry_max": int(cap),
                "interim": _interim_items(result["spec"], kwargs["components"], scores),
            }
        )
    result["rows"] = sorted(rows, key=_risk_key)
    return result


# --------------------------------------------------------------------------- #
# Dərs günləri (cədvəl slotları — əlavə sorğusuz)
# --------------------------------------------------------------------------- #


def _monday(day):
    return day - datetime.timedelta(days=day.weekday())


def lessons_on(slots, day, *, period) -> list:
    """Verilmiş TARİXDƏ keçiriləcək slotlar (həftə günü + üst/alt pariteti + dövr sərhədi).

    ``all`` (və ya naməlum) tipli slot hər həftə keçir, ``odd``/``even`` yalnız
    öz paritetində — köhnə ``todays_slots`` qaydası ilə eyni.
    """
    if not slots or day is None:
        return []
    if period is not None and not period_contains(period, day):
        return []
    weekday = day.isoweekday()
    parity = schedule.week_parity(period, _monday(day))
    picked = [
        slot
        for slot in slots
        if slot.weekday == weekday
        and not (slot.week_type in (WeekType.ODD, WeekType.EVEN) and slot.week_type != parity)
    ]
    return sorted(picked, key=lambda slot: (slot.start_time, slot.end_time))


def next_lesson_day(slots, *, period, today, horizon_days=NEXT_DAY_HORIZON_DAYS):
    """Bu gündən SONRAKI ilk dərsli gün → ``(tarix, slotlar)`` və ya ``(None, [])``.

    Həftə sonunu keçir (cümə → bazar ertəsi), pariteti hər həftə üçün ayrıca
    hesablayır, dövr hələ başlamayıbsa onun ilk günündən axtarır və dövr
    bitəndən sonrakı tarixi qaytarmır.
    """
    if not slots:
        return None, []
    start = today + datetime.timedelta(days=1)
    if period is not None and period.start_date > start:
        start = period.start_date
    for offset in range(horizon_days):
        day = start + datetime.timedelta(days=offset)
        if period is not None and day > period.end_date:
            break
        picked = lessons_on(slots, day, period=period)
        if picked:
            return day, picked
    return None, []


def week_lesson_count(slots, *, period, today) -> int:
    """Cari həftədə (B.e.–Bazar) keçiriləcək dərslərin sayı — üst/alt pariteti nəzərə alınır."""
    monday = _monday(today)
    return sum(len(lessons_on(slots, monday + datetime.timedelta(days=i), period=period)) for i in range(7))


def week_parity(period, today) -> str:
    """Bu günün həftəsi — ``odd`` (üst) / ``even`` (alt)."""
    return schedule.week_parity(period, _monday(today))


# --------------------------------------------------------------------------- #
# Müəllim
# --------------------------------------------------------------------------- #


def _per_offering(queryset, aggregate):
    """Açılış başına aqreqat ALT-SORĞUSU — JOIN-lə sətir çoxalması (Count × Sum) olmadan."""
    return Coalesce(
        Subquery(
            queryset.filter(offering=OuterRef("pk"))
            .order_by()
            .values("offering")
            .annotate(v=aggregate)
            .values("v")[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def teacher_offerings(*, organization, teacher, period, today=None) -> dict:
    """Müəllimin cari dövrdəki jurnalları — TAM say + sətir məlumatı, TƏK sorğu.

    ``held_hours`` — bu günə qədər keçirilmiş dərslərin saat cəmi,
    ``plan_hours`` — açılışın semestr dərs saatı (``lesson_hours``; 0 = təyin
    olunmayıb).  Tələbə sayı jurnal siyahısı ilə eyni qaydadır (yalnız
    ``ENROLLED``).  Sayğaclar alt-sorğu annotasiyasıdır, ona görə açılış sayı
    artanda sorğu sayı artmır.
    """
    result = {"total": 0, "students_total": 0, "rows": []}
    if organization is None or teacher is None or period is None:
        return result
    today = today or timezone.localdate()
    offerings = list(
        CourseOffering.objects.filter(organization=organization, instructor=teacher, period=period, is_active=True)
        .select_related("subject", "group")
        .annotate(
            dash_students=_per_offering(Enrollment.objects.filter(status=Enrollment.Status.ENROLLED), Count("id")),
            dash_held_hours=_per_offering(Lesson.objects.filter(date__lte=today), Sum("hours")),
            dash_lessons=_per_offering(Lesson.objects.filter(date__lte=today), Count("id")),
        )
        .order_by("subject__name", "group__name", "pk")
    )
    rows = [
        {
            "offering_id": offering.id,
            "subject_name": getattr(offering.subject, "name", "") or "—",
            "group_name": getattr(getattr(offering, "group", None), "name", "") or "",
            "students": int(offering.dash_students or 0),
            "held_hours": int(offering.dash_held_hours or 0),
            "lessons_held": int(offering.dash_lessons or 0),
            "plan_hours": int(offering.lesson_hours or 0),
        }
        for offering in offerings
    ]
    result.update(total=len(rows), students_total=sum(row["students"] for row in rows), rows=rows)
    return result


# --------------------------------------------------------------------------- #
# Aralıq qiymətləndirmə (Midterm / K1–K3) pəncərələri
# --------------------------------------------------------------------------- #


def window_status(window, today) -> str:
    """``kollokvium_windows.entry_state`` statusları — açılışa xas uzatma NƏZƏRƏ ALINMADAN.

    Ana səhifə org səviyyəli xülasədir: uzatma (grant) bölməyə bağlıdır və
    açılış ağacını gəzmək tələb edir; onun yerinə ``extended`` bayrağı verilir.
    """
    if window is None:
        return "not_configured"
    if not window.is_active:
        return "inactive"
    if today < window.opens_on:
        return "scheduled"
    if today > window.closes_on:
        return "closed"
    return "open"


def interim_windows(*, organization, period, today=None) -> dict:
    """Dövrün aralıq qiymətləndirmə rejimi + İmtahan Mərkəzi pəncərələri — TƏK sorğu.

    Midterm rejimində yalnız ``k_index=0`` pəncərəsi var (``spec.count == 1``);
    kollokvium rejimində K1–K3.  Qaytarır::

        {"spec": InterimSpec, "open_count": int,
         "windows": [{index, label, status, opens_on, closes_on, extended}]}
    """
    spec = interim_assessment.spec_for_period(period, organization)
    result = {"spec": spec, "open_count": 0, "windows": []}
    if organization is None or period is None:
        return result
    today = today or timezone.localdate()
    rows = {
        row.k_index: row
        for row in KollokviumWindow.objects.filter(organization=organization, period=period).annotate(
            grant_count=Count("extra_grants", filter=Q(extra_grants__extra_days__gt=0))
        )
    }
    for index in range(spec.count):
        window = rows.get(index)
        status = window_status(window, today)
        result["windows"].append(
            {
                "index": index,
                "label": spec.label_for(index),
                "status": status,
                "opens_on": getattr(window, "opens_on", None),
                "closes_on": getattr(window, "closes_on", None),
                "extended": bool(window is not None and getattr(window, "grant_count", 0)),
            }
        )
    result["open_count"] = sum(1 for item in result["windows"] if item["status"] == "open")
    return result


# --------------------------------------------------------------------------- #
# İdarəetmə sayğacları (ana səhifənin yeganə jurnal/reyestr model oxumaları)
# --------------------------------------------------------------------------- #


def correction_counts(organization, *, today=None) -> dict:
    """Bu gün / bu həftə (B.e.-dən) edilmiş auditli jurnal düzəlişləri — TƏK aqreqat sorğu."""
    today = today or timezone.localdate()
    week_start = _monday(today)
    totals = JournalCorrection.objects.filter(organization=organization).aggregate(
        today_count=Count("id", filter=Q(created_at__date=today)),
        week_count=Count("id", filter=Q(created_at__date__gte=week_start)),
    )
    return {"today": int(totals.get("today_count") or 0), "week": int(totals.get("week_count") or 0)}


def active_close_notices(organization):
    """Aktiv jurnal bağlama bildirişləri (queryset — çağıran dilimləyib sayır)."""
    return JournalCloseNotice.objects.filter(organization=organization, is_active=True).order_by("closes_on", "pk")


def active_student_count(organization) -> int:
    """Təşkilatın aktiv akademik qeydlərinin sayı (rektorluq KPI-ı)."""
    return StudentAcademicRecord.objects.filter(organization=organization, is_active=True).count()


__all__ = [
    "NEXT_DAY_HORIZON_DAYS",
    "STATUS_RISK_ORDER",
    "active_close_notices",
    "active_student_count",
    "correction_counts",
    "current_period",
    "interim_windows",
    "lessons_on",
    "next_lesson_day",
    "period_contains",
    "pick_current_period",
    "student_record",
    "student_subjects",
    "teacher_offerings",
    "week_lesson_count",
    "week_parity",
    "window_status",
]
