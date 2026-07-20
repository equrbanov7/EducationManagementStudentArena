"""Public read-facing helpers the accounts profile reuses for the student cabinet.

Mirrors the ``apps.appeals.public`` pattern: the accounts profile context
builder calls :func:`build_student_subjects_context` for the "Fənlərim" section
without importing registrar internals. Tenant/RLS scoping is inherited from the
active request; the helper only reads the requesting student's own record.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from apps.registrar import services
from apps.registrar.exam_bridge import (
    exam_eligibility,
    exam_result_summary,
    record_exam_result,
)
from apps.registrar.models import StudentAcademicRecord

# İmtahan mərkəzi ↔ jurnal körpüsü — exams tərəfindən bu fasad üzərindən çağırılır
# (apps/registrar/exam_bridge.py). Re-eksport, boundary-safe.
__all__ = [
    "exam_eligibility",
    "exam_result_summary",
    "record_exam_result",
]

# ``AcademicPeriod`` lives in the organizations module. Registrar already
# references organizations models only via string FKs (no Python import), which
# keeps the module-dependency graph acyclic (organizations → registrar via the
# seed command, but not back). We resolve it through the app registry to keep
# that property instead of a static ``from apps.organizations`` import.


def _academic_period_model():
    return django_apps.get_model("organizations", "AcademicPeriod")


def _empty_transcript() -> dict:
    from decimal import Decimal

    return {
        "has_record": False,
        "record": None,
        "semesters": [],
        "cumulative_gpa": Decimal("0.00"),
        "total_credits_earned": 0,
        "total_credits_gpa": 0,
        "quality_points": Decimal("0.00"),
        "ects_total": 0,
    }


def build_student_transcript_context(request, *, organization) -> dict:
    """Context for the student "Transkript" cabinet section (U5).

    Aggregates the requesting student's enrollments across all semesters into a
    credit-weighted GPA transcript (see :func:`transcript.build_student_transcript`).
    Degrades to a friendly empty state when the student has no academic record or
    no enrollments yet. Tenant/RLS scoping is inherited from the active request.
    """
    if organization is None or not getattr(request.user, "is_authenticated", False):
        return {"student_transcript_section": _empty_transcript()}

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program")
        .first()
    )
    program = record.program if record else None

    from apps.registrar import transcript as transcript_service

    data = transcript_service.build_student_transcript(student=request.user, organization=organization, program=program)
    data["record"] = record
    return {"student_transcript_section": data}


def _empty_overall_academic() -> dict:
    return {"has_record": False, "semesters": [], "year_options": [], "season_options": []}


def build_student_overall_academic_context(request, *, organization) -> dict:
    """Context for the student "Ümumi tədris məlumatı" cabinet section.

    Every subject the student has ever taken, grouped by semester (newest
    first) and decorated with the teacher name + fail-reason so the cabinet
    can offer search/filter over the full academic record (see
    :func:`transcript.build_student_overall_record`). Mirrors
    :func:`build_student_transcript_context`'s empty-state contract; does NOT
    duplicate the transcript's GPA aggregation.
    """
    if organization is None or not getattr(request.user, "is_authenticated", False):
        return {"overall_academic_section": _empty_overall_academic()}

    from apps.registrar import transcript as transcript_service

    data = transcript_service.build_student_overall_record(student=request.user, organization=organization)
    return {"overall_academic_section": data}


def build_profile_registrar_section(request, *, organization, section: str) -> dict:
    """Context for the registrar cabinet sections rendered INSIDE the profile
    shell (U12): schedule, academic calendar, teacher journal list, grade
    approvals and analytics. Access is already gated by ``allowed_sections``
    (rbac) + the AJAX-safe section whitelist; data scoping stays in the
    registrar service layer (RLS/tenant).

    Built lazily — only for the ACTIVE section (performance: no wasted queries)."""
    from apps.registrar import page_contexts

    if section in ("my-schedule", "academic-calendar", "grade-approvals", "analytics") and organization is None:
        return {"has_context": False}

    if section == "my-schedule":
        return page_contexts.schedule_context(request, organization, embedded=True)
    if section == "academic-calendar":
        return page_contexts.calendar_context(organization)
    if section == "my-journal":
        # Rol-aware: tələbə → öz jurnal xülasəsi (yalnız-oxu, bu günün dərsi gizli);
        # müəllim/admin → qrup seçimi (iş sahəsi ayrıca URL-də olsa da fallback qalır).
        student_context = build_student_journal_context(request, organization=organization)
        if student_context is not None:
            return student_context
        return page_contexts.journal_list_context(request.user, request=request)
    if section == "grade-approvals":
        return page_contexts.approvals_context(request.user, organization)
    if section == "analytics":
        return page_contexts.analytics_context(request, organization, embedded=True)
    return {}


def build_student_journal_context(request, *, organization) -> dict | None:
    """Tələbənin öz elektron jurnal görünüşü (profil paneli, yalnız-oxu).

    ``None`` → istifadəçi bu orqda tələbə deyil (çağıran müəllim fallback-ına
    keçir). Detal rejimi ``?subject=<enrollment_id>`` ilə açılır — YALNIZ öz
    enrollment-i qəbul olunur (IDOR yoxdur). BU GÜNÜN dərsi gizlədilir:
    müəllim hələ 2 saatlıq düzəliş pəncərəsindədir; qeydlər sabah görünür."""
    from decimal import Decimal

    from django.utils import timezone as _tz

    from apps.registrar import attendance, gradebook, journal_extras
    from apps.registrar.models import ComponentKind, ComponentScore, Enrollment, LessonMark

    if organization is None or not getattr(request.user, "is_authenticated", False):
        return None
    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program", "group")
        .first()
    )
    if record is None:
        return None

    from apps.registrar.page_contexts import _season_label

    AcademicPeriod = _academic_period_model()
    # Tədris ili + yarım il (Payız/Yaz/Yay) seçicisi — MÜƏLLİM jurnalı ilə eyni
    # məntiq (semestr 1-10 YOX). Yalnız tələbənin qeydiyyatı olan dövrlər.
    # (Enrollment funksiyanın yuxarısında artıq import olunub.)
    period_ids = list(
        Enrollment.objects.filter(organization=organization, student=request.user)
        .values_list("offering__period_id", flat=True)
        .distinct()
    )
    all_periods = list(
        AcademicPeriod.objects.filter(organization=organization, id__in=period_ids).order_by("-start_date")
    )
    if not all_periods:  # heç bir qeydiyyat yoxdursa — cari dövrü göstər (boş kartlar)
        cur = (
            AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
            or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
        )
        all_periods = [cur] if cur else []
    for p in all_periods:
        p.year_label = p.year_display
        p.season_label = _season_label(p)

    requested_period = (request.GET.get("period") or "").strip()
    period = next((p for p in all_periods if str(p.id) == requested_period), None)
    if period is None:
        period = next((p for p in all_periods if getattr(p, "is_current", False)), None) or (
            all_periods[0] if all_periods else None
        )

    section = {"is_student_journal": True, "record": record, "period": period, "subjects": [], "detail": None}
    if period is None:
        return {"journal_student_section": section}

    # Tədris ili seçimləri (RAW academic_year → label) + dövr seçimləri (season).
    year_label_map = {p.academic_year: p.year_display for p in all_periods}
    section["year_choices"] = [{"value": y, "label": year_label_map[y]} for y in sorted(year_label_map, reverse=True)]
    section["period_choices"] = [
        {"id": str(p.id), "year": p.academic_year, "label": p.season_label} for p in all_periods
    ]
    section["selected_year"] = period.academic_year
    section["selected_period_id"] = str(period.id)
    section["academic_year"] = period.year_display
    section["season_label"] = getattr(period, "season_label", "")

    semester_number = _resolve_semester_number(request)
    summary = gradebook.get_student_journal_summary(record=record, period=period, semester_number=semester_number)
    # FAZA B: hər fənnin müəllimini kart üçün əlavə et (kiçik N — tələbənin fənləri).
    for row in summary["subjects"]:
        row["teacher"] = getattr(row["enrollment"].offering, "instructor", None)
    section["subjects"] = summary["subjects"]
    section["semester_number"] = semester_number
    # Başqa fənlər üzrə limit xəbərdarlıqları (mockup: alt qırmızı çip).
    section["warnings"] = [
        row
        for row in summary["subjects"]
        if row["journal"]["barred"]
        or (
            row["journal"]["allowed_absence"] > 0
            and row["journal"]["absence_hours"] >= row["journal"]["allowed_absence"] * Decimal("0.75")
        )
    ]

    # FAZA B: ?subject yoxdursa FƏNN KARTLARI göstərilir (avtomatik açılış yox) —
    # müəllim jurnalı kimi: kartlar → klik → cədvəl.
    selected = (request.GET.get("subject") or "").strip()
    if not selected:
        return {"journal_student_section": section}

    enrollment = (
        Enrollment.objects.filter(pk=selected, student=request.user, organization=organization)
        .select_related("offering", "offering__subject", "offering__assessment_scheme")
        .first()
    )
    if enrollment is None:
        return {"journal_student_section": section}

    offering = enrollment.offering
    today = _tz.localdate()
    # Tam şəxsi tarixçə — BU GÜN İSTİSNA (müəllimin düzəliş pəncərəsi bitməmiş).
    marks = list(
        LessonMark.objects.filter(enrollment=enrollment, lesson__date__lt=today)
        .select_related("lesson")
        .order_by("-lesson__date", "-lesson__created_at")
    )
    hidden_today = LessonMark.objects.filter(enrollment=enrollment, lesson__date=today).exists()

    kollokviums = []
    kcomps = list(offering.assessment_components.filter(kind=ComponentKind.KOLLOKVIUM).order_by("order", "name"))
    if kcomps:
        score_by = {
            cs.component_id: cs.score
            for cs in ComponentScore.objects.filter(component__in=kcomps, enrollment=enrollment)
        }
        kollokviums = [{"component": c, "score": score_by.get(c.id), "held_on": c.held_on} for c in kcomps]

    # Rəsmi düzəliş almış xanalar (tələbə tərəfdə sarı + tarixçə üçün, sənədsiz).
    from apps.registrar import corrections as _corrections

    corr_map = _corrections.corrections_map_for_enrollment(enrollment)

    # Tarixçə sətirləri: paritet çipi + kollokvium markeri (held_on tarixinə görə).
    koll_by_date = {k["held_on"]: k for k in kollokviums if k["held_on"]}
    history = [
        {
            "mark": m,
            "parity": gradebook._lesson_parity(offering, m.lesson),
            "kollokvium": koll_by_date.get(m.lesson.date),
            "corrected": str(m.id) in corr_map,
            # Dərs tipi (mühazirə/seminar/lab) — cədvəldə sütun + filtr üçün.
            "kind": m.lesson.kind,
            "kind_display": m.lesson.get_kind_display(),
            "teacher": getattr(offering, "instructor", None),
        }
        for m in marks
    ]
    # Bu fənndə mövcud dərs tipləri (filtr düymələri üçün).
    section_kinds = []
    _seen_kinds = set()
    for m in marks:
        if m.lesson.kind not in _seen_kinds:
            _seen_kinds.add(m.lesson.kind)
            section_kinds.append({"value": m.lesson.kind, "label": m.lesson.get_kind_display()})

    selfwork = journal_extras.get_selfwork_board(offering)
    own_selfwork = next((r for r in selfwork["rows"] if r["enrollment"].id == enrollment.id), None)

    scheme = getattr(offering, "assessment_scheme", None)
    cap = scheme.entry_score_max if scheme else 50
    journal_row = next((s for s in summary["subjects"] if s["enrollment"].id == enrollment.id), None)

    # KPI + bal bölgüsü (real kompozisiya): dərs balları + kollokvium + sərbəst iş.
    entry = gradebook.entry_score_for(enrollment, cap)
    # Davamiyyət balı (10-luq) — rəsmi "DAVAMİYYƏT BALININ HESABLANMASI" cədvəli:
    # 10 × (1 − buraxılmış_saat/dərs_saatı), 25%-dən çox qayıbda "imtahana buraxılmır".
    dav_lesson_hours = offering.lesson_hours or sum((m.lesson.hours for m in marks), 0)
    dav_score, dav_barred = attendance.attendance_score(
        dav_lesson_hours,
        enrollment.absence_hours,
        limit_percent=gradebook.absence_limit_percent_for(offering),
    )
    koll_entered = [k["score"] for k in kollokviums if k["score"] is not None]
    koll_sum = sum(koll_entered, Decimal("0"))
    selfwork_total = own_selfwork["total"] if own_selfwork else 0
    koll_avg = (koll_sum / len(koll_entered)).quantize(Decimal("0.1")) if koll_entered else None
    # Bölgü hissələri KANONİK entry ilə uzlaşır: "dərs balları" qalıq kimi
    # hesablanır (generic komponent rejimində də cəm düz çıxır).
    lesson_sum = max(Decimal("0"), entry - koll_sum - Decimal(selfwork_total))

    def _pct(part):
        return min(100, int(part / Decimal(cap) * 100)) if cap else 0

    section["detail"] = {
        "enrollment": enrollment,
        "offering": offering,
        "subject": offering.subject,
        "marks": marks,
        "history": history,
        "lesson_kinds": section_kinds,
        "teacher": getattr(offering, "instructor", None),
        "hidden_today": hidden_today,
        "kollokviums": kollokviums,
        "koll_avg": koll_avg,
        "dav_score": dav_score,
        "dav_barred": dav_barred,
        "selfwork_topics": selfwork["topics"],
        "selfwork_row": own_selfwork,
        "coursework": getattr(enrollment, "course_work", None),
        "entry_score": entry,
        "entry_score_max": cap,
        "entry_pct": _pct(entry),
        "parts": {
            "lesson_sum": lesson_sum,
            "lesson_pct": _pct(lesson_sum),
            "koll_sum": koll_sum,
            "koll_pct": _pct(koll_sum),
            "selfwork": selfwork_total,
            "selfwork_pct": _pct(Decimal(selfwork_total)),
        },
        "journal": journal_row["journal"] if journal_row else None,
    }
    section["corrections_map"] = corr_map
    return {"journal_student_section": section}


def _empty_section() -> dict:
    return {
        "has_record": False,
        "record": None,
        "period": None,
        "semester_number": 1,
        "subjects": [],
        "elective_blocks": {},
        "group_decisions": {},
        "credit_summary": None,
    }


def _resolve_semester_number(request, default=1) -> int:
    try:
        value = int(request.GET.get("semester") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def build_student_subjects_context(request, *, organization, semester_number=None) -> dict:
    """Context for the student "Fənlərim" (my-subjects) cabinet section.

    Resolves the requesting user's :class:`StudentAcademicRecord` and the
    current :class:`AcademicPeriod` in *organization*, then delegates to
    :func:`services.get_student_cabinet_data`. Degrades to a friendly empty
    state (``has_record=False``) when the student has no academic record yet,
    so non-university tenants render a harmless placeholder.
    """
    section = _empty_section()
    if organization is None or not getattr(request.user, "is_authenticated", False):
        return {"student_subjects_section": section}

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program", "curriculum", "group")
        .first()
    )
    if record is None:
        return {"student_subjects_section": section}

    section["has_record"] = True
    section["record"] = record

    AcademicPeriod = _academic_period_model()
    period = (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )
    if period is None:
        return {"student_subjects_section": section}

    if semester_number is None:
        semester_number = _resolve_semester_number(request)

    data = services.get_student_cabinet_data(record=record, period=period, semester_number=semester_number)

    # Attach each subject's electronic-journal summary (giriş balı + davamiyyət),
    # so "Fənlərim" doubles as the student's "Qiymətlərim" view.
    from apps.registrar import gradebook

    journal_summary = gradebook.get_student_journal_summary(
        record=record, period=period, semester_number=semester_number
    )
    journal_by_enrollment = {row["enrollment"].id: row["journal"] for row in journal_summary["subjects"]}
    from apps.registrar import finals

    for subject_row in data["subjects"]:
        subject_row["journal"] = journal_by_enrollment.get(subject_row["enrollment"].id)
        subject_row["final"] = finals.compute_final_result(
            enrollment=subject_row["enrollment"], organization=organization
        )
        subject_row["components"] = gradebook.get_component_breakdown(subject_row["enrollment"])

    # Pre-join each elective block with the group's decision so the template
    # renders without a dict-lookup filter (block name → chosen subject).
    group_decisions = data["group_decisions"]
    elective_blocks = [
        {
            "name": name,
            "required_choices": block["required_choices"],
            "options": block["options"],
            "chosen": group_decisions.get(name),
        }
        for name, block in data["elective_blocks"].items()
    ]
    section.update(
        {
            "period": period,
            "semester_number": semester_number,
            "subjects": data["subjects"],
            "elective_blocks": elective_blocks,
            "group_decisions": group_decisions,
            "credit_summary": data["credit_summary"],
        }
    )
    return {"student_subjects_section": section}
