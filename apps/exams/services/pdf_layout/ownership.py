"""Anchor midpoint-ini keçən mətn qutularını qonşu segmentlər arasında bölür."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from ..pdf_math import remap_symbol_pua
from .manifest import PageRect, Rect
from .noise import is_section_heading
from .slicing import SlicePlan

_SPACE_RE = re.compile(r"\s+")
_JOIN_GAP = 2.5
_SPILL_ROW_GAP = 64.0

# END_QUESTION yalnız blok sərhədi işarəsidir, sualın məzmunu deyil. PDF mətn
# qatında çox vaxt sonuncu variantın SONUNA yapışır ("D) Dörd END_QUESTION") —
# həm mətndən, həm də seqmentin qutusundan çıxarılmalıdır, əks halda marker
# tələbəyə göstərilən source-render şəklinin İÇİNDƏ görünür.
# Alt-xətt sayı sərbəstdir ("END__QUESTION" da tutulur) — `parsing.extraction.
# constants.END_QUESTION_RE` ilə eyni qayda. Qəsdən lokal saxlanılır: pdf_layout
# paketi parsing-i modul səviyyəsində import etsə idxal dövrü yaranardı.
_END_QUESTION_TOKEN_RE = re.compile(r"END_+QUESTION", re.IGNORECASE)


def _without_end_question(chars: Sequence[Any]) -> list:
    """END_QUESTION marker-ini təşkil edən simvolları seqmentdən çıxarır."""

    text = "".join(str(char.value) for char in chars)
    if not _END_QUESTION_TOKEN_RE.search(text):
        return list(chars)

    # Simvol dəyəri çox-hərfli ola bilər — mövqe→indeks xəritəsi qururuq.
    owner_index: list[int] = []
    for index, char in enumerate(chars):
        owner_index.extend([index] * len(str(char.value)))

    dropped: set[int] = set()
    for match in _END_QUESTION_TOKEN_RE.finditer(text):
        for position in range(match.start(), min(match.end(), len(owner_index))):
            dropped.add(owner_index[position])
    return [char for index, char in enumerate(chars) if index not in dropped]


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str
    box: PageRect


def segment_content(
    start: Any,
    end: Any | None,
    lines: Sequence[Any],
    slice_plan: SlicePlan,
    *,
    prefix: Sequence[TextPart] = (),
) -> tuple[str, list[PageRect], tuple[TextPart, ...]]:
    """Segment mətnini qurur və next-question-a aid disconnected spill-i ayırır."""

    parts = _line_parts(start, end, lines)
    owned, spill = _partition(parts, start, end, slice_plan)
    combined = [*owned[:1], *prefix, *owned[1:]] if owned else [*prefix]
    text = remap_symbol_pua(_SPACE_RE.sub(" ", " ".join(part.text for part in combined if part.text)).strip())
    return text, [part.box for part in combined], tuple(spill)


def _line_parts(start: Any, end: Any | None, lines: Sequence[Any]) -> list[TextPart]:
    end_order = end.line.global_order if end else len(lines) - 1
    parts: list[TextPart] = []
    for line in lines[start.line.global_order : end_order + 1]:
        if is_section_heading(line.text):
            continue
        low = start.content_start if line.global_order == start.line.global_order else 0
        high = end.start if end and line.global_order == end.line.global_order else len(line.chars)
        if high <= low:
            continue
        selected = _without_end_question(line.chars[low:high])
        visible = [char.rect for char in selected if not char.value.isspace()]
        if not visible:
            continue
        text = _SPACE_RE.sub(" ", "".join(char.value for char in selected)).strip()
        parts.append(
            TextPart(
                text,
                PageRect(
                    line.page_index,
                    Rect(
                        min(rect.x0 for rect in visible),
                        min(rect.y0 for rect in visible),
                        max(rect.x1 for rect in visible),
                        max(rect.y1 for rect in visible),
                    ),
                ),
            )
        )
    return parts


def _partition(
    parts: Sequence[TextPart],
    start: Any,
    end: Any | None,
    slice_plan: SlicePlan,
) -> tuple[list[TextPart], list[TextPart]]:
    if end is None:
        return list(parts), []
    if _is_postfix_anchor(start) and end.kind == "option":
        # Bəzi PDF generatorləri növbəti variantın label-ini əvvəlki sətrin
        # sonuna yazır:
        #
        #   B) plot(z, y) C)
        #   plot(z, 'y') D)
        #
        # Belə halda C-nin real məzmunu növbəti sətirdə, D label-indən
        # əvvəldir. Midpoint partition onu D-yə spill etsə variantlar bir
        # pillə sürüşür. Anchor-dan sonrakı cari intervalın hamısı C-yə aiddir.
        return list(parts), []
    boundary = slice_plan.anchor_bounds[id(start)].bottom
    owned = [part for part in parts if _global_center(part.box, slice_plan) <= boundary]
    remaining = [part for part in parts if part not in owned]
    while True:
        connected = [
            part for part in remaining if any(_connected(part.box, current.box, slice_plan) for current in owned)
        ]
        if not connected:
            break
        owned.extend(connected)
        remaining = [part for part in remaining if part not in connected]
    if end.kind == "option":
        spill = [part for part in remaining if _near_end_line(part.box, end)]
        while True:
            connected_spill = [
                part
                for part in remaining
                if part not in spill and any(_spill_connected(part.box, current.box, slice_plan) for current in spill)
            ]
            if not connected_spill:
                break
            spill.extend(connected_spill)
        owned.extend(part for part in remaining if part not in spill)
    owned_ids = {id(part) for part in owned}
    return (
        [part for part in parts if id(part) in owned_ids],
        [part for part in parts if id(part) not in owned_ids],
    )


def _is_postfix_anchor(anchor: Any) -> bool:
    """Sətirin məzmunundan sonra gələn və özündən sonra yalnız boşluq saxlayan label."""

    return bool(getattr(anchor, "is_postfix", False))


def _near_end_line(box: PageRect, end: Any) -> bool:
    if box.page_index != end.line.page_index:
        return False
    line = end.line.rect
    horizontal_overlap = min(box.rect.x1, line.x1) > max(box.rect.x0, line.x0)
    vertical_gap = max(
        0.0,
        max(box.rect.y0, line.y0) - min(box.rect.y1, line.y1),
    )
    return horizontal_overlap and vertical_gap <= _JOIN_GAP


def _global_center(box: PageRect, plan: SlicePlan) -> float:
    page = plan.page_rects[box.page_index]
    return plan.page_offsets[box.page_index] + (box.rect.y0 + box.rect.y1) / 2 - page.y0


def _global_rect(box: PageRect, plan: SlicePlan) -> Rect:
    page = plan.page_rects[box.page_index]
    offset = plan.page_offsets[box.page_index] - page.y0
    return Rect(box.rect.x0, box.rect.y0 + offset, box.rect.x1, box.rect.y1 + offset)


def _connected(first: PageRect, second: PageRect, plan: SlicePlan) -> bool:
    first_rect = _global_rect(first, plan)
    second_rect = _global_rect(second, plan)
    horizontal_overlap = min(first_rect.x1, second_rect.x1) > max(first_rect.x0, second_rect.x0)
    vertical_gap = max(
        0.0,
        max(first_rect.y0, second_rect.y0) - min(first_rect.y1, second_rect.y1),
    )
    return horizontal_overlap and vertical_gap <= _JOIN_GAP


def _spill_connected(first: PageRect, second: PageRect, plan: SlicePlan) -> bool:
    """Eyni vizual sətirin parçalanmış sütunlarını spill qrupuna birləşdirir."""

    first_rect = _global_rect(first, plan)
    second_rect = _global_rect(second, plan)
    horizontal_gap = max(
        0.0,
        max(first_rect.x0, second_rect.x0) - min(first_rect.x1, second_rect.x1),
    )
    vertical_gap = max(
        0.0,
        max(first_rect.y0, second_rect.y0) - min(first_rect.y1, second_rect.y1),
    )
    return horizontal_gap <= _SPILL_ROW_GAP and vertical_gap <= _JOIN_GAP
