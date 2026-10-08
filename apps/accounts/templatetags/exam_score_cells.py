"""`exam_score_cells` — «İmtahan balı» siyahısının S1..S10 sual xanaları (bir sətir, bir çağırış).

NİYƏ Python-da? 2026-10-08 tutum testi (300 müəllim, 10 app × 1 CPU): «jf exam-score
page» p50 3.8 s idi, app CPU-ları 100 %. Siyahı sətir başına 10 xana render edir; hər
xanada ~20 şablon düyünü (dəyişən həlli, `if`, filtr) — 60 tələbəlik qrupda 600 xana
× 20 düyün Django şablon mühərrikində səhifənin ən bahalı hissəsi idi. Markup DƏYİŞMƏYİB
(`_roster.html`-in əvvəlki xana bloku ilə eyni atributlar/siniflər); burada yalnız sətir
başına BİR dəfə, ``format_html`` ilə (dəyərlər escape olunur) yığılır.

Kontrakt (`exam_score_entry.js`): select-də YALNIZ «—» + seçilmiş dəyər var,
``data-max=""`` — JS ``applyQuestionGrid`` ilk render-də 0..max variantlarını qurur.

İstifadə::

    {% load exam_score_cells %}
    {% ese_question_cells row %}
"""

from __future__ import annotations

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_CELL = (
    '<td class="ese-td--num ese-td--q" data-ese-qcell="{index}"{hidden}>'
    '<div class="bootstrap-single-select bootstrap-single-select--ems bootstrap-single-select--compact ese-qsel"'
    " data-ese-qwrap>"
    '<select class="ems-select bootstrap-single-select__native is-enhanced" data-bootstrap-select-lazy'
    ' name="q__{enrollment}__{index}" aria-label="{label} — {name}"{disabled} data-ese-q="{index}"'
    ' data-initial="{value}" data-max="" tabindex="-1">'
    '<option value=""{blank_selected}>—</option>{selected_option}</select>'
    '<button type="button" class="btn btn-outline-secondary dropdown-toggle bootstrap-single-select__toggle'
    '{placeholder}" data-ese-qtoggle{toggle_disabled} aria-label="{label} — {name}" aria-haspopup="listbox">'
    '<span class="bootstrap-single-select__label-text">{label_text}</span>'
    '<span class="bootstrap-single-select__caret"><i class="fas fa-chevron-down" aria-hidden="true"></i></span>'
    "</button></div></td>"
)

_HIDDEN = mark_safe(" hidden")
_DISABLED = mark_safe(" disabled")
_SELECTED = mark_safe(" selected")
_PLACEHOLDER = mark_safe(" is-placeholder")
_EMPTY = mark_safe("")


@register.simple_tag(name="ese_question_cells")
def ese_question_cells(row) -> str:
    """Sətrin ``question_cells`` siyahısından (``index``/``label``/``value``/``off``) xanaların HTML-i.

    ``row`` — ``exam_score_roster.roster_for_offering`` sətri (+ ``question_cells``, ``name``,
    ``locked``). Bitmiş dövrdə yazılmış balı olan sətir (``locked``) və sual sayından artıq
    xana (``off``) ``disabled`` olur — POST-a düşmür (əvvəlki şablonla eyni qayda).
    """
    enrollment_id = row["enrollment"].id
    name = row.get("name") or ""
    locked = bool(row.get("locked"))
    parts = []
    for cell in row.get("question_cells") or ():
        value = cell["value"]
        off = cell["off"]
        parts.append(
            format_html(
                _CELL,
                index=cell["index"],
                hidden=_HIDDEN if off else _EMPTY,
                enrollment=enrollment_id,
                label=cell["label"],
                name=name,
                disabled=_DISABLED if (off or locked) else _EMPTY,
                value=value,
                blank_selected=_EMPTY if value else _SELECTED,
                selected_option=(format_html('<option value="{0}" selected>{0}</option>', value) if value else _EMPTY),
                placeholder=_EMPTY if value else _PLACEHOLDER,
                toggle_disabled=_DISABLED if locked else _EMPTY,
                label_text=value or "—",
            )
        )
    return mark_safe("".join(parts))
