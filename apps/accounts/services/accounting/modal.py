"""«Mühasibatlıq» — müəllim pəncərəsi (modal) konteksti (sahib 2026-10-19: «müəllimə klik → ətraflı modal»).

Qapı bölmə ilə EYNİDİR (``panel.resolve`` → ``policy.resolve_actor``: ``accounting.view`` + ``get_permission_scope``):
açarsız aktor → 403, əhatədən kənar / mövcud olmayan müəllim → 404 (fərqləndirilmir — mövcudluq sızdırılmır).
Dövr (ay / bütün semestr / tarix aralığı) və filtrlər panelin ``ac_*`` parametrlərindən gəlir — modal, KPI,
cədvəl və ixrac eyni rəqəmləri göstərir.

Sorğu büdcəsi SABİTDİR və digər müəllimlərin sayından asılı deyil: ``resolve_teacher`` (fakt / plan / şəxs
sorğuları yalnız HƏMİN müəllim üçün) + fənn × qrup 1 + dərslərin sayı və dilimi 2. Dərslər «Daha çox»
ilə ``LESSON_PAGE_SIZE`` qədər əlavə olunur (``ac_part=lessons`` yalnız sətirləri qaytarır — 2 sorğu + resolve).
Tələbə adı / qiyməti YOXDUR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from . import constants as C
from .detail import detail_core, find_row, lesson_list, period_label
from .panel import _url, detail_query, resolve_teacher

PART_LESSONS = "lessons"


@dataclass
class ModalResult:
    status: int
    error: str = ""
    context: dict = field(default_factory=dict)


def _more(resolved, teacher_id: int, page) -> dict:
    if not page.has_next():
        return {"more_url": "", "remaining": 0}
    path = reverse("accounts:accounting_teacher_detail", args=[teacher_id])
    query = detail_query(resolved.filters, lpage=page.number + 1)
    remaining = page.paginator.count - page.end_index()
    return {"more_url": f"{path}?{query}&{urlencode({'ac_part': PART_LESSONS})}", "remaining": remaining}


def teacher_modal(request, teacher_id: int, *, profile_base_url: str = "") -> ModalResult:
    resolved = resolve_teacher(request, teacher_id)
    if not resolved.actor.has_access:
        return ModalResult(403, "forbidden")
    if resolved.semester is None:
        return ModalResult(404, "no_semester")
    row = find_row(resolved, teacher_id)
    if row is None:
        return ModalResult(404, "teacher_not_found")
    filters = resolved.filters
    lessons = lesson_list(resolved, teacher_id, page_number=filters.lpage)
    page = lessons["page"]
    context = {
        "lessons": lessons["items"],
        "lessons_total": page.paginator.count,
        **_more(resolved, teacher_id, page),
    }
    if str(request.GET.get(f"{C.PARAM_PREFIX}part") or "") == PART_LESSONS:
        return ModalResult(200, context=context)
    base = profile_base_url or reverse("accounts:profile")
    view_as = resolved.actor.view_as
    export_query = urlencode(filters.as_params(page=1, lpage=1, teacher=str(teacher_id)))
    context.update(
        detail=detail_core(resolved, row),
        kind_labels=[str(label) for _key, label in C.KINDS],
        view_as=view_as,
        export_url="" if view_as else reverse("accounts:accounting_export") + "?" + export_query,
        page_url=_url(base, filters, teacher=str(teacher_id), lpage=1),
        title=row["name"],
        subtitle=" · ".join(
            part
            for part in (
                row.get("position") or "",
                row["chair"] or "",
                row["faculty"] or "",
                pgettext(C.CTX, "Dövr: {period}").format(period=period_label(filters, resolved.semester)),
            )
            if part
        ),
    )
    return ModalResult(200, context=context)


__all__ = ["ModalResult", "PART_LESSONS", "teacher_modal"]
