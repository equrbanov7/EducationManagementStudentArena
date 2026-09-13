"""«Göstəricilər (CSV)» — rol-aware statistika göstəricilərinin ixracı.

Codex audit §7 (2026-09-13): «Statistik CSV əvvəlki göndəriş selector-larını
ixrac edir; düymə "Göndərişlər (CSV)" adlandırıldı». Köhnə ixrac
(`statistics_export.py`) köhnə `statistics_selectors` xülasəsini verir — ekranda
görünən yeni rol-aware kartlar/bloklar (`services/statistics_metrics/`) ona
düşmür. Bu modul İKİNCİ ixracdır: ekranda göstərilən `statistics_data`-nın
(KPI kartları, paylanma zolaqları, cədvəllər, RİM rəhbərinin «İmtahan mərkəzi»
alt-bölməsi, superadmin təşkilat müqayisəsi) uzun («tidy») formatda CSV-si.

Əhatə qaydası: rəqəmlər dashboard ilə EYNİ yoldan gəlir —
`_sections.statistics._compute_dashboard` (profil həlli, `statistics_scope`
(P1-11), superadmin təşkilat süzgəci, keş açarları) təkrar yazılmır və heç
vaxt daha geniş əhatə ilə yenidən hesablanmır.

Təhlükəsizlik: UTF-8 BOM (Excel), düstur-inyeksiyası neytrallaşdırılır
(`registrar.exam_score_import.export_text` — mövcud ixrac köməkçisi, ictimai
fasad üzərindən). Audit/rate-limit köhnə ixrac ilə eyni: `login_required` +
bölmə icazəsi (`allowed_sections`) → 404.
"""

from __future__ import annotations

import csv
import io

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.utils.translation import pgettext

from apps.registrar.public import exam_score_import

from ...models import UserProfile
from .._helpers import _get_active_organization, _role_capabilities
from ._sections.statistics import _compute_dashboard, _read_filters, _resolve_profile, statistics_scope

#: Excel-in UTF-8 CSV-ni düzgün açması üçün BOM.
UTF8_BOM = "\ufeff"


def _t(text: str) -> str:
    return pgettext("profile.statistics", text)


def _safe(value) -> str:
    """Boş → "", düstur başlanğıcı (= + - @ və ağ boşluq) → apostrof prefiksi."""
    return exam_score_import.export_text("" if value is None else value)


def _cell_text(cell) -> str:
    """Cədvəl xanası: `cell()` / `chip()` lüğəti və ya düz mətn."""
    if isinstance(cell, dict):
        return str(cell.get("text", "") or "")
    return "" if cell is None else str(cell)


def _block_rows(prefix: str, block: dict) -> list[list[str]]:
    """Bir blok → sətirlər: paylanma zolağı = 1 sətir; cədvəl = (sətir × sütun)."""
    title = block.get("title") or ""
    section = f"{prefix} · {title}" if prefix else title
    rows: list[list[str]] = []
    for bar in block.get("bars") or []:
        rows.append([section, "", bar.get("label"), bar.get("value_label"), "", bar.get("sub")])
    # `_data_table.html` müqaviləsi: `columns[0]` sətir-başlığı (`row_head`) sütunudur,
    # `cells[i]` isə `columns[i + 1]`-ə uyğundur.
    columns = block.get("columns") or []
    cell_columns = columns[1:] if columns else []
    for row in block.get("rows") or []:
        head = row.get("row_head") or ""
        cells = row.get("cells") or []
        for index, cell in enumerate(cells):
            column = cell_columns[index]["label"] if index < len(cell_columns) else ""
            rows.append([section, head, column, _cell_text(cell), "", ""])
    return rows


def _kpi_rows(section: str, tiles) -> list[list[str]]:
    return [
        [section, "", tile.get("label"), tile.get("value"), tile.get("unit"), tile.get("note")] for tile in tiles or []
    ]


def _org_comparison_rows(rows) -> list[list[str]]:
    """Superadmin təşkilat müqayisəsi — ekranda səhifələnir, CSV-də tam siyahı."""
    section = _t("Təşkilatlar")
    out: list[list[str]] = []
    for row in rows or []:
        for key, label in (("members", _t("Üzvlər")), ("exams", _t("İmtahanlar")), ("attempts", _t("Cəhdlər"))):
            out.append([section, row.get("name"), label, row.get(key), "", ""])
    return out


def _context_rows(profile: str, presented: dict) -> list[list[str]]:
    """Başlıq metaməlumatı: profil, əhatə, dövr — oxuyan hansı mənzərəyə baxdığını bilsin."""
    window = presented.get("window") or {}
    period = window.get("period_name") or ""
    date_from = window.get("date_from") or ""
    date_to = window.get("date_to") or ""
    span = " – ".join(part for part in (date_from, date_to) if part)
    section = _t("Kontekst")
    return [
        [section, "", _t("Profil"), profile, "", ""],
        [section, "", _t("Əhatə"), presented.get("scope_label"), "", ""],
        [section, "", _t("Dövr"), period, "", span],
    ]


def build_metrics_csv_rows(profile: str, presented: dict) -> list[list[str]]:
    """`statistics_data` (presenter çıxışı) → CSV sətirləri (başlıq daxil)."""
    rows: list[list[str]] = [
        [_t("Bölmə"), _t("Sətir"), _t("Göstərici"), _t("Dəyər"), _t("Vahid"), _t("Qeyd")],
    ]
    rows.extend(_context_rows(profile, presented))
    rows.extend(_kpi_rows(_t("Əsas göstəricilər"), presented.get("kpis")))
    for block in presented.get("blocks") or []:
        rows.extend(_block_rows("", block))
    for extra in presented.get("extra") or []:
        extra_title = extra.get("title") or ""
        rows.extend(_kpi_rows(extra_title, extra.get("kpis")))
        for block in extra.get("blocks") or []:
            rows.extend(_block_rows(extra_title, block))
    rows.extend(_org_comparison_rows(presented.get("org_comparison")))
    return [[_safe(value) for value in row] for row in rows]


@login_required
def statistics_export_metrics_csv(request):
    """Cari aktorun ekranda gördüyü rol-aware göstəriciləri CSV kimi endir."""
    # GET ilə heç nə YAZILMIR (view-as qapısı `MutatingGetRouteScanTests`): profil
    # yoxdursa yaradılmır — `_role_capabilities` `None`-u adi üzv kimi oxuyur.
    profile_obj = UserProfile.objects.filter(user=request.user).first()
    capabilities = _role_capabilities(request.user, profile_obj)
    if "statistics" not in capabilities["allowed_sections"]:
        raise Http404

    organization = _get_active_organization(request)
    filters = _read_filters(request, is_superadmin=capabilities["is_superadmin"])
    scope = None
    if organization is not None and not capabilities["is_superadmin"]:
        scope = statistics_scope(request, organization)
    profile = _resolve_profile(capabilities, organization=organization, scope=scope)
    presented, _courses, _orgs = _compute_dashboard(
        request,
        capabilities=capabilities,
        profile=profile,
        organization=organization,
        scope=scope,
        filters=filters,
    )

    output = io.StringIO()
    output.write(UTF8_BOM)
    writer = csv.writer(output)
    writer.writerows(build_metrics_csv_rows(profile, presented))

    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="statistics_metrics.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
