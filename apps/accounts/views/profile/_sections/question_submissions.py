"""Profil "question-submissions" bölməsi üçün context-fragment qurucusu.

Müəllim: öz göndərişləri — axtarış + status filtri + səhifələmə.
İmtahan mərkəzi: təşkilatın bütün göndərişləri EYNİ bölmədə inline filtrlənir
(ayrıca "qutu" səhifəsi yoxdur): axtarış, status, fakültə/kafedra (OrgUnit
subtree), müəllim, tədris ili/semestr (AcademicPeriod tarix aralığı —
göndərişdə dövr FK-sı yoxdur, ona görə ``created_at`` aralığa salınır) və dil.

2026-09-09 (sahib: «sual göndərişləri … modern UX/UI»): ekran `ems_ui`
komponentlərinə keçdi — KPI kartları klik edilə bilən status filtrləridir,
filtrlər AVTO panelə köçdü, siyahı cədvəl + status badge-dir, sətrin «yolu»
isə çekmecədə açılır.  Təqdimat modeli ``question_submissions_ui.py``-dədir.

Bütün GET parametrləri ``qsub_`` prefikslidir ki, digər profil bölmələrinin
parametrləri ilə toqquşmasın və filtr panelinin «Sıfırla»-sı yalnız bu bölməni
sıfırlasın.
"""

from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext

from . import question_submissions_ui as ui

PAGE_SIZE = 10

# Status FİLTRLƏRİ artıq QRUPLARDIR: yeni zəncirdə (müəllim → kafedra → mərkəz)
# bir kartın arxasında bir neçə texniki status dayanır.  Açar → status siyahısı.
_STATUS_GROUPS = {
    "at_chair": ("submitted_to_chair",),
    "at_center": ("chair_approved", "center_review"),
    "accepted": ("accepted",),
    "returned": ("chair_revision", "center_revision", "rejected"),
}
_STATUS_VALUES = tuple(_STATUS_GROUPS)

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
        "question_submissions_rejected_count": 0,
        "question_submissions_create_url": "",
        "question_submissions_clear_url": "",
        "question_submissions_pagination_query": "",
        "question_submissions_section": {},
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


def _applied_chips(filters, *, faculty, kafedra, teacher, period, languages) -> list:
    """Tətbiq olunmuş reviewer filtrləri — panelin «×» ilə silinən çipləri."""
    lang_map = dict(languages)
    labels = {
        "faculty": (pgettext("accounts.profile.question_submissions", "Fakültə"), faculty.name if faculty else ""),
        "kafedra": (pgettext("accounts.profile.question_submissions", "Kafedra"), kafedra.name if kafedra else ""),
        "teacher": (
            pgettext("accounts.profile.question_submissions", "Müəllim"),
            (teacher.get_full_name() or teacher.username) if teacher else "",
        ),
        "year": (pgettext("accounts.profile.question_submissions", "Tədris ili"), filters["year"]),
        "period": (pgettext("accounts.profile.question_submissions", "Semestr"), period.name if period else ""),
        "lang": (pgettext("accounts.profile.question_submissions", "Dil"), lang_map.get(filters["lang"], "")),
    }
    chips = []
    for key, param in _FILTER_PARAMS.items():
        if not filters[key]:
            continue
        title, value = labels[key]
        chips.append({"name": param, "label": title, "value_label": value or "—"})
    return chips


#: Hadisə növü → timeline nöqtəsinin tonu (`ems_ui/timeline.css`).
_EVENT_TONES = {
    "chair_approved": "success",
    "center_accepted": "success",
    "chair_revision": "warning",
    "center_revision": "warning",
    "chair_rejected": "danger",
    "center_rejected": "danger",
    "center_opened": "info",
}


def _events(submission) -> list:
    return [
        {
            "action": str(event.get_action_display()),
            "actor": event.actor_label or "—",
            "date": event.created_at.strftime("%d.%m.%Y %H:%M"),
            "reason": event.reason or "",
            "tone": _EVENT_TONES.get(event.action, "neutral"),
        }
        for event in submission.events.all()
    ]


def _meta(submission, *, is_reviewer: bool) -> list:
    """Çekmecədəki «kim / nə / harada» sətirləri."""
    rows = [
        (pgettext("accounts.profile.question_submissions", "Fənn"), submission.subject or "—"),
        (pgettext("accounts.profile.question_submissions", "Qrup"), submission.group_label or "—"),
        (pgettext("accounts.profile.question_submissions", "Dil"), str(submission.get_language_display())),
    ]
    if submission.exam_kind:
        rows.insert(
            1,
            (
                pgettext("accounts.profile.question_submissions", "İmtahan növü"),
                str(submission.get_exam_kind_display()),
            ),
        )
    if is_reviewer:
        rows.insert(
            0,
            (
                pgettext("accounts.profile.question_submissions", "Müəllim"),
                submission.teacher.get_full_name() or submission.teacher.username,
            ),
        )
    if submission.resubmission_count:
        rows.append(
            (pgettext("accounts.profile.question_submissions", "Təkrar göndəriş"), f"×{submission.resubmission_count}")
        )
    if submission.chair_note:
        rows.append((pgettext("accounts.profile.question_submissions", "Kafedra qeydi"), submission.chair_note))
    if submission.reviewer_note:
        rows.append((pgettext("accounts.profile.question_submissions", "Mərkəzin qeydi"), submission.reviewer_note))
    return [{"label": label, "value": value} for label, value in rows]


def _bank_note(submission, *, is_reviewer: bool):
    """Qəbul olunmuş göndərişin yazıldığı bank (mətn + opsional keçid)."""
    bank = submission.accepted_bank
    if submission.status != "accepted" or bank is None:
        return None
    text = pgettext("accounts.profile.question_submissions", "Suallar «%(bank)s» bankına əlavə olunub") % {
        "bank": bank.name
    }
    url = ""
    if is_reviewer and bank.is_active:
        url = reverse("exams:question_bank_detail", args=[submission.accepted_bank_id])
    return {"text": text, "url": url}


def _row(submission, *, is_reviewer: bool) -> dict:
    teacher = submission.teacher
    open_url = reverse(
        "exams:question_submission_review" if is_reviewer else "exams:question_submission_detail",
        args=[submission.id],
    )
    can_edit = not is_reviewer and submission.can_be_edited_by_teacher
    return {
        "id": str(submission.id),
        "title": submission.title,
        "subject": submission.subject or "—",
        "group": submission.group_label or "—",
        "teacher": teacher.get_full_name() or teacher.username,
        "status": submission.status,
        "status_badge": ui.status_badge(submission.status, is_reviewer=is_reviewer),
        "question_count": submission.question_count,
        "error_count": submission.error_count,
        "warning_count": submission.warning_count,
        "created": submission.created_at.strftime("%d.%m.%Y %H:%M"),
        "open_url": open_url,
        "can_edit": can_edit,
        "edit_url": reverse("exams:question_submission_detail", args=[submission.id]) if can_edit else "",
        "delete_url": reverse("exams:question_submission_delete", args=[submission.id]) if can_edit else "",
        "bank_note": _bank_note(submission, is_reviewer=is_reviewer),
        "drawer_meta": _meta(submission, is_reviewer=is_reviewer),
        "events": _events(submission),
    }


def _reviewer_sources(organization, filters, scoped):
    """Mərkəz filtrlərinin mənbələri + seçilmiş obyektlər (tək yerdə)."""
    from django.contrib.auth import get_user_model

    from apps.organizations.models import AcademicPeriod, OrgUnit
    from apps.organizations.structure_views.constants import KAFEDRA_UNIT_TYPES
    from core.constants import OrgUnitType

    faculties = list(OrgUnit.active.filter(organization=organization, unit_type=OrgUnitType.FACULTY).order_by("name"))
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
    return {
        "faculties": faculties,
        "kafedras": kafedras,
        "teachers": teachers,
        "periods": periods,
        "year_periods": year_periods,
        "years": years,
        "selected": {"faculty": faculty, "kafedra": kafedra, "teacher": teacher, "period": period},
    }


def _option_pairs(sources, *, languages, filters) -> dict:
    """Filtr paneli üçün (value, label) cütləri."""
    if not sources:
        return {}
    return {
        "faculties": [(str(unit.pk), unit.name) for unit in sources["faculties"]],
        "kafedras": [(str(unit.pk), unit.name) for unit in sources["kafedras"]],
        "teachers": [(str(user.pk), user.get_full_name() or user.username) for user in sources["teachers"]],
        "years": [(year, year) for year in sources["years"]],
        "periods": [
            (
                str(period.pk),
                period.name if filters["year"] else f"{period.name} · {period.academic_year}",
            )
            for period in sources["periods"]
        ],
        "languages": list(languages),
    }


def build_question_submissions_context(request, *, allowed_sections, active_section) -> dict:
    if not (active_section == "question-submissions" and "question-submissions" in allowed_sections):
        return _inactive_defaults()

    from django.core.paginator import Paginator
    from django.db.models import Count, Q

    from apps.exams.constants import EXAM_LANGUAGE_CHOICES
    from apps.exams.models import QuestionSubmission
    from apps.exams.public import is_exam_center_user
    from core.tenancy import get_request_organization

    organization = get_request_organization(request)
    if organization is None:
        return _inactive_defaults()

    is_reviewer = is_exam_center_user(request.user)
    scoped = QuestionSubmission.objects.filter(organization=organization)
    if is_reviewer:
        # MƏRKƏZ YALNIZ kafedra təsdiqindən keçmiş göndərişləri görür — kafedrada
        # gözləyən/qaytarılan dəst mərkəz üçün MÖVCUD DEYİL (fail-closed).
        scoped = scoped.filter(reached_center_at__isnull=False)
    else:
        scoped = scoped.filter(teacher=request.user)

    # KPI kartları üçün saylar — filtrsiz skop, TƏK aqreqat sorğu.
    counts = scoped.aggregate(
        total=Count("id"),
        at_chair=Count("id", filter=Q(status__in=_STATUS_GROUPS["at_chair"])),
        at_center=Count("id", filter=Q(status__in=_STATUS_GROUPS["at_center"])),
        accepted=Count("id", filter=Q(status__in=_STATUS_GROUPS["accepted"])),
        returned=Count("id", filter=Q(status__in=_STATUS_GROUPS["returned"])),
    )
    counts = {key: value or 0 for key, value in counts.items()}

    filters = _read_filters(request, is_reviewer=is_reviewer)
    sources = _reviewer_sources(organization, filters, scoped) if is_reviewer else None
    if filters["lang"] and filters["lang"] not in {code for code, _ in EXAM_LANGUAGE_CHOICES}:
        filters["lang"] = ""

    # ── Siyahı queryset-i: axtarış + status + reviewer filtrləri ──
    filtered = scoped
    if filters["status"]:
        filtered = filtered.filter(status__in=_STATUS_GROUPS[filters["status"]])
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
        selected = sources["selected"]
        filtered = _apply_reviewer_filters(
            filtered,
            filters,
            faculty=selected["faculty"],
            kafedra=selected["kafedra"],
            periods=sources["periods"],
            year_periods=sources["year_periods"],
        )

    filtered = (
        filtered.select_related("teacher", "accepted_bank", "chair_unit", "chair_reviewer")
        # Çekmecə hadisə lentini göstərir — N+1 olmasın.
        .prefetch_related("events__actor")
        .distinct()
        .order_by("-created_at", "-id")
    )
    page = Paginator(filtered, PAGE_SIZE).get_page(request.GET.get("qsub_page"))
    rows = [_row(item, is_reviewer=is_reviewer) for item in page.object_list]

    # ── Query string-lər: aktiv parametrlər (page-siz) ──
    active_params = {"qsub_q": filters["q"], "qsub_status": filters["status"]}
    for key, param in _FILTER_PARAMS.items():
        active_params[param] = filters[key] if is_reviewer else ""
    has_filters = any(filters[key] for key in _FILTER_PARAMS) or bool(filters["q"] or filters["status"])
    selected = sources["selected"] if sources else {}
    state_title, state_body = ui.states(has_filters=has_filters, is_reviewer=is_reviewer)

    section = {
        "subtitle": ui.subtitle(is_reviewer=is_reviewer),
        "is_reviewer": is_reviewer,
        # Mərkəz göndəriş yaratmır — başlıq əməli qutusu boş render olunmasın.
        "header_actions": ("" if is_reviewer else "exams/teacher/partials/question_submissions/_header_actions.html"),
        "kpi_tiles": ui.kpi_tiles(counts, active_status=filters["status"], is_reviewer=is_reviewer),
        "filter_fields": ui.filter_fields(
            filters=filters,
            is_reviewer=is_reviewer,
            sources=_option_pairs(sources, languages=EXAM_LANGUAGE_CHOICES, filters=filters),
        ),
        "filter_applied": (
            _applied_chips(
                filters,
                faculty=selected.get("faculty"),
                kafedra=selected.get("kafedra"),
                teacher=selected.get("teacher"),
                period=selected.get("period"),
                languages=EXAM_LANGUAGE_CHOICES,
            )
            if is_reviewer
            else []
        ),
        "filter_count_label": pgettext("accounts.profile.question_submissions", "Nəticə: %(n)d göndəriş")
        % {"n": page.paginator.count},
        "columns": ui.columns(is_reviewer=is_reviewer),
        "table_rows": ui.table_rows(rows, is_reviewer=is_reviewer),
        "table_state": "ready" if rows else "empty",
        "drawer_data": ui.drawer_data(rows),
        "state_title": state_title,
        "state_body": state_body,
        # Boş ekranda əsas addım düymə kimi görünür (müəllim, filtrsiz hal).
        "state_action_label": (
            pgettext("accounts.profile.question_submissions", "Yeni göndəriş")
            if not (is_reviewer or has_filters or counts["total"])
            else ""
        ),
        "state_action_url": reverse("exams:question_submission_create"),
        "returned_count": counts["returned"],
    }

    return {
        "question_submissions_items": rows,
        "question_submissions_page": page,
        "question_submissions_is_reviewer": is_reviewer,
        "question_submissions_total_count": counts["total"],
        # Müəllim üçün "düzəliş gözləyən", mərkəz üçün "rədd edilmiş" mənasında.
        "question_submissions_rejected_count": counts["returned"],
        "question_submissions_create_url": reverse("exams:question_submission_create"),
        "question_submissions_clear_url": f"{reverse('accounts:profile')}?section=question-submissions",
        "question_submissions_pagination_query": _profile_query(active_params),
        "question_submissions_section": section,
    }
