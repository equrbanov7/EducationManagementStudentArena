"""Profil «teaching-handover» bölməsi — fənnin başqa müəllimə təhvili.

2026-09-09 (sahib: «bu fənn təhvili yerini düzəlt, modern UX/UI və proses çox
aydın olsun; performans baxımından da çox kəskin»): bölmə SPA çərçivəsindən
`ems_ui` SERVER-RENDER panelinə keçirildi.

──────────────────────────────────────────────────────────────────────────────
NİYƏ SERVER-RENDER?
──────────────────────────────────────────────────────────────────────────────
Köhnə axın boş çərçivə göndərib cədvəli, süzgəc açılışlarını və tarixçəni ÜÇ
ayrı JSON sorğusu ilə çəkirdi — ilk mənalı görüntüyə qədər 4 gediş-gəliş, hər
biri eyni icazə/əhatə hesablamasını təkrarlayırdı. İndi panel bir sorğuda gəlir;
JSON endpoint-ləri (`apps/accounts/views/handover/api.py`) müqavilə kimi
QALIR — müəllim seçicisi və xarici istehlakçılar onları oxuyur.

TAB-LAR LAZY-dir: `handover_tab=history` verilməyibsə tarixçə ÜMUMİYYƏTLƏ
sorğulanmır (və əksinə) — «hansı tab açıqdırsa onun qiyməti ödənilir» qaydası.

⚠️ QAYDALAR BURADA DEYİL. İcazə, əhatə, bloker və audit `apps.registrar.handover`
/ `handover_actions`-dadır; bu modul yalnız onların cavabını ekrana yığır.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (`handover_section`)
──────────────────────────────────────────────────────────────────────────────
    has_access, access_denied_message, scope_label, header_subtitle
    action_url                     — POST (təhvil + geri qaytarma)
    teachers_url … max_bulk_rows   — köhnə JSON müqaviləsi (dəyişməz)
    tab, tabs, tabs_label
    steps, kpi_tiles, filter_fields, filter_count_label
    banner_*                       — aqreqat bloker lenti
    columns, table_rows, table_state, page_obj, pagination_query
    history_*                      — YALNIZ tarixçə tabında dolur
    target_options, confirm_hidden, revert_hidden, form_data
"""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.views.handover import filters as handover_filters
from apps.registrar import handover as handover_read
from apps.registrar import handover_query

from . import handover_rows as rows_ui
from . import handover_ui as ui

_CTX = "accounts.handover"


def build_handover_section(request, section, *, active_organization, allowed_sections, active_section):
    """``section`` dict-ini YERİNDƏ mutasiya edir (kollokvium/journal-close naxışı)."""
    if "teaching-handover" not in allowed_sections or active_section != "teaching-handover":
        return

    from ...handover.api import DEFAULT_PAGE_SIZE

    has_access = bool(active_organization is not None and handover_read.can_reassign(request.user, active_organization))
    section["has_access"] = has_access
    section["access_denied_message"] = pgettext(
        _CTX, "Fənn təhvili üçün icazəniz yoxdur — bu bölmə yalnız səlahiyyətli rollar üçündür."
    )
    section["teachers_url"] = reverse("accounts:handover_teachers")
    section["offerings_url"] = reverse("accounts:handover_offerings")
    section["options_url"] = reverse("accounts:handover_options")
    section["history_url"] = reverse("accounts:handover_history")
    section["action_url"] = reverse("accounts:handover_action")
    section["default_page_size"] = DEFAULT_PAGE_SIZE
    section["min_reason_length"] = handover_read.MIN_REASON_LENGTH
    section["max_reason_length"] = handover_read.MAX_REASON_LENGTH
    section["max_bulk_rows"] = handover_write_limit()

    if not has_access:
        return

    scope = handover_read.actor_scope(request.user, active_organization)
    section["scope_label"] = (
        pgettext(_CTX, "Bütün universitet") if scope.is_org_wide else pgettext(_CTX, "Yalnız öz struktur bölmələriniz")
    )
    section["header_subtitle"] = pgettext(
        _CTX,
        "Müəllim işdən çıxdıqda və ya dərs yükü dəyişdikdə fənnin elektron jurnalını başqa müəllimə verin. "
        "Yazılmış bal və davamiyyət olduğu kimi qalır — yalnız jurnalın sahibi dəyişir.",
    )
    section["header_note"] = pgettext(_CTX, "Səlahiyyət sahəniz: %(scope)s") % {"scope": section["scope_label"]}

    tab = ui.active_tab(request)
    section["tab"] = tab
    section["tabs"] = [
        {"key": ui.TAB_TRANSFER, "label": pgettext(_CTX, "Təhvil"), "current": tab == ui.TAB_TRANSFER},
        {"key": ui.TAB_HISTORY, "label": pgettext(_CTX, "Tarixçə"), "current": tab == ui.TAB_HISTORY},
    ]
    section["tabs_label"] = pgettext(_CTX, "Fənn təhvili bölmələri")
    # `ems_ui/_skeleton_rows.html` sətir sayını KONTEKSTDƏN oxuyur (şablonda
    # `range` yaratmaq mümkün deyil); verilməsə skeleton BOŞ render olunur.
    section["skeleton_range"] = range(6)
    section["tab_param"] = ui.TAB_PARAM
    section["prefix"] = ui.PREFIX
    section["form_data"] = {"data-tof-form": "handover"}
    # Seçilmiş sətirlər dialoq açılanda GİZLİ `offering_ids` sahələri kimi
    # yazılır (teaching_handover.js) — burada yalnız sabit əməl açarı var.
    section["confirm_hidden"] = [{"name": "action", "value": "reassign", "keep": True}]
    section["revert_hidden"] = [
        {"name": "action", "value": "revert", "keep": True},
        {"name": "handover_id", "value": ""},
    ]

    if tab == ui.TAB_HISTORY:
        _build_history(request, section, actor=request.user, organization=active_organization)
    else:
        _build_transfer(request, section, actor=request.user, organization=active_organization, scope=scope)


def handover_write_limit() -> int:
    from apps.registrar import handover_actions as handover_write

    return handover_write.MAX_BULK_ROWS


# ── «Təhvil» tabı ────────────────────────────────────────────────────────────


def _build_transfer(request, section, *, actor, organization, scope):
    from core.constants import OrgUnitType

    values = ui.filter_values(request)
    base = handover_read.scoped_offerings(actor, organization)
    filtered = handover_filters.apply_filters(base, values, organization=organization, actor=actor)

    facets = handover_query.blocker_facets(filtered, actor=actor)
    page_obj = Paginator(handover_query.list_queryset(filtered), ui.PAGE_SIZE).get_page(
        request.GET.get(ui.PREFIX + "page")
    )
    table_rows = rows_ui.offering_rows(page_obj.object_list, actor=actor, organization=organization)

    section["steps"] = ui.steps(values, facets)
    section["steps_label"] = pgettext(_CTX, "Təhvil mərhələləri")
    section["kpi_tiles"] = ui.kpi_tiles(facets)
    section["filter_fields"] = ui.filter_fields(
        values,
        sources=ui.source_teacher_options(base, values["teacher"]),
        periods=ui.period_options(organization, values["period"]),
        faculties=ui.unit_options(organization, scope, (OrgUnitType.FACULTY,), values["faculty"]),
        kafedras=ui.unit_options(organization, scope, (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT), values["kafedra"]),
    )
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(n)d fənn") % {"n": facets["total"]}
    section["columns"] = rows_ui.columns()
    section["table_rows"] = table_rows
    section["table_state"] = "ready" if table_rows else "empty"
    section["page_obj"] = page_obj
    section["pagination_query"] = _pagination_query(values, ui.TAB_TRANSFER)
    section["target_options"] = ui.target_teacher_options(organization)
    section["has_blocked"] = bool(facets["blocked"])
    # AQREQAT lent: «3 fənn təhvil verilə bilməz: 2 bağlı jurnal, 1 keçmiş
    # semestr» — qırmızı mətn divarı əvəzinə bir cümlə (sətrin öz səbəbi
    # cədvəldə, badge-in altındadır).
    section["blocked_title"] = pgettext(_CTX, "%(n)d fənn təhvil verilə bilməz") % {"n": facets["blocked"]}
    breakdown = ui.blocker_breakdown(facets)
    hint = pgettext(_CTX, "Səbəb hər sətirdə yazılıb. Bağlı jurnal üçün əvvəlcə RİM semestri açmalıdır.")
    section["blocked_body"] = f"{breakdown} — {hint}" if breakdown else hint
    _empty_state(section, filtered_by=any(values.values()))


def _empty_state(section, *, filtered_by: bool):
    if filtered_by:
        section["state_title"] = pgettext(_CTX, "Bu süzgəclərə uyğun fənn tapılmadı.")
        section["state_body"] = pgettext(_CTX, "Süzgəci dəyişin və ya «Sıfırla» ilə tam siyahıya qayıdın.")
    else:
        section["state_title"] = pgettext(_CTX, "Səlahiyyət sahənizdə dərs açılışı yoxdur")
        section["state_body"] = pgettext(_CTX, "Semestr açıldıqdan sonra fənlər burada görünəcək.")


# ── «Tarixçə» tabı ───────────────────────────────────────────────────────────


def _build_history(request, section, *, actor, organization):
    queryset = handover_read.scoped_history(actor, organization)
    page_obj = Paginator(queryset, ui.HISTORY_PAGE_SIZE).get_page(request.GET.get(ui.PREFIX + "page"))
    history = rows_ui.history_rows(page_obj.object_list, organization=organization)
    section["history_columns"] = rows_ui.history_columns()
    section["history_rows"] = history
    section["history_state"] = "ready" if history else "empty"
    section["page_obj"] = page_obj
    section["pagination_query"] = _pagination_query({}, ui.TAB_HISTORY)
    section["state_title"] = pgettext(_CTX, "Hələ təhvil qeydi yoxdur.")
    section["state_body"] = pgettext(_CTX, "İlk təhvildən sonra kim, nə vaxt və niyə dəyişdiyi burada qalır.")
    section["history_subtitle"] = pgettext(
        _CTX, "Kim, nə vaxt, hansı fənni kimdən kimə verib. Səhv təyinat geri qaytarıla bilər."
    )


def _pagination_query(values, tab) -> str:
    params = {ui.PREFIX + key: value for key, value in (values or {}).items() if value}
    params["section"] = "teaching-handover"
    if tab != ui.TAB_TRANSFER:
        params[ui.TAB_PARAM] = tab
    return urlencode(params)


__all__ = ["build_handover_section"]
