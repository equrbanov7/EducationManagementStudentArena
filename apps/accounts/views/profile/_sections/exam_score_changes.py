"""Profil «exam-score-entry» — «Dəyişən nəticələr» alt-görünüşü (``?ese_view=changes``).

Sahibin tələbi (2026-09-14, W2 `w2paper`): «apellyasiyadan və ya nədənsə sonra
DƏYİŞƏN nəticələrin izlənməsi lazımdır». Tenantın bütün ``kind != initial``
``ExamScoreEntry`` sətirləri (sənədli düzəliş + apellyasiya nəticəsi) —
aktorun struktur əhatəsi ilə (siyahı ilə eyni qayda), filtrlərlə (qrup, fənn,
müəllim, növ, tarix aralığı, tələbə axtarışı), 50-lik səhifələmə, CSV ixracı
(``accounts:exam_score_changes_export``) və sətir-səviyyə «tarixçə» çekmecəsi.

Filtr həlli (:func:`resolve_changes_filters`) bölmə ilə ixrac view-u arasında
ORTAQDIR — «gördüyün cədvəl = endirdiyin fayl».
"""

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views._helpers.formatting import _append_query_params

SECTION = "exam-score-entry"
_CTX = "registrar.exam_score_entry"
PAGE_PARAM = "ese_page"


def _select_field(name, label, options, value, *, searchable=False, wide=False):
    return {
        "name": name,
        "label": label,
        "kind": "select",
        "options": options,
        "value": value,
        "searchable": searchable,
        "wide": wide,
    }


def _all_option(label):
    return {"value": "", "label": label}


def _pick(request, name, valid_ids) -> str:
    requested = (request.GET.get(name) or "").strip()
    return requested if requested in valid_ids else ""


def resolve_changes_filters(request, *, service, sheets_service, organization, period, allowed_group_ids):
    """GET-dən filtr dəyərlərini həll et → ``{"params": {...}, "fields": [...], "query": {...}}``.

    ``allowed_group_ids`` — ``None`` (org-wide) və ya unit-scoped aktorun qrup
    id-ləri: qrup seçicisi və müəllim siyahısı ona görə daralır.
    """
    changes = service.exam_score_changes
    groups = sheets_service.groups_for_period(organization=organization, period=period)
    if allowed_group_ids is not None:
        groups = [g for g in groups if g["id"] in allowed_group_ids]
    subjects = service.subjects_for_period(organization=organization, period=period)
    instructors = service.instructors_for_period(organization=organization, period=period, group_ids=allowed_group_ids)

    group_id = _pick(request, "ese_group", {g["id"] for g in groups})
    subject_id = _pick(request, "ese_subject", {s["id"] for s in subjects})
    teacher_id = _pick(request, "ese_teacher", {i["id"] for i in instructors})
    kind = _pick(request, "ese_kind", {row["value"] for row in changes.kind_options()})
    exam_kind = _pick(request, "ese_exam_kind", {row["value"] for row in changes.exam_kind_options() if row["value"]})
    date_from_raw = (request.GET.get("ese_from") or "").strip()
    date_to_raw = (request.GET.get("ese_to") or "").strip()
    date_from = changes.parse_date(date_from_raw)
    date_to = changes.parse_date(date_to_raw)
    search = (request.GET.get("ese_q") or "").strip()[:100]

    fields = [
        _select_field(
            "ese_group",
            pgettext(_CTX, "Qrup"),
            [_all_option(pgettext(_CTX, "Bütün qruplar"))] + [{"value": g["id"], "label": g["name"]} for g in groups],
            group_id,
            searchable=True,
        ),
        _select_field(
            "ese_subject",
            pgettext(_CTX, "Fənn"),
            [_all_option(pgettext(_CTX, "Bütün fənlər"))]
            + [{"value": s["id"], "label": f"{s['code']} — {s['name']}"} for s in subjects],
            subject_id,
            searchable=True,
            wide=True,
        ),
        _select_field(
            "ese_teacher",
            pgettext(_CTX, "Müəllim"),
            [_all_option(pgettext(_CTX, "Bütün müəllimlər"))]
            + [{"value": i["id"], "label": i["name"]} for i in instructors],
            teacher_id,
            searchable=len(instructors) > 8,
        ),
        _select_field("ese_kind", pgettext(_CTX, "Növ"), changes.kind_options(), kind),
        {"name": "ese_from", "label": pgettext(_CTX, "Tarixdən"), "kind": "date", "value": date_from_raw},
        {"name": "ese_to", "label": pgettext(_CTX, "Tarixədək"), "kind": "date", "value": date_to_raw},
        {
            "name": "ese_q",
            "label": pgettext(_CTX, "Tələbə axtarışı"),
            "kind": "search",
            "value": search,
            "placeholder": pgettext(_CTX, "ad · istifadəçi adı · FİN · tələbə №"),
        },
    ]
    params = {
        "ese_group": group_id,
        "ese_subject": subject_id,
        "ese_teacher": teacher_id,
        "ese_kind": kind,
        "ese_exam_kind": exam_kind,
        "ese_from": date_from_raw if date_from else "",
        "ese_to": date_to_raw if date_to else "",
        "ese_q": search,
    }
    query = {
        "period": period,
        "group_id": group_id,
        "subject_id": subject_id,
        "instructor_id": teacher_id,
        "kind": kind,
        "exam_kind": exam_kind,
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
    }
    return {"params": params, "fields": fields, "query": query}


def changes_queryset_for(request, *, service, organization, query, is_superadmin):
    """Əhatə + filtrlər → queryset (superadmin bütün təşkilatı görür)."""
    from django.db.models import Q

    changes = service.exam_score_changes
    scope = (
        Q(organization=organization)
        if is_superadmin
        else changes.scope_q(request.user, organization, permission=service.ENTRY_PERMISSION)
    )
    return changes.changes_queryset(scope=scope, **query)


def build_changes_view(
    request,
    section,
    filter_fields,
    *,
    service,
    sheets_service,
    organization,
    period,
    base_params,
    allowed_group_ids,
    is_superadmin,
):
    """Bölmə lüğətini «Dəyişən nəticələr» üçün doldur (``section`` yerində mutasiya)."""
    changes = service.exam_score_changes
    resolved = resolve_changes_filters(
        request,
        service=service,
        sheets_service=sheets_service,
        organization=organization,
        period=period,
        allowed_group_ids=allowed_group_ids,
    )
    filter_fields.extend(resolved["fields"])
    queryset = changes_queryset_for(
        request, service=service, organization=organization, query=resolved["query"], is_superadmin=is_superadmin
    )
    page = changes.paginate(queryset, request.GET.get(PAGE_PARAM))
    rows = [changes.change_row(entry) for entry in page.object_list]

    section["changes_page"] = page
    section["changes_rows"] = rows
    section["changes_total"] = page.paginator.count
    section["changes_page_param"] = PAGE_PARAM
    all_params = {**base_params, "ese_view": "changes", **resolved["params"]}
    section["changes_query"] = _append_query_params("", section=SECTION, **all_params).lstrip("?")
    # `base_params` təşkilat (superadmin), tədris ili və semestri daşıyır —
    # ixrac view-u dövrü bölmə ilə eyni heuristika ilə həll edir.
    section["changes_export_url"] = _append_query_params(
        reverse("accounts:exam_score_changes_export"),
        **base_params,
        **{key: value for key, value in resolved["params"].items() if value},
    )
    section["changes_count_label"] = "%s: %s" % (pgettext(_CTX, "Dəyişiklik"), page.paginator.count)
    current_kind = resolved["params"]["ese_exam_kind"]
    section["changes_kind_chips"] = [
        {
            "key": option["value"],
            "label": option["label"],
            "current": option["value"] == current_kind,
            "url": _append_query_params(
                reverse("accounts:profile"),
                section=SECTION,
                **{**all_params, "ese_exam_kind": option["value"]},
            ),
        }
        for option in changes.exam_kind_options()
    ]
    section["steps"] = []
    section["changes_columns"] = [
        {"key": "date", "label": pgettext(_CTX, "Tarix")},
        {"key": "student", "label": pgettext(_CTX, "Tələbə")},
        {"key": "subject", "label": pgettext(_CTX, "Fənn / qrup")},
        {"key": "exam_kind", "label": pgettext(_CTX, "İmtahan növü")},
        {"key": "delta", "label": pgettext(_CTX, "Köhnə → yeni"), "align": "num"},
        {"key": "kind", "label": pgettext(_CTX, "Növ")},
        {"key": "reason", "label": pgettext(_CTX, "Səbəb")},
        {"key": "by", "label": pgettext(_CTX, "Kim")},
        {"key": "doc", "label": pgettext(_CTX, "Sənəd")},
        {"key": "actions", "label": pgettext(_CTX, "Tarixçə"), "sr_only": True},
    ]


__all__ = ["PAGE_PARAM", "build_changes_view", "changes_queryset_for", "resolve_changes_filters"]
