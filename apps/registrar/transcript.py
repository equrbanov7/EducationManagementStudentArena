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

from django.utils import timezone

from apps.registrar import analytics, exam_eligibility, finals, finals_batch, legacy_grade_read
from apps.registrar.models import Enrollment, StudentAcademicRecord

_TWO_PLACES = Decimal("0.01")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _credit_for(offering) -> int:
    """ECTS credit of the offering's subject (0 if somehow unset)."""
    return int(getattr(offering.subject, "ects", 0) or 0)


def _grade_point(result) -> Decimal:
    return Decimal(str(result.get("gpa") or "0"))


def _build_row(enrollment, organization=None, *, exempt=False, hours_map=None, batch=None):
    offering = enrollment.offering
    result = finals.compute_final_result(
        enrollment=enrollment, organization=organization, exempt=exempt, hours_map=hours_map, batch=batch
    )
    credit = _credit_for(offering)
    # Definite outcome → contributes to GPA; still-open course is excluded.
    in_gpa = bool(result["passed"] or result["failed"])
    return {
        "enrollment": enrollment,
        # Köçürülmüş qiymət nişanının SABİT qoşma açarı (bax
        # ``legacy_grade_read.attach_legacy_provenance``).  Sətri fənn adı ilə
        # uyğunlaşdırmaq həm yanlış nişan, həm IDOR riski yaradardı.
        "enrollment_id": enrollment.id,
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
    # ⚠️ Məxrəc sıfır olduqda ``0.00`` QAYTARILMIR — bax
    # :func:`exam_eligibility.uomg_from`.  Rəsmi transkriptdə sıfır «tələbə sıfır
    # bal aldı» kimi oxunur; halbuki bu, «məlumat yoxdur» halıdır (231 tələbənin
    # BÜTÜN ÜOMG-daşıyan sətirləri köhnə sistemdə nəticəsizdir).
    uomg, available = exam_eligibility.uomg_from(score_points, gpa_credits)
    return {
        "gpa": uomg,  # geriyə-uyğunluq: bütün "ÜOMG" göstəriciləri bu dəyəri oxuyur (indi 100 bal)
        "uomg": uomg,  # ÜOMG (100 bal) — açıq ad; ``None`` = hesablana bilmir
        "uomg_available": available,
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


def student_record_enrollments(*, student, organization):
    """Akademik qeydə DAXİL OLAN qeydiyyatlar — TƏK mənbə.

    Həm ağır transkript aqreqasiyası (``build_student_transcript``), həm də ucuz
    sətir sayğacı (``count_student_record_rows``) məhz bu çoxluqdan çıxır. Beləcə
    kabinetdə göstərilən sətir sayı ilə tab/badge sayğacı heç vaxt ayrılmır —
    "hansı qeydiyyat sayılır?" qaydası tək yerdə yazılıb.
    """
    return Enrollment.objects.filter(organization=organization, student=student).exclude(
        status=Enrollment.Status.DROPPED
    )


def count_student_record_rows(*, student, organization) -> int:
    """``build_student_overall_record``-un qaytaracağı sətir sayı — tək ``COUNT(*)``.

    Ağır hesablamanı (hər qeydiyyat üçün giriş balı + yekun + təkrar imtahan
    sorğuları) işə salmadan sayğacı doldurmaq üçün; sətirlərin ÖZÜ lazım olanda
    ``build_student_overall_record`` çağırılır.
    """
    if organization is None or student is None:
        return 0
    return student_record_enrollments(student=student, organization=organization).count()


def build_student_transcript(*, student, organization, program=None):
    """Full transcript for one student: chronological semesters + cumulative GPA.

    Only the requesting student's own enrollments are read; tenant isolation is
    inherited from the active request (RLS). Returns ``has_record=False`` when the
    student has no enrollments yet so the cabinet renders a friendly placeholder.
    """
    enrollments = list(
        student_record_enrollments(student=student, organization=organization)
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
            # Qeydiyyat yoxdursa ÜOMG də yoxdur — sıfır DEYİL (bax _summarize).
            "cumulative_gpa": None,
            "cumulative_gpa_available": False,
            "total_credits_earned": 0,
            "total_credits_gpa": 0,
            "quality_points": Decimal("0.00"),
            "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
        }

    # İdmançı istisnası tələbə üzrə BİR dəfə oxunur və hər sətrə ötürülür —
    # ``compute_final_result`` onu sətir-sətir sorğulamasın (2026-08-31, 3-cü bloker).
    exempt = bool(
        StudentAcademicRecord.objects.filter(organization=organization, student=student)
        .values_list("national_athlete_exemption", flat=True)
        .first()
    )
    # Məxrəc fallback-ı da tələbə üzrə BİR sorğu (``lesson_hours=0`` olan
    # köçürülmüş açılışlarda sətir-sətir oxumaq N+1 olardı).
    hours_map = exam_eligibility.lesson_hours_map({e.offering_id for e in enrollments})
    # Qalan sətir-sətir oxumalar (komponent balları, sərbəst iş sayğacı,
    # ``FinalGrade``/``ResitRecord``, donma dəsti, qayıb həddi) da BİR dəfə:
    # 59 fənnli real tələbədə ~690 sorğu idi (2026-09-02 ölçməsi).
    batch = finals_batch.build(enrollments)
    rows = [_build_row(e, organization, exempt=exempt, hours_map=hours_map, batch=batch) for e in enrollments]
    # Köçürülmüş qiymət nişanı BURADA qoşulur — transkript ekranı, transkript
    # PDF-i və «Ümumi tədris məlumatı» üçün TƏK mənbə.  Hər səth özü qoşsaydı
    # eyni sətir bir ekranda nişanlı, digərində nişansız görünərdi (məhz bu
    # sürüşmə ``exam_eligibility`` docstring-indəki 2026-08-31 auditinin
    # mövzusudur).  Maliyyəti: tələbə başına bir toplu sorğu dəsti.
    legacy_grade_read.attach_legacy_provenance(rows, organization=organization)

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
        # Köçürülmüş nəticənin OXUNAN qeydi semestr blokunda BİR dəfə çıxır
        # (sətir-sətir yox — ölçmə üçün bax ``LEGACY_SEMESTER_CHECK_NOTICE``).
        bucket.update(legacy_grade_read.semester_notice_flags(bucket["rows"]))
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
        "cumulative_gpa_available": overall["uomg_available"],
        "quality_points": overall["quality_points"],
        "total_credits_gpa": overall["credits_gpa"],
        "total_credits_earned": overall["credits_earned"],
        "ects_total": int(getattr(program, "ects_total", 0) or 0) if program else 0,
    }


def student_credit_totals(*, student, organization, today=None) -> dict:
    """Boloniya kredit yekunu: TOPLANMIŞ (keçilmiş) + hazırda DAVAM EDƏN ECTS.

    Niyə ayrıca funksiya (2026-08-24 QA): «Fənlərim» bölməsindəki ECTS qutusu
    krediti ``Enrollment.status``-dan oxuyurdu — ``COMPLETED`` isə istehsal
    kodunda heç vaxt təyin olunmur (yalnız demo seed yazır), ona görə *hər*
    tələbədə ``earned=0`` çıxırdı, «davam edən» isə tələbənin İNDİYƏ QƏDƏR
    keçdiyi bütün fənlərin cəmi olurdu (köçürülmüş tələbədə 294 kredit «davam
    edir»). Status DƏYİŞDİRİLMİR — o, layihədə həm də yazı/görünmə qapısıdır
    (``gradebook.save_marks``, ``journal_extras`` jurnal/sərbəst-iş siyahıları,
    ``exam_bridge`` yalnız ``ENROLLED`` süzür), tarixi qeydiyyatları
    ``COMPLETED`` etmək imtahan mərkəzinin doldurmalı olduğu köhnə jurnalları
    gizlədər və redaktə olunmaz edərdi. Ona görə kredit
    artıq QİYMƏTLƏRDƏN — transkriptlə EYNİ keçmə qaydası ilə — hesablanır.

    Performans (seçilmiş yol və NİYƏ): sadəcə ``build_student_transcript``
    çağırmaq olardı, amma o, sətir-sətir ``finals.compute_final_result``
    işlədir (fənn başına ~7 sorğu; 59 fənnli real tələbədə 517 sorğu ölçüldü),
    bu funksiya isə tələbə kabinetinin HƏR açılışında işləyir. Ona görə burada
    ``analytics.build_evaluation_maps`` + ``analytics.evaluate_enrollment``
    bulk yolu işlədilir: sabit ~10 sorğu, qeydiyyat sayından asılı deyil.
    Bu, riyaziyyatı TƏKRAR YAZMAQ demək deyil — ``analytics._evaluate``
    ``compute_final_result``-un rəsmi güzgüsüdür və ``test_analytics.py``
    konsistensiya testi ilə ona kilidlənib; üstəlik staff tərəfdəki akademik-
    qeyd icmalı (``apps.accounts.academic_records``) da eyni yolu işlədir.
    Hesablanmış dəyəri saxlamaq (miqrasiya) düşünülmədi: 517 → ~10 sorğu
    onsuz da kifayət qədər ucuzdur, denormallaşma isə yeni sinxronlaşma
    borcu yaradardı (bax hesabat).

    * ``earned``      — KEÇİLMİŞ fənlərin ECTS cəmi (``transcript``-in
      ``total_credits_earned``-i ilə eyni qayda: ``result["passed"]``).
    * ``in_progress`` — «davam edir» hərfi mənada: hələ BİTMƏMİŞ dövrdəki
      (``period.end_date >= bugün``) və hələ keçilməmiş qeydiyyatların ECTS-i.
      Bitmiş semestrdə kəsilmiş fənn nə toplanmışdır, nə də davam edən.
    """
    today = today or timezone.localdate()
    enrollments = list(
        Enrollment.objects.filter(organization=organization, student=student)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("offering", "offering__subject", "offering__period")
    )
    if not enrollments:
        return {"earned": 0, "in_progress": 0}

    maps = analytics.build_evaluation_maps(organization, enrollments)
    earned = 0
    in_progress = 0
    for enrollment in enrollments:
        result = analytics.evaluate_enrollment(enrollment, maps)
        if result["passed"]:
            earned += result["credit"]
            continue
        end_date = getattr(enrollment.offering.period, "end_date", None)
        if end_date is None or end_date >= today:
            in_progress += result["credit"]
    return {"earned": earned, "in_progress": in_progress}


def _fail_reason_code(result) -> str:
    """Bir KƏSİLMİŞ nəticənin səbəb kodu — iki AYRI hal (q/b ≠ 25%):

    * ``"qb"``     — DAVAMİYYƏTDƏN kəsilib: qayıb dərs saatlarının 25%-ini keçdiyi
      üçün tələbə final imtahanına BURAXILMIR → fənn yenidən keçilməlidir (yenidən
      tədris). ``result["barred"]``.
    * ``"exam25"`` — İMTAHANDAN kəsilib: tələbə final imtahanına GİRİB, amma fənni
      keçə bilməyib → 25% (fənn haqqının 25%-i) ilə bir dəfə təkrar imtahan hüququ.
    * ``"total"``  — nadir/qeyri-müəyyən hal (imtahan qeyd olunmayıb).
    """
    return exam_eligibility.fail_reason_code(result)


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
                    # Legacy qiymət sübutları bu stabil FK ilə bulk şəkildə
                    # qoşulur; tələbə/tenant sərhədini subject adı ilə təxmin
                    # etmək həm yanlış uyğunlaşdırma, həm də IDOR riski yaradardı.
                    "enrollment_id": row["enrollment_id"],
                    # Nişan yuxarıdakı transkript qurucusundan gəlir — burada
                    # YENİDƏN sorğulanmır.  Xam faktlar da eyni oxumadan gəlir:
                    # «Nəticələrim» kartı onları açılan sübut panelində göstərir
                    # və İKİNCİ sorğu dəsti açmır (bax registrar.public).
                    "legacy": row.get("legacy"),
                    "legacy_grade_facts": row.get("legacy_grade_facts") or [],
                    "legacy_grade_review_required": row.get("legacy_grade_review_required", False),
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
                "uomg_available": sem.get("uomg_available", False),
                # Köçürülmüş nəticənin OXUNAN qeydi — blok başına BİR dəfə
                # (sətir-sətir yox; ölçmə üçün bax legacy_grade_read).
                "legacy_check_notice": sem.get("legacy_check_notice", ""),
                "legacy_missing_notice": sem.get("legacy_missing_notice", ""),
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
        "overall_uomg_available": data["cumulative_gpa_available"],
        "overall_uomg_label": exam_eligibility.UOMG_UNAVAILABLE_LABEL,
        "overall_uomg_notice": exam_eligibility.UOMG_UNAVAILABLE_NOTICE,
        "total_credits_earned": data["total_credits_earned"],
        "total_credits_gpa": data["total_credits_gpa"],
    }
