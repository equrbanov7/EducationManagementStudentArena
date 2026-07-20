"""Transkript + GPA (U5) — read-only aggregation over the final results.

A transcript groups a student's enrollments by academic period (semester) and,
for each, reuses :func:`finals.compute_final_result` to get the letter grade +
GPA point. The cumulative GPA is **credit-weighted** (Boloniya/ECTS), matching
the official AZ university "ÜOMG" (Ümumi Orta Qiymət Göstəricisi):

    ÜOMG = Σ(gpa_point × credit) / Σ(credit)   over courses with a definite result

A course counts toward the GPA once its result is definite (``passed`` or
``failed`` — a bar counts as a failed attempt); a still-ungraded course is "in
progress" and excluded until it has an exam/resit score. Earned credits are the
credits of *passed* courses only. This layer is additive and pure-read — it adds
no models and never writes.

On top of the flat per-semester grouping (``semesters``, kept for backward
compatibility), the semesters are also folded into ``years`` — one bucket per
academic year (e.g. "2024-2025") holding its semesters (Payız / Yaz / Yay, in
chronological order) plus a year-level credit-weighted ÜOMG — so the official
"AKADEMİK TRANSKRİPT" layout (UNEC-style: one row of academic-year blocks, two
semester columns each) can be rendered directly off the returned structure.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from apps.registrar import finals
from apps.registrar.models import Enrollment

_TWO_PLACES = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _credit_for(offering) -> int:
    """ECTS credit of the offering's subject (0 if somehow unset)."""
    return int(getattr(offering.subject, "ects", 0) or 0)


def _grade_point(result) -> Decimal:
    return Decimal(str(result.get("gpa") or "0"))


def _build_row(enrollment, organization=None):
    offering = enrollment.offering
    result = finals.compute_final_result(enrollment=enrollment, organization=organization)
    credit = _credit_for(offering)
    # Definite outcome → contributes to GPA; still-open course is excluded.
    in_gpa = bool(result["passed"] or result["failed"])
    return {
        "enrollment": enrollment,
        "offering": offering,
        "subject": offering.subject,
        "period": offering.period,
        "credit": credit,
        "result": result,
        "in_gpa": in_gpa,
        "quality_points": _grade_point(result) * credit if in_gpa else Decimal("0"),
    }


def _summarize(rows) -> dict:
    """Kredit-çəkili ÜOMG (100 bal) + kredit yekunları.

    AZ kredit sistemi (UNEC/AMU əsasnamələri): ÜOMG **100 bal** üzərindən hesablanır —

        ÜOMG = Σ(yekun_bal × kredit) / Σ(kredit)

    burada ``yekun_bal`` fənnin 100-lük yekun balıdır (``result["total"]``), cəm isə
    qəti nəticəli (keçmiş VƏ ya kəsilmiş) fənlər üzrədir — kəsilmiş fənn aşağı balı
    ilə ÜOMG-ni azaldır. Qazanılmış kredit yalnız KEÇİLMİŞ fənlərdir. (4.0-lıq GPA
    nöqtəsi ``finals.score_to_letter``-də hərf üçün qalır, amma ÜOMG artıq ondan
    asılı deyil.)"""
    gpa_credits = sum((r["credit"] for r in rows if r["in_gpa"]), 0)
    score_points = sum(
        (Decimal(str(r["result"]["total"])) * r["credit"] for r in rows if r["in_gpa"]),
        Decimal("0"),
    )
    earned_credits = sum((r["credit"] for r in rows if r["result"]["passed"]), 0)
    uomg = _round2(score_points / gpa_credits) if gpa_credits else Decimal("0.00")
    return {
        "gpa": uomg,  # geriyə-uyğunluq: bütün "ÜOMG" göstəriciləri bu dəyəri oxuyur (indi 100 bal)
        "uomg": uomg,  # ÜOMG (100 bal) — açıq ad
        "quality_points": _round2(score_points),
        "credits_gpa": gpa_credits,
        "credits_earned": earned_credits,
    }


def _season_of(period) -> str:
    """Semestrin fəsil adı (Payız/Yaz/Yay) — başlanğıc ayından (page_contexts-in
    ``_season_label`` ilə eyni qayda, qısa forma: "semestri" şəkilçisiz, çünki
    rəsmi transkriptdə fəsil adı sütun/başlıq kimi tək başına göstərilir)."""
    start_date = getattr(period, "start_date", None)
    month = start_date.month if start_date else 9
    if month >= 8 or month == 12:
        return "Payız"
    if month <= 5:
        return "Yaz"
    return "Yay"


def _year_label(period) -> str:
    """Rəsmi transkript başlığı üçün "2024-2025" formatı (year_display-in
    defis-li variantı — UNEC nümunəsində "Akademik il 2025-2026" kimi göstərilir)."""
    return (getattr(period, "year_display", "") or "").replace("/", "-")


def _group_by_year(semesters: list[dict]) -> list[dict]:
    """Fold the chronological semester list into one bucket per academic year
    (each already carrying its ``season``/``year_key`` from the caller), with a
    year-level credit-weighted ÜOMG computed over all of that year's rows."""
    years: list[dict] = []
    by_year: dict = {}
    for bucket in semesters:
        year_key = bucket["year_key"]
        year_bucket = by_year.get(year_key)
        if year_bucket is None:
            year_bucket = {"year_key": year_key, "year_label": bucket["year_label"], "semesters": []}
            by_year[year_key] = year_bucket
            years.append(year_bucket)
        year_bucket["semesters"].append(bucket)

    for year_bucket in years:
        year_rows = [row for sem in year_bucket["semesters"] for row in sem["rows"]]
        year_bucket.update(_summarize(year_rows))
    return years


def build_student_transcript(*, student, organization, program=None):
    """Full transcript for one student: chronological semesters + cumulative GPA.

    Only the requesting student's own enrollments are read; tenant isolation is
    inherited from the active request (RLS). Returns ``has_record=False`` when the
    student has no enrollments yet so the cabinet renders a friendly placeholder.
    """
    enrollments = list(
        Enrollment.objects.filter(organization=organization, student=student)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related(
            "offering",
            "offering__subject",
            "offering__period",
            "offering__assessment_scheme",
            "offering__instructor",
        )
        .order_by("offering__period__start_date", "offering__subject__code")
    )
    if not enrollments:
        return {
            "has_record": False,
            "student": student,
            "semesters": [],
            "years": [],
            "cumulative_gpa": Decimal("0.00"),
            "total_credits_earned": 0,
            "total_credits_gpa": 0,
            "quality_points": Decimal("0.00"),
            "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
        }

    rows = [_build_row(e, organization) for e in enrollments]

    # Group into semesters, preserving the chronological (period) order.
    semesters: list[dict] = []
    by_period: dict = {}
    for row in rows:
        period = row["period"]
        bucket = by_period.get(period.id)
        if bucket is None:
            bucket = {"period": period, "rows": []}
            by_period[period.id] = bucket
            semesters.append(bucket)
        bucket["rows"].append(row)

    for bucket in semesters:
        bucket.update(_summarize(bucket["rows"]))
        period = bucket["period"]
        bucket["season"] = _season_of(period)
        bucket["year_label"] = _year_label(period)
        bucket["year_key"] = period.year_display

    overall = _summarize(rows)
    return {
        "has_record": True,
        "student": student,
        "semesters": semesters,
        "years": _group_by_year(semesters),
        "cumulative_gpa": overall["gpa"],
        "quality_points": overall["quality_points"],
        "total_credits_gpa": overall["credits_gpa"],
        "total_credits_earned": overall["credits_earned"],
        "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
    }


def _fail_reason_code(result) -> str:
    """Bir KƏSİLMİŞ nəticənin səbəb kodu — iki AYRI hal (q/b ≠ 25%):

    * ``"qb"``     — DAVAMİYYƏTDƏN kəsilib: qayıb dərs saatlarının 25%-ini keçdiyi
      üçün tələbə final imtahanına BURAXILMIR → fənn yenidən keçilməlidir (yenidən
      tədris). ``result["barred"]``.
    * ``"exam25"`` — İMTAHANDAN kəsilib: tələbə final imtahanına GİRİB, amma fənni
      keçə bilməyib → 25% (fənn haqqının 25%-i) ilə bir dəfə təkrar imtahan hüququ.
    * ``"total"``  — nadir/qeyri-müəyyən hal (imtahan qeyd olunmayıb).
    """
    if result["barred"]:
        return "qb"  # davamiyyət 25% saat həddi → imtahana buraxılmayıb
    if result["graded"] and not result["passed"]:
        return "exam25"  # imtahana girib, kəsilib → 25% təkrar imtahan
    return "total"


def build_student_overall_record(*, student, organization):
    """Per-subject academic record for the "Ümumi tədris məlumatı" (overall
    academic record) cabinet section — every subject the student has ever
    taken, flattened + decorated with the teacher name and a fail-reason code,
    grouped by semester (newest first) for client-side search/filtering.

    Pure read; reuses :func:`build_student_transcript`'s enrollment
    aggregation instead of re-querying, so this layer never drifts from the
    transcript's pass/fail/letter logic. Also returns the distinct
    (year, season) option lists the cabinet's filter dropdowns need.
    """
    data = build_student_transcript(student=student, organization=organization)
    if not data["has_record"]:
        return {"has_record": False, "semesters": [], "year_options": [], "season_options": []}

    semesters: list[dict] = []
    year_options: list[str] = []
    season_options: list[str] = []
    for sem in data["semesters"]:
        period = sem["period"]
        year_display = period.year_display
        # Fəsil AYRICA (Payız/Yaz/Yay) — period.name ("2024/2025 Payız semestri")
        # deyil; il artıq qrup başlığındadır, filtr yalnız fəsli süzsün.
        season = sem.get("season") or _season_of(period)
        if year_display not in year_options:
            year_options.append(year_display)
        if season not in season_options:
            season_options.append(season)

        rows = []
        for row in sem["rows"]:
            result = row["result"]
            instructor = getattr(row["offering"], "instructor", None)
            teacher_name = ""
            if instructor is not None:
                teacher_name = (instructor.get_full_name() or "").strip() or instructor.username
            rows.append(
                {
                    "subject": row["subject"],
                    "credit": row["credit"],
                    "teacher_name": teacher_name,
                    "result": result,
                    "in_gpa": row["in_gpa"],
                    "fail_reason": _fail_reason_code(result) if result["failed"] else "",
                }
            )
        semesters.append(
            {
                "period": period,
                "season": season,
                "rows": rows,
                # Semestrdə TOPLANMIŞ kredit (yalnız keçilmiş fənlər) — cədvəldə göstərilir.
                "credits_earned": sem.get("credits_earned", 0),
                "credits_gpa": sem.get("credits_gpa", 0),
                "gpa": sem.get("gpa"),
            }
        )

    # build_student_transcript orders semesters chronologically (ascending);
    # the cabinet wants the newest semester first, like the transcript screenshot.
    semesters.reverse()
    year_options.reverse()
    return {
        "has_record": True,
        "semesters": semesters,
        "year_options": year_options,
        "season_options": season_options,
        # Kumulyativ ÜOMG (100 bal) + kredit — bölmə başlığındakı xülasə üçün.
        "overall_uomg": data["cumulative_gpa"],
        "total_credits_earned": data["total_credits_earned"],
        "total_credits_gpa": data["total_credits_gpa"],
    }
