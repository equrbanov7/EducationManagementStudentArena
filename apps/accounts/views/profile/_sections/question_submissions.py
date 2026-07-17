"""Profil "question-submissions" bölməsi üçün context-fragment qurucusu.

Müəllim: öz göndərişləri — axtarış + status filtri + səhifələmə.
İmtahan mərkəzi: təşkilatın bütün göndərişləri EYNİ bölmədə inline filtrlənir
(ayrıca "qutu" səhifəsi yoxdur): axtarış, status, fakültə/kafedra (OrgUnit
subtree), müəllim, tədris ili/semestr (AcademicPeriod tarix aralığı —
göndərişdə dövr FK-sı yoxdur, ona görə ``created_at`` aralığa salınır) və dil.

Bütün GET parametrləri ``qsub_`` prefikslidir ki, digər profil bölmələrinin
parametrləri ilə toqquşmasın. Stat kartlar həm də status-filtr linkləridir.
"""

from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext

PAGE_SIZE = 10

_STATUS_VALUES = ("pending", "accepted", "rejected")

# Reviewer filtr açarları → GET parametr adları.
_FILTER_PARAMS = {
    "faculty": "qsub_faculty",
    "kafedra": "qsub_kafedra",
    "teacher": "qsub_teacher",
    "year": "qsub_year",
    "period": "qsub_period",
    "lang": "qsub_lang",
}


def _inactive_defaults() -> dict:
    return {
        "question_submissions_items": [],
        "question_submissions_page": None,
        "question_submissions_is_reviewer": False,
        "question_submissions_total_count": 0,
        "question_submissions_pending_count": 0,
        "question_submissions_accepted_count": 0,
        "question_submissions_rejected_count": 0,
        "question_submissions_create_url": "",
        "question_submissions_search": "",
        "question_submissions_status": "",
        "question_submissions_filters": {},
        "question_submissions_faculties": [],
        "question_submissions_kafedras": [],
        "question_submissions_teachers": [],
        "question_submissions_years": [],
        "question_submissions_periods": [],
        "question_submissions_languages": [],
        "question_submissions_status_cards": [],
        "question_submissions_active_chips": [],
        "question_submissions_clear_url": "",
        "question_submissions_base_query": "",
        "question_submissions_pagination_query": "",
        "question_submissions_has_filters": False,
    }


def _profile_query(params: dict) -> str:
    """?section=… ilə başlayan, yalnız dolu qiymətləri saxlayan query string."""
    pairs = [("section", "question-submissions")]
    pairs.extend((key, value) for key, value in params.items() if value)
    return urlencode(pairs)


def _read_filters(request, *, is_reviewer: bool) -> dict:
    """GET-dən filtr dəyərlərini oxu (reviewer olmayan üçün yalnız q + status)."""
    values = {
        "q": (request.GET.get("qsub_q") or "").strip(),
        "status": (request.GET.get("qsub_status") or "").strip().lower(),
    }
    if values["status"] not in _STATUS_VALUES:
        values["status"] = ""
    for key, param in _FILTER_PARAMS.items():
        raw = (request.GET.get(param) or "").strip() if is_reviewer else ""
        values[key] = raw[:100]
    return values


def _pick(options, raw_id):
    """Siyahıdan pk-sı uyğun gələn elementi tap (yanlış/yad id → None)."""
    if not raw_id:
        return None
    return next((item for item in options if str(item.pk) == raw_id), None)


def _apply_reviewer_filters(filtered, filters, *, faculty, kafedra, periods, year_periods):
    """Fakültə/kafedra subtree, müəllim, dövr (tarix aralığı) və dil filtrləri."""
    from django.db.models import Q

    unit = kafedra or faculty
    if unit:
        filtered = filtered.filter(
            Q(student_groups__org_unit__path__startswith=unit.path)
            | Q(student_group__org_unit__path__startswith=unit.path)
        )

    if filters["teacher"].isdigit():
        filtered = filtered.filter(teacher_id=int(filters["teacher"]))

    selected_period = _pick(periods, filters["period"])
    if selected_period is not None:
        filtered = filtered.filter(created_at__date__range=(selected_period.start_date, selected_period.end_date))
    elif filters["year"] and year_periods:
        ranges = Q()
        for period in year_periods:
            ranges |= Q(created_at__date__range=(period.start_date, period.end_date))
        filtered = filtered.filter(ranges)

    if filters["lang"]:
        filtered = filtered.filter(language=filters["lang"])

    return filtered


def _status_cards(counts, filters, active_params, *, is_reviewer: bool) -> list:
    """Stat kartlar = status filtr linkləri (aktiv kart təkrar klikdə sıfırlanır)."""
    ctx = "accounts.profile.question_submissions"
    rejected_label = pgettext(ctx, "Rədd edilmiş") if is_reviewer else pgettext(ctx, "Düzəliş gözləyən")
    cards = [
        ("", pgettext(ctx, "Ümumi göndəriş"), counts["total"], "fa-paper-plane", "blue"),
        ("pending", pgettext(ctx, "Baxılır"), counts["pending"], "fa-hourglass-half", "amber"),
        ("accepted", pgettext(ctx, "Qəbul edilmiş"), counts["accepted"], "fa-check", "green"),
        ("rejected", rejected_label, counts["rejected"], "fa-rotate-left", "red"),
    ]
    result = []
    for status, label, value, icon, tone in cards:
        is_active = filters["status"] == status
        params = dict(active_params)
        # Aktiv karta təkrar klik → "hamısı"; kartlar səhifəni sıfırlayır.
        params["qsub_status"] = "" if is_active else status
        result.append(
            {
                "status": status,
                "label": label,
                "value": value or 0,
                "icon": icon,
                "tone": tone,
                "is_active": is_active,
                "query": _profile_query(params),
            }
        )
    return result


def _active_chips(filters, active_params, *, faculty, kafedra, teacher, period, languages) -> list:
    """Seçilmiş reviewer filtrləri üçün silinə bilən çiplər."""
    ctx = "accounts.profile.question_submissions"
    lang_map = dict(languages)
    labels = {
        "faculty": (pgettext(ctx, "Fakültə"), faculty.name if faculty else ""),
        "kafedra": (pgettext(ctx, "Kafedra"), kafedra.name if kafedra else ""),
        "teacher": (
            pgettext(ctx, "Müəllim"),
            (teacher.get_full_name() or teacher.username) if teacher else "",
        ),
        "year": (pgettext(ctx, "Tədris ili"), filters["year"]),
        "period": (pgettext(ctx, "Semestr"), period.name if period else ""),
        "lang": (pgettext(ctx, "Dil"), lang_map.get(filters["lang"], "")),
    }
    chips = []
    for key, param in _FILTER_PARAMS.items():
        if not filters[key]:
            continue
        title, value = labels[key]
        params = dict(active_params)
        params[param] = ""
        if key == "faculty":
            params["qsub_kafedra"] = ""  # fakültə silinəndə kafedra da sıfırlanır
        if key == "year":
            params["qsub_period"] = ""
        chips.append({"title": title, "value": value or "—", "query": _profile_query(params)})
    return chips


def build_question_submissions_context(request, *, allowed_sections, active_section) -> dict:
    if not (active_section == "question-submissions" and "question-submissions" in allowed_sections):
        return _inactive_defaults()

    from django.contrib.auth import get_user_model
    from django.core.paginator import Paginator
    from django.db.models import Count, Q

    from apps.exams.constants import EXAM_LANGUAGE_CHOICES
    from apps.exams.models import QuestionSubmission
    from apps.exams.public import is_exam_center_user
    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.organizations.structure_views.constants import KAFEDRA_UNIT_TYPES
    from core.constants import OrgUnitType
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return _inactive_defaults()

    is_reviewer = is_exam_center_user(request.user)
    scoped = QuestionSubmission.objects.filter(organization=organization)
    if not is_reviewer:
        scoped = scoped.filter(teacher=request.user)

    # Stat kartlar üçün saylar — filtrsiz skop, TƏK aqreqat sorğu.
    counts = scoped.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=QuestionSubmission.STATUS_PENDING)),
        accepted=Count("id", filter=Q(status=QuestionSubmission.STATUS_ACCEPTED)),
        rejected=Count("id", filter=Q(status=QuestionSubmission.STATUS_REJECTED)),
    )

    filters = _read_filters(request, is_reviewer=is_reviewer)

    # ── Reviewer filtr mənbələri (yalnız mərkəz üçün sorğulanır) ──
    faculties, kafedras, teachers, periods, years, year_periods = [], [], [], [], [], []
    faculty = kafedra = teacher = period = None
    if is_reviewer:
        faculties = list(
            OrgUnit.active.filter(organization=organization, unit_type=OrgUnitType.FACULTY).order_by("name")
        )
        faculty = _pick(faculties, filters["faculty"])
        kafedra_qs = OrgUnit.active.filter(organization=organization, unit_type__in=KAFEDRA_UNIT_TYPES)
        if faculty is not None:
            kafedra_qs = kafedra_qs.filter(parent=faculty)
        kafedras = list(kafedra_qs.order_by("name"))
        kafedra = _pick(kafedras, filters["kafedra"])
        if kafedra is None:
            filters["kafedra"] = ""

        User = get_user_model()
        teacher_ids = scoped.values_list("teacher_id", flat=True).distinct()
        teachers = list(User.objects.filter(id__in=teacher_ids).order_by("first_name", "last_name", "username"))
        teacher = _pick(teachers, filters["teacher"])

        all_periods = list(AcademicPeriod.active.filter(organization=organization).order_by("-start_date"))
        years = sorted({p.academic_year for p in all_periods}, reverse=True)
        if filters["year"] not in years:
            filters["year"] = ""
        year_periods = [p for p in all_periods if p.academic_year == filters["year"]]
        periods = year_periods if filters["year"] else all_periods
        period = _pick(periods, filters["period"])
        if period is None:
            filters["period"] = ""

    if filters["lang"] and filters["lang"] not in {code for code, _ in EXAM_LANGUAGE_CHOICES}:
        filters["lang"] = ""

    # ── Siyahı queryset-i: axtarış + status + reviewer filtrləri ──
    filtered = scoped
    if filters["status"]:
        filtered = filtered.filter(status=filters["status"])
    if filters["q"]:
        condition = (
            Q(title__icontains=filters["q"])
            | Q(subject__icontains=filters["q"])
            | Q(group_label__icontains=filters["q"])
        )
        if is_reviewer:
            condition |= (
                Q(teacher__first_name__icontains=filters["q"])
                | Q(teacher__last_name__icontains=filters["q"])
                | Q(teacher__username__icontains=filters["q"])
            )
        filtered = filtered.filter(condition)
    if is_reviewer:
        filtered = _apply_reviewer_filters(
            filtered, filters, faculty=faculty, kafedra=kafedra, periods=periods, year_periods=year_periods
        )

    filtered = filtered.select_related("teacher", "accepted_bank").distinct().order_by("-created_at", "-id")
    page = Paginator(filtered, PAGE_SIZE).get_page(request.GET.get("qsub_page"))

    # ── Query string-lər: aktiv parametrlər (page-siz) ──
    active_params = {"qsub_q": filters["q"], "qsub_status": filters["status"]}
    for key, param in _FILTER_PARAMS.items():
        active_params[param] = filters[key] if is_reviewer else ""
    has_filters = any(filters[key] for key in _FILTER_PARAMS)

    return {
        "question_submissions_items": list(page.object_list),
        "question_submissions_page": page,
        "question_submissions_is_reviewer": is_reviewer,
        "question_submissions_total_count": counts["total"] or 0,
        "question_submissions_pending_count": counts["pending"] or 0,
        "question_submissions_accepted_count": counts["accepted"] or 0,
        # Müəllim üçün "düzəliş gözləyən", mərkəz üçün "rədd edilmiş" mənasında.
        "question_submissions_rejected_count": counts["rejected"] or 0,
        "question_submissions_create_url": reverse("exams:question_submission_create"),
        "question_submissions_search": filters["q"],
        "question_submissions_status": filters["status"],
        "question_submissions_filters": filters,
        "question_submissions_faculties": faculties,
        "question_submissions_kafedras": kafedras,
        "question_submissions_teachers": teachers,
        "question_submissions_years": years,
        "question_submissions_periods": periods,
        "question_submissions_languages": EXAM_LANGUAGE_CHOICES,
        "question_submissions_status_cards": _status_cards(counts, filters, active_params, is_reviewer=is_reviewer),
        "question_submissions_active_chips": _active_chips(
            filters,
            active_params,
            faculty=faculty,
            kafedra=kafedra,
            teacher=teacher,
            period=period,
            languages=EXAM_LANGUAGE_CHOICES,
        ),
        "question_submissions_clear_url": f"{reverse('accounts:profile')}?section=question-submissions",
        "question_submissions_base_query": _profile_query(active_params),
        "question_submissions_pagination_query": _profile_query(active_params),
        "question_submissions_has_filters": has_filters,
    }
