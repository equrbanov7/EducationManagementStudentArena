"""«Tələbə reyestri» → «Hesab aktivləşdirmə» görünüşü (``sr_view=activation``, sahib 2026-10-03).

GLUE qatı: məntiq ``apps.accounts.services.people.activation``-dadır. Reyestrin filtrləri (fakültə,
ixtisas, qrup, qəbul ili …) olduğu kimi tətbiq olunur; cədvəl tələbələr əvəzinə QRUPLARI göstərir —
ən geri qalan qrup birinci. Hər sətirdə: «Siyahı» (reyestr bu qrup + «ilkin paroldadır» süzgəci ilə)
və «Çap vərəqi» (QR + addım-addım təlimat + aktivləşdirməyənlərin adı/istifadəçi adı, PAROLSUZ).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services.people import activation as activation_service

_CTX = "accounts.student_registry"


def _tone(pct: int) -> str:
    return "full" if pct >= 80 else "half" if pct >= 40 else "low"


def build_activation_view(request, section, *, actor, values, base_params) -> None:
    """``section["activation"]`` — qrup sətirləri, fakültə xülasəsi, ümumi faiz (yerində mutasiya)."""
    report = activation_service.activation_report(actor=actor, request=request, values=values)
    profile_url = reverse("accounts:profile")
    sheet_url = reverse("accounts:student_activation_sheet")
    keep = {key: value for key, value in base_params.items() if value not in ("", None) and key != "sr_view"}

    rows = []
    for row in report["rows"]:
        list_params = {**keep, "sr_group": row["group_id"], "sr_account": "initial"} if row["group_id"] else None
        rows.append(
            {
                **row,
                "group_label": row["group_name"] or pgettext(_CTX, "Qrupsuz"),
                "tone": _tone(row["pct"]),
                "list_url": f"{profile_url}?{urlencode(list_params)}" if list_params else "",
                "sheet_url": f"{sheet_url}?{urlencode({'group': row['group_id']})}" if row["group_id"] else "",
            }
        )

    totals = report["totals"]
    section["activation"] = {
        "rows": rows,
        "faculties": [{**item, "tone": _tone(item["pct"])} for item in report["faculties"]],
        "totals": totals,
        "tiles": [
            {
                "label": pgettext(_CTX, "AKTİVLƏŞDİRİB"),
                "value": f"{totals['pct']}%",
                "note": pgettext(_CTX, "%(done)d / %(total)d tələbə")
                % {"done": totals["activated"], "total": totals["total"]},
                "tone": "accent-primary",
            },
            {
                "label": pgettext(_CTX, "HƏLƏ İLKİN PAROLDA"),
                "value": totals["initial"],
                "tone": "warning" if totals["initial"] else None,
            },
            {
                "label": pgettext(_CTX, "HEÇ GİRMƏYİB"),
                "value": totals["never"],
                "note": pgettext(_CTX, "Sistemə bir dəfə də daxil olmayıb"),
            },
            {"label": pgettext(_CTX, "QRUP"), "value": len(rows)},
        ],
    }
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d qrup") % {"count": len(rows)}


def view_toggle_urls(base_params: dict) -> dict:
    """Başlıq düymələri: siyahı ↔ aktivləşdirmə (cari filtrlər qorunur, səhifə sıfırlanır)."""
    keep = {key: value for key, value in base_params.items() if value not in ("", None) and key != "sr_view"}
    profile_url = reverse("accounts:profile")
    return {
        "list_view_url": f"{profile_url}?{urlencode(keep)}",
        "activation_view_url": f"{profile_url}?{urlencode({**keep, 'sr_view': 'activation'})}",
    }


__all__ = ["build_activation_view", "view_toggle_urls"]
