"""«Lab qrupları» kabinet bölməsi — panel konteksti (sahib 2026-11-07).

Sahib: «lab qruplarını yarat modern üslub və dizaynda, sidebarda qruplar olan yerdə yerləşsin gərək. Belə yox …»
Əvvəl ekran yalnız jurnal başlığındakı çipdən açılan ayrıca səhifə idi. İndi sol menyuda «Qruplar»ın yanındadır
(müəllimin düz menyusunda «Elektron jurnal»ın altında): jurnalı seç → qruplar sütun-kart kimi, qrupsuz tələbələr,
seçib köçürmək (və ya sürüşdürüb atmaq), yaratmaq, ad vermək, boş qrupu silmək.

QAPI (fail-closed, hər render-də yenidən):

* menyu — ``rbac_sections`` (``lab_groups_section.visible``); bölmə açarı ``lab-groups``;
* siyahı — ``lab_groups_section.resolve_scope`` (``lab_groups_manage.can_manage`` ilə eyni mənbələr);
* seçilmiş jurnal — ``lab_groups_manage.can_manage`` (yoxdursa iş sahəsi açılmır, səbəb göstərilir);
* yazı — ``registrar:journal_lab_groups_action`` (eyni qapı + siyahı qapısı). «Başqasının adından» (view-as)
  rejimində iş sahəsi yalnız oxu üçündür.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import lab_groups_manage as service
from apps.registrar.public import lab_groups_section as journals

SECTION = "lab-groups"
CTX = "accounts.lab_groups"
#: «Qrupsuz et» seçiminin dəyəri (``registrar.lab_groups_views.UNASSIGN`` ilə eyni).
UNASSIGN = "none"


def section_url(params) -> str:
    return f"{reverse('accounts:profile')}?{urlencode({'section': SECTION, **params})}"


def _active_organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


# ── Süzgəc sahələri ──────────────────────────────────────────────────────────


def _select(name, label, options, value, *, searchable=False, all_label=None) -> dict:
    head = [] if all_label is False else [{"value": "", "label": all_label or pgettext(CTX, "Hamısı")}]
    return {
        "name": f"{journals.PREFIX}{name}",
        "label": label,
        "kind": "select",
        "value": value,
        "options": [*head, *options],
        "searchable": searchable,
    }


def _filter_fields(organization, scope, filters, base) -> list:
    fields = [
        {
            "name": f"{journals.PREFIX}q",
            "label": pgettext(CTX, "Axtarış"),
            "kind": "search",
            "value": filters.q,
            "placeholder": pgettext(CTX, "Fənn, kod, qrup və ya müəllim"),
            "wide": True,
        },
        _select(
            "period",
            pgettext(CTX, "Semestr"),
            journals.period_options(organization),
            filters.period,
            searchable=True,
            all_label=False,
        ),
    ]
    if not scope.is_personal:
        chairs = None if scope.org_wide else scope.chair_units
        fields += [
            _select(
                "faculty",
                pgettext(CTX, "Fakültə"),
                journals.unit_options(organization, journals.FACULTY_TYPES),
                filters.faculty,
                searchable=True,
            ),
            _select(
                "chair",
                pgettext(CTX, "Kafedra"),
                journals.unit_options(organization, journals.CHAIR_TYPES, within=chairs),
                filters.chair,
                searchable=True,
            ),
            _select(
                "teacher",
                pgettext(CTX, "Müəllim"),
                journals.teacher_options(base),
                filters.teacher,
                searchable=True,
            ),
        ]
    fields += [
        _select("group", pgettext(CTX, "Qrup"), journals.group_options(base), filters.group, searchable=True),
        _select("status", pgettext(CTX, "Vəziyyət"), journals.status_options(), filters.status),
    ]
    return fields


def _kpi_tiles(kpis) -> list:
    total, split = kpis.get("total", 0), kpis.get("split", 0)
    return [
        {"label": pgettext(CTX, "Lab saatlı jurnal"), "value": total, "tone": "accent-primary"},
        {
            "label": pgettext(CTX, "Qruplara bölünüb"),
            "value": split,
            "note": pgettext(CTX, "%(n)s jurnal hələ bölünməyib") % {"n": max(0, total - split)},
            "tone": "accent-success",
        },
        {
            "label": pgettext(CTX, "Qrupsuz tələbə"),
            "value": kpis.get("ungrouped", 0),
            "note": pgettext(CTX, "%(n)s jurnalda") % {"n": kpis.get("pending", 0)},
            "tone": "accent-warning" if kpis.get("ungrouped") else "accent-success",
        },
    ]


# ── İş sahəsi (seçilmiş jurnal) ──────────────────────────────────────────────


def _js_data(offering, blocked) -> dict:
    """İş sahəsinin data-atributları (CSP: inline JS yoxdur; mətnlər tərcümə olunmuş halda)."""
    return {
        "data-lgx-ws": "1",
        "data-action-url": reverse("registrar:journal_lab_groups_action", args=[offering.pk]),
        "data-unassign": UNASSIGN,
        "data-readonly": "1" if blocked else "0",
        "data-msg-generic": pgettext(CTX, "Əməliyyat alınmadı — yenidən cəhd edin."),
        "data-msg-pick": pgettext(CTX, "Əvvəlcə tələbələri seçin."),
        "data-msg-target": pgettext(CTX, "Hansı qrupa köçürüləcəyini seçin."),
        "data-msg-delete-title": pgettext(CTX, "Qrupu silmək"),
        "data-msg-delete-body": pgettext(
            CTX, "«%(label)s» silinəcək; onun %(n)s tələbəsi qrupsuz qalacaq. Davam edilsin?"
        ),
        "data-msg-delete-ok": pgettext(CTX, "Qrupu sil"),
    }


def _workspace(request, organization, filters, view_as) -> dict | None:
    offering, error = journals.selected_offering(request.user, organization, filters.offering)
    if offering is None:
        return {"error": error} if error else None
    panel = service.panel(offering)
    blocked = service.block_reason(offering)
    read_only = bool(blocked or view_as)
    grouped = panel["total"] - len(panel["ungrouped"])
    return {
        "offering": journals.offering_summary(offering),
        "panel": panel,
        "blocked_reason": blocked,
        "view_as": view_as,
        "can_edit": not read_only,
        "grouped": grouped,
        "pct": round(grouped * 100 / panel["total"]) if panel["total"] and panel["groups"] else 0,
        "journal_url": reverse("registrar:journal_detail", args=[offering.pk]),
        "close_url": section_url(filters.as_params(offering="")),
        "unassign_value": UNASSIGN,
        "data": _js_data(offering, read_only),
    }


# ── Panel ────────────────────────────────────────────────────────────────────


def build_panel_context(request) -> dict:
    organization = _active_organization(request)
    user = getattr(request, "user", None)
    scope = journals.resolve_scope(user, organization) if organization is not None else journals.NO_ACCESS
    panel = {
        "has_access": scope.has_access,
        "access_denied_message": pgettext(CTX, "Bu bölmə jurnalın müəllimi, kafedra müdiri və RİM rəhbəri üçündür."),
    }
    if not scope.has_access:
        return panel
    view_as = bool(getattr(request, "is_view_as", False))
    filters = journals.parse_filters(request.GET, organization)
    base = journals.base_queryset(user, organization, scope, filters)
    result = journals.page(user, organization, scope, filters)
    for row in result["rows"]:
        row["url"] = section_url(filters.as_params(offering=row["id"]))
        row["is_selected"] = row["id"] == filters.offering
    panel.update(
        section=SECTION,
        filters=filters,
        scope_personal=scope.is_personal,
        filter_fields=_filter_fields(organization, scope, filters, base),
        filter_count_label=pgettext(CTX, "Nəticə: %(n)s jurnal") % {"n": result["total"]},
        is_filtered=filters.is_filtered,
        kpi_tiles=_kpi_tiles(result["kpis"]),
        prev_url=section_url(filters.as_params(page=result["page"] - 1)) if result["has_prev"] else "",
        next_url=section_url(filters.as_params(page=result["page"] + 1)) if result["has_next"] else "",
        workspace=_workspace(request, organization, filters, view_as),
        **result,
    )
    return panel


__all__ = ["SECTION", "build_panel_context", "section_url"]
