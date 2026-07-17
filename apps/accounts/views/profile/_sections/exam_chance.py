"""Profil "exam-chance" bölməsi — İmtahan Mərkəzi «imtahan şansı ver».

``section`` dict-ini YERİNDƏ mutasiya edir (kollokvium_windows pattern-i).
İmtahan siyahısı tədris ili / semestr (AcademicPeriod tarix aralığı —
imtahanda dövr FK-sı yoxdur, ``start_datetime`` aralığa salınır), fakültə /
kafedra (OrgUnit subtree, imtahanın icazəli qruplarının ``org_unit``-i
üzərindən) və ad axtarışı ilə daraldılır; kafedra seçimləri seçilmiş
fakültənin uşaqlarıdır. Tələbə axtarışı qrup adı / istifadəçi adı /
ad-soyad üzrə işləyir və nəticələr grant formunda checkbox kimi seçilir.
"""

from django.urls import reverse

from apps.accounts.views._helpers.formatting import _append_query_params

RECENT_GRANT_LIMIT = 15
STUDENT_RESULT_LIMIT = 40

# Filtr açarları → GET parametr adları (qsub bölməsi ilə eyni yanaşma).
_FILTER_PARAMS = {
    "year": "chance_year",
    "period": "chance_period",
    "faculty": "chance_faculty",
    "kafedra": "chance_kafedra",
    "exam_q": "chance_exam_q",
    "student_q": "chance_student_q",
}


def _pick(options, raw_id):
    """Siyahıdan pk-sı uyğun gələn elementi tap (yanlış/yad id → None)."""
    if not raw_id:
        return None
    return next((item for item in options if str(item.pk) == raw_id), None)


def _read_filters(request) -> dict:
    return {key: (request.GET.get(param) or "").strip()[:100] for key, param in _FILTER_PARAMS.items()}


def _search_students(organization, query):
    """Org üzvləri arasında qrup adı / istifadəçi adı / ad-soyad axtarışı."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from apps.organizations.public import organization_user_queryset

    User = get_user_model()
    condition = (
        Q(username__icontains=query)
        | Q(first_name__icontains=query)
        | Q(last_name__icontains=query)
        | Q(
            student_groups_as_student__organization=organization,
            student_groups_as_student__name__icontains=query,
        )
    )
    return list(
        organization_user_queryset(organization, queryset=User.objects.filter(condition))
        .distinct()
        .order_by("first_name", "last_name", "username")[:STUDENT_RESULT_LIMIT]
    )


def build_exam_chance_section(request, section, *, active_organization, allowed_sections, active_section):
    if "exam-chance" not in allowed_sections or active_section != "exam-chance":
        return

    from django.db.models import Q

    from apps.exams.models import Exam, StudentExamAttemptGrant, StudentGroup
    from apps.exams.services.access_policy import SECURE_EXAM_CATEGORIES
    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.organizations.structure_views.constants import KAFEDRA_UNIT_TYPES
    from core.constants import OrgUnitType

    organization = active_organization
    section["selected_org"] = organization
    section["post_next_url"] = _append_query_params(reverse("accounts:profile"), section="exam-chance")
    if organization is None:
        return

    filters = _read_filters(request)

    # ── Tədris ili + semestr seçimləri ──────────────────────────────────────
    all_periods = list(AcademicPeriod.active.filter(organization=organization).order_by("-start_date"))
    years = sorted({p.academic_year for p in all_periods}, reverse=True)
    if filters["year"] not in years:
        filters["year"] = ""
    year_periods = [p for p in all_periods if p.academic_year == filters["year"]]
    periods = year_periods if filters["year"] else all_periods
    period = _pick(periods, filters["period"])
    if period is None:
        filters["period"] = ""

    # ── Fakültə → kafedra (asılı seçimlər) ──────────────────────────────────
    faculties = list(OrgUnit.active.filter(organization=organization, unit_type=OrgUnitType.FACULTY).order_by("name"))
    faculty = _pick(faculties, filters["faculty"])
    if faculty is None:
        filters["faculty"] = ""
    kafedra_qs = OrgUnit.active.filter(organization=organization, unit_type__in=KAFEDRA_UNIT_TYPES)
    if faculty is not None:
        kafedra_qs = kafedra_qs.filter(parent=faculty)
    kafedras = list(kafedra_qs.order_by("name"))
    kafedra = _pick(kafedras, filters["kafedra"])
    if kafedra is None:
        filters["kafedra"] = ""

    # ── İmtahan siyahısı (filtrli) ──────────────────────────────────────────
    exams_qs = Exam.objects.filter(
        organization=organization,
        exam_type_extended__in=sorted(SECURE_EXAM_CATEGORIES),
        is_deleted=False,
        is_archived=False,
    )
    if filters["exam_q"]:
        exams_qs = exams_qs.filter(title__icontains=filters["exam_q"])
    unit = kafedra or faculty
    if unit is not None:
        exams_qs = exams_qs.filter(allowed_groups__org_unit__path__startswith=unit.path)
    if period is not None:
        exams_qs = exams_qs.filter(start_datetime__date__range=(period.start_date, period.end_date))
    elif filters["year"] and year_periods:
        ranges = Q()
        for p in year_periods:
            ranges |= Q(start_datetime__date__range=(p.start_date, p.end_date))
        exams_qs = exams_qs.filter(ranges)
    section["exams"] = list(
        exams_qs.only("id", "title", "exam_type_extended", "start_datetime")
        .distinct()
        .order_by("-start_datetime", "-id")[:300]
    )

    # ── Qruplar (fakültə/kafedra seçiminə uyğun daraldılır) ────────────────
    groups_qs = StudentGroup.objects.filter(organization=organization)
    if unit is not None:
        groups_qs = groups_qs.filter(org_unit__path__startswith=unit.path)
    section["groups"] = list(groups_qs.only("id", "name").order_by("name"))

    # ── Tələbə axtarışı (qrup / istifadəçi adı / ad-soyad) ─────────────────
    section["student_results"] = _search_students(organization, filters["student_q"]) if filters["student_q"] else []

    # ── Son verilən şanslar (görünən jurnal; tam tarixçə auditdədir) ───────
    section["recent_grants"] = list(
        StudentExamAttemptGrant.objects.filter(exam__organization=organization)
        .select_related("exam", "student", "granted_by")
        .order_by("-updated_at")[:RECENT_GRANT_LIMIT]
    )

    section["filters"] = filters
    section["years"] = years
    section["periods"] = periods
    section["faculties"] = faculties
    section["kafedras"] = kafedras
    selected_exam = (request.GET.get("chance_exam") or "").strip()
    section["selected_exam_id"] = selected_exam if selected_exam.isdigit() else ""
