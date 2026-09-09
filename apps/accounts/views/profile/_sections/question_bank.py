"""Profil "question-bank" bölməsi üçün context-fragment qurucusu.

2026-09-09 (sahib: «sual bankı … səliqəyə sal, modern UX/UI»): ekran `ems_ui`
komponentləri ilə yenidən quruldu — yaratma forması artıq səhifənin yarısını
tutan kart deyil, başlıqdakı «Yeni bank» düyməsi ilə açılan dialoqdur; əsas
məzmun KPI sırası + avto filtr paneli + bank cədvəlidir.  Təqdimat modeli
``question_bank_ui.py``-dədir (modul ölçüsü büdcəsi).

GET parametrləri `bank_` prefiksindədir (`bank_search`, `bank_kind`,
`bank_format`, `bank_lang`, `bank_page`) — filtr panelinin «Sıfırla» düyməsi
məhz bu prefiksi atır.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext, pgettext

from apps.accounts.views._helpers.formatting import _append_query_params, _query_string

from . import question_bank_ui as ui


def _inactive_defaults() -> dict:
    """Bölmə aktiv olmayanda main.py-dakı default dəyərlərlə eyni."""
    return {
        "question_bank_banks": [],
        "question_bank_page_obj": None,
        "question_bank_search_query": "",
        "question_bank_pagination_query": _query_string(section="question-bank"),
        "question_bank_back_url": _append_query_params(reverse("accounts:profile"), section="question-bank"),
        "question_bank_language_choices": [],
        "question_bank_default_type_choices": [],
        "question_bank_exam_kind_choices": [],
        "question_bank_kind_filter": "",
        "question_bank_kind_pills": [],
        "question_bank_can_create": False,
        "question_bank_is_center": False,
        "question_bank_section": {},
    }


def _kind_pills(search_query: str, kind_filter: str, choices) -> list:
    """İmtahan növü filtr pillləri (Hamısı / Final / Midterm / Quiz / Ümumi).

    Filtr artıq panelin «Təyinat» seçicisindədir; bu siyahı geriyə uyğunluq
    üçün (dərin linklər, köhnə şablon çağırışları) qalır.
    """
    pills = [("", pgettext("accounts.profile.question_bank", "Hamısı"))]
    pills.extend((value, label) for value, label in choices)
    pills.append(("general", pgettext("accounts.profile.question_bank", "Ümumi")))
    result = []
    for value, label in pills:
        params = [("section", "question-bank")]
        if search_query:
            params.append(("bank_search", search_query))
        if value:
            params.append(("bank_kind", value))
        result.append(
            {
                "value": value,
                "label": label,
                "is_active": kind_filter == value,
                "query": urlencode(params),
            }
        )
    return result


def _format_labels() -> dict:
    """`default_question_type` → istifadəçi etiketi (mövcud msgid-lər)."""
    return {"test": gettext("Test"), "written": gettext("Yazılı")}


def _row(bank, *, user_id, back_url, format_labels, kind_labels) -> dict:
    """Cədvəl sətri üçün bir bankın bütün göstərilən dəyərləri."""
    teacher = bank.source_teacher
    teacher_name = (teacher.get_full_name() or teacher.username) if teacher else ""
    return {
        "id": str(bank.id),
        "name": bank.name,
        "subject_label": bank.subject_label,
        "kind": bank.exam_kind or "",
        "kind_badge": ui.kind_badge(bank.exam_kind, kind_labels.get(bank.exam_kind or "", "—")),
        "format": bank.default_question_type,
        "format_label": format_labels.get(bank.default_question_type, bank.default_question_type),
        "language": bank.language,
        "language_label": bank.get_language_display(),
        "teacher_id": str(bank.source_teacher_id) if bank.source_teacher_id else "",
        "teacher_name": teacher_name,
        "question_count": bank.lib_count,
        "created": bank.created_at.strftime("%d.%m.%Y"),
        "is_shared": bank.is_shared,
        # Redaktə/silmə YALNIZ bankın sahibinə açıqdır (server də bunu yoxlayır).
        "can_manage": bank.created_by_id == user_id,
        "subject_id": str(bank.subject_ref_id) if bank.subject_ref_id else "",
        "detail_url": reverse("exams:question_bank_detail", args=[bank.id]),
        "word_url": reverse("exams:question_bank_word_export", args=[bank.id]),
        "update_url": reverse("exams:question_bank_update", args=[bank.id]),
        "delete_url": reverse("exams:question_bank_delete", args=[bank.id]),
        "back_url": back_url,
    }


def _read_params(request, *, is_center, exam_kind_choices, language_values, format_values) -> dict:
    """GET filtrlərini oxuyub təmizləyir (yad dəyər → boş)."""
    from apps.exams.constants import QUESTION_EXAM_KIND_VALUES

    allowed_kinds = {value for value, _label in exam_kind_choices}
    kind = (request.GET.get("bank_kind") or "").strip().lower()
    if kind not in QUESTION_EXAM_KIND_VALUES and kind != "general":
        kind = ""
    if not is_center and kind and kind != "general" and kind not in allowed_kinds:
        kind = ""
    language = (request.GET.get("bank_lang") or "").strip().lower()
    fmt = (request.GET.get("bank_format") or "").strip().lower()
    return {
        "search": (request.GET.get("bank_search") or "").strip()[:120],
        "kind": kind,
        "lang": language if language in language_values else "",
        "format": fmt if fmt in format_values else "",
    }


def _apply_filters(qs, params):
    search = params["search"]
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(subject__icontains=search)
            | Q(subject_ref__name__icontains=search)
            | Q(subject_ref__code__icontains=search)
            | Q(source_teacher__first_name__icontains=search)
            | Q(source_teacher__last_name__icontains=search)
            | Q(source_teacher__username__icontains=search)
        )
    if params["kind"] == "general":
        qs = qs.filter(exam_kind="")
    elif params["kind"]:
        qs = qs.filter(exam_kind=params["kind"])
    if params["lang"]:
        qs = qs.filter(language=params["lang"])
    if params["format"]:
        qs = qs.filter(default_question_type=params["format"])
    return qs


def build_question_bank_context(request, *, allowed_sections, active_section) -> dict:
    """Sual bankı bölməsi üçün ``context`` açarlarını qaytarır. Bölmə aktiv
    deyilsə main.py default-ları ilə eyni dəyərləri verir (davranış dəyişmir)."""
    if not (active_section == "question-bank" and "question-bank" in allowed_sections):
        return _inactive_defaults()

    from apps.exams.constants import QUESTION_EXAM_KIND_CHOICES
    from apps.exams.models import QuestionBank
    from apps.exams.public import (
        EXAM_LANGUAGE_CHOICES,
        accessible_banks,
        can_create_question_bank,
        is_exam_center_user,
    )
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    # Müəllim üçün bank təyinatı YALNIZ Quiz-dir (şəxsi bank); Final/Midterm
    # seçimləri və filtri ancaq imtahan mərkəzinə göstərilir.
    is_center = is_exam_center_user(request.user)
    exam_kind_choices = (
        QUESTION_EXAM_KIND_CHOICES
        if is_center
        else tuple((value, label) for value, label in QUESTION_EXAM_KIND_CHOICES if value == "quiz")
    )
    type_choices = QuestionBank.DEFAULT_QUESTION_TYPE_CHOICES
    format_labels = _format_labels()
    filter_type_choices = tuple((value, format_labels.get(value, value)) for value, _label in type_choices)
    params = _read_params(
        request,
        is_center=is_center,
        exam_kind_choices=exam_kind_choices,
        language_values={code for code, _ in EXAM_LANGUAGE_CHOICES},
        format_values={value for value, _ in type_choices},
    )

    base_qs = accessible_banks(request.user, organization)
    totals = base_qs.aggregate(
        banks=Count("id", distinct=True),
        questions=Count("library_questions", filter=Q(library_questions__is_active=True)),
    )
    kind_counts = {
        row["exam_kind"] or "": row["total"]
        for row in base_qs.values("exam_kind").order_by().annotate(total=Count("id"))
    }

    qs = _apply_filters(
        base_qs.select_related("subject_ref", "source_teacher").annotate(
            lib_count=Count("library_questions", filter=Q(library_questions__is_active=True))
        ),
        params,
    ).order_by("-created_at")

    page_obj = Paginator(qs, 12).get_page(request.GET.get("bank_page"))
    back_url = _append_query_params(
        reverse("accounts:profile"),
        section="question-bank",
        bank_search=params["search"],
        bank_kind=params["kind"],
        bank_lang=params["lang"],
        bank_format=params["format"],
        bank_page=request.GET.get("bank_page"),
    )
    kind_labels = {value: label for value, label in QUESTION_EXAM_KIND_CHOICES}
    kind_labels[""] = pgettext("accounts.profile.question_bank", "Ümumi")
    rows = [
        _row(
            bank,
            user_id=request.user.id,
            back_url=back_url,
            format_labels=format_labels,
            kind_labels=kind_labels,
        )
        for bank in page_obj.object_list
    ]
    can_create = can_create_question_bank(request.user)
    state_title, state_body = ui.states(has_filters=any(params.values()), can_create=can_create)
    create_next = _append_query_params(reverse("accounts:profile"), section="question-bank")

    section = {
        "subtitle": ui.subtitle(is_center=is_center),
        # Boş `ems-header__actions` qutusu qalmasın — şablon yolu yalnız
        # səlahiyyət varsa verilir.
        "header_actions": ("exams/teacher/partials/question_bank/_header_actions.html" if can_create else ""),
        "kpi_tiles": ui.kpi_tiles(
            bank_count=totals["banks"] or 0,
            question_count=totals["questions"] or 0,
            kind_counts=kind_counts,
            exam_kind_choices=exam_kind_choices,
        ),
        "filter_fields": ui.filter_fields(
            search=params["search"],
            kind=params["kind"],
            language=params["lang"],
            fmt=params["format"],
            exam_kind_choices=exam_kind_choices,
            language_choices=EXAM_LANGUAGE_CHOICES,
            type_choices=filter_type_choices,
        ),
        "filter_count_label": pgettext("accounts.profile.question_bank", "Nəticə: %(n)d bank")
        % {"n": page_obj.paginator.count},
        "columns": ui.columns(is_center=is_center),
        "table_rows": ui.table_rows(rows, is_center=is_center),
        "table_state": "ready" if rows else "empty",
        "state_title": state_title,
        "state_body": state_body,
        "is_center": is_center,
        "can_create": can_create,
        "create_hidden": [{"name": "action", "value": "create_bank"}, {"name": "next", "value": create_next}],
        "edit_hidden": [{"name": "next", "value": back_url}],
        "create_action": reverse("exams:question_bank_list"),
        # Dialoq formalarına qoyulan atributlar (`_form_dialog.html`
        # `form_dialog_data` müqaviləsi) — köhnə JS çəngəlləri qorunur.
        "create_form_attrs": {"class": "js-qb-create-form"},
        "edit_form_attrs": {
            "id": "editBankForm",
            "data-subject-url": reverse("exams:subject_search"),
            "data-teacher-url": reverse("exams:bank_teacher_search"),
        },
    }

    return {
        "question_bank_banks": page_obj.object_list,
        "question_bank_page_obj": page_obj,
        "question_bank_search_query": params["search"],
        "question_bank_pagination_query": _query_string(
            section="question-bank",
            bank_search=params["search"],
            bank_kind=params["kind"],
            bank_lang=params["lang"],
            bank_format=params["format"],
        ),
        "question_bank_back_url": back_url,
        "question_bank_language_choices": EXAM_LANGUAGE_CHOICES,
        "question_bank_default_type_choices": type_choices,
        "question_bank_exam_kind_choices": exam_kind_choices,
        "question_bank_kind_filter": params["kind"],
        "question_bank_kind_pills": _kind_pills(params["search"], params["kind"], exam_kind_choices),
        # Mərkəz tam səlahiyyətli; müəllim öz şəxsi Quiz bankını yarada bilir.
        "question_bank_can_create": can_create,
        "question_bank_is_center": is_center,
        "question_bank_section": section,
    }
