"""PyMuPDF geometriyasından fail-closed MCQ layout manifesti qurur."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import fitz

from .answers import correct_labels as detect_correct_labels
from .limits import validate_document_budget
from .manifest import (
    Anchor,
    Confidence,
    LayoutConfidenceError,
    Manifest,
    Option,
    PageRect,
    Question,
    Rect,
    Segment,
)
from .ocr import page_text_result
from .ownership import TextPart, segment_content
from .slicing import SlicePlan, build_slice_plan
from .yellow import BakedAnswerDetector

_QUESTION_RE = re.compile(r"^\s*(?P<label>\d{1,4})\s*(?P<punct>[.)])(?!\d)")
_OPTION_RE = re.compile(r"(?<![\w])(?P<label>[A-E])\s*(?P<punct>[.)])")
_ANCHOR_COLUMN_TOLERANCE = 6.0
_VISUAL_ONLY_TEXT = "[Vizual məzmun mənbə şəklindədir]"


@dataclass(frozen=True, slots=True)
class _Char:
    value: str
    rect: Rect


@dataclass(frozen=True, slots=True)
class _Line:
    page_index: int
    page_order: int
    global_order: int
    text: str
    rect: Rect
    chars: tuple[_Char, ...]


@dataclass(frozen=True, slots=True)
class _DetectedAnchor:
    kind: str
    label: str
    line: _Line
    start: int
    label_end: int
    content_start: int
    rect: Rect

    @property
    def position(self) -> tuple[int, int, int]:
        return (self.line.page_index, self.line.page_order, self.start)

    def public(self) -> Anchor:
        return Anchor(
            label=self.label,
            page_index=self.line.page_index,
            rect=self.rect,
            line_rect=self.line.rect,
        )


@dataclass(frozen=True, slots=True)
class _AnnotationRegion:
    page_index: int
    rects: tuple[Rect, ...]


def extract_pdf_layout(data: bytes, *, fail_closed: bool = True) -> Manifest:
    """
    PDF-dən sual/variant manifesti və canonical MCQ mətni çıxarır.

    Default rejim fail-closed-dur: çap sual nömrələri müsbət və ardıcıl deyilsə
    və ya hər sualda ardıcıl ən azı ``A-D`` yoxdursa
    :class:`LayoutConfidenceError` qaldırılır. ``ordinal`` həmişə ``1..N``
    qalır; çap nömrəsi isə, məsələn, ``51..100`` ola bilər. Diaqnostika üçün
    ``fail_closed=False`` yarımçıq manifest qaytarır.
    """

    if not data:
        raise ValueError("PDF məlumatı boşdur")

    with fitz.open(stream=data, filetype="pdf") as document:
        validate_document_budget(document)

        page_rects = tuple(_rect(page.rect) for page in document)
        lines, page_issues = _read_lines(document)
        question_anchors, option_anchors = _detect_anchors(lines)
        questions, issues = _build_questions(
            question_anchors,
            option_anchors,
            lines,
            page_rects,
            _highlight_regions(document),
            _ink_fallback_regions(document),
            BakedAnswerDetector(document),
        )
        issues = _confidence_issues(
            question_anchors,
            option_anchors,
            questions,
            [*page_issues, *issues],
        )
        confidence = Confidence(
            is_confident=not issues,
            question_anchor_count=len(question_anchors),
            option_anchor_count=len(option_anchors),
            issues=tuple(issues),
        )
        canonical_text = _canonical_text(questions)
        manifest = Manifest(
            page_count=document.page_count,
            questions=tuple(questions),
            canonical_text=canonical_text,
            confidence=confidence,
        )

    if fail_closed and not manifest.confidence.is_confident:
        raise LayoutConfidenceError(manifest)
    return manifest


def analyze_pdf(data: bytes, *, fail_closed: bool = True) -> dict[str, object]:
    """Public API: yalnız JSON-serializable tiplərdən ibarət manifest qaytarır."""

    return extract_pdf_layout(data, fail_closed=fail_closed).to_dict()


def manifest_to_mcq_text(manifest: Mapping[str, object] | Manifest) -> str:
    """Manifestdən deterministik canonical raw MCQ mətni yaradır."""

    if isinstance(manifest, Manifest):
        return _canonical_text(manifest.questions)
    questions = manifest.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Manifest questions siyahısı saxlamır")

    blocks: list[str] = []
    for question in questions:
        if not isinstance(question, Mapping):
            raise ValueError("Manifestdə sual obyekti yanlışdır")
        q_no = question.get("q_no")
        stem = question.get("stem")
        options = question.get("options")
        if not isinstance(stem, Mapping) or not isinstance(options, Mapping):
            raise ValueError("Manifestdə stem/options strukturu yanlışdır")
        lines = [f"{q_no}. {_canonical_value(stem.get('text'))}"]
        correct = question.get("correct")
        correct_labels = set(correct) if isinstance(correct, list) else set()
        for label, segment in options.items():
            if not isinstance(segment, Mapping):
                raise ValueError("Manifestdə variant segmenti yanlışdır")
            marker = "*" if label in correct_labels else ""
            lines.append(f"{marker}{label}) {_canonical_value(segment.get('text'))}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _read_lines(document: fitz.Document) -> tuple[tuple[_Line, ...], tuple[str, ...]]:
    pending: list[tuple[int, Rect, tuple[_Char, ...], str]] = []
    issues: list[str] = []
    for page_index, page in enumerate(document):
        result = page_text_result(page, page_index)
        raw = result.rawdict
        if result.unprocessed_reason:
            issues.append(f"səhifə {page_index + 1}: vizual məzmun emal olunmadı ({result.unprocessed_reason})")
        for block in raw.get("blocks", ()):
            if block.get("type") != 0:
                continue
            for raw_line in block.get("lines", ()):
                chars = tuple(
                    _Char(str(char.get("c", "")), _rect(char["bbox"]))
                    for span in raw_line.get("spans", ())
                    for char in span.get("chars", ())
                    if char.get("c") is not None
                )
                if not chars:
                    continue
                text = "".join(char.value for char in chars)
                pending.append((page_index, _rect(raw_line["bbox"]), chars, text))

    ordered: list[_Line] = []
    global_order = 0
    for page_index in range(document.page_count):
        page_lines = [item for item in pending if item[0] == page_index]
        page_lines.sort(key=lambda item: (round(item[1].y0, 2), item[1].x0, item[1].y1))
        for page_order, (_, line_rect, chars, text) in enumerate(page_lines):
            ordered.append(
                _Line(
                    page_index=page_index,
                    page_order=page_order,
                    global_order=global_order,
                    text=text,
                    rect=line_rect,
                    chars=chars,
                )
            )
            global_order += 1
    return tuple(ordered), tuple(issues)


def _detect_anchors(lines: Sequence[_Line]) -> tuple[list[_DetectedAnchor], list[_DetectedAnchor]]:
    question_candidates: list[_DetectedAnchor] = []
    options: list[_DetectedAnchor] = []
    for line in lines:
        question_match = _QUESTION_RE.match(line.text)
        if question_match:
            question_candidates.append(_make_anchor("question", question_match, line))

        option_start = question_match.end() if question_match else 0
        for option_match in _OPTION_RE.finditer(line.text, option_start):
            options.append(_make_anchor("option", option_match, line))

    questions = _select_question_anchor_column(question_candidates)
    options = _select_option_subsequences(questions, options)
    return questions, options


def _select_question_anchor_column(candidates: Sequence[_DetectedAnchor]) -> list[_DetectedAnchor]:
    """
    Sol-margin/typographic kolonunu seçərək formuladakı ``3.``, ``9.4`` kimi
    line-start rəqəmlərini sual anchor-u saymır.

    Eyni sənəddə real sual nömrələrinin x0 koordinatı sabit olur. Cluster-lər
    arasından çap nömrələri müsbət və ardıcıl olan ən uzun kolon seçilir. Heç
    bir kolon invariantı ödəmirsə ən böyük kolon saxlanır və son confidence
    yoxlaması onu fail-closed rədd edir.
    """

    if not candidates:
        return []
    clusters: list[list[_DetectedAnchor]] = []
    for candidate in sorted(candidates, key=lambda item: item.rect.x0):
        matching = next(
            (
                cluster
                for cluster in clusters
                if abs(candidate.rect.x0 - sum(item.rect.x0 for item in cluster) / len(cluster))
                <= _ANCHOR_COLUMN_TOLERANCE
            ),
            None,
        )
        if matching is None:
            clusters.append([candidate])
        else:
            matching.append(candidate)

    ordered_clusters = [sorted(cluster, key=lambda item: item.position) for cluster in clusters]
    valid = [cluster for cluster in ordered_clusters if _is_positive_contiguous([int(item.label) for item in cluster])]
    selected = max(valid or ordered_clusters, key=len)
    return list(selected)


def _select_option_subsequences(
    questions: Sequence[_DetectedAnchor],
    candidates: Sequence[_DetectedAnchor],
) -> list[_DetectedAnchor]:
    """Hər sual intervalında ən yığcam A-B-C-D[/E] subsequence-ni seçir."""

    selected: list[_DetectedAnchor] = []
    ordered = sorted(candidates, key=lambda item: item.position)
    for index, question in enumerate(questions):
        boundary = questions[index + 1].position if index + 1 < len(questions) else None
        scoped = [
            item
            for item in ordered
            if item.position > question.position and (boundary is None or item.position < boundary)
        ]
        complete: list[list[_DetectedAnchor]] = []
        for first in (item for item in scoped if item.label == "A"):
            path = [first]
            for expected in ("B", "C", "D"):
                following = next(
                    (item for item in scoped if item.position > path[-1].position and item.label == expected),
                    None,
                )
                if following is None:
                    break
                path.append(following)
            if len(path) == 4:
                complete.append(path)
        if not complete:
            selected.extend(scoped)
            continue
        path = min(
            complete,
            key=lambda items: (
                items[-1].line.global_order - items[0].line.global_order,
                items[0].position,
            ),
        )
        optional_e = next(
            (item for item in scoped if item.position > path[-1].position and item.label == "E"),
            None,
        )
        selected.extend([*path, *([optional_e] if optional_e else [])])
    return selected


def _make_anchor(kind: str, match: re.Match[str], line: _Line) -> _DetectedAnchor:
    start = match.start("label")
    label_end = match.end("punct")
    content_start = label_end
    while content_start < len(line.text) and line.text[content_start].isspace():
        content_start += 1
    anchor_chars = [char.rect for char in line.chars[start:label_end] if not char.value.isspace()]
    return _DetectedAnchor(
        kind=kind,
        label=match.group("label"),
        line=line,
        start=start,
        label_end=label_end,
        content_start=content_start,
        rect=_union(anchor_chars),
    )


def _build_questions(
    question_anchors: Sequence[_DetectedAnchor],
    option_anchors: Sequence[_DetectedAnchor],
    lines: Sequence[_Line],
    page_rects: Sequence[Rect],
    highlights: Sequence[_AnnotationRegion],
    ink_fallbacks: Sequence[_AnnotationRegion],
    baked_answers: BakedAnswerDetector,
) -> tuple[list[Question], list[str]]:
    questions: list[Question] = []
    issues: list[str] = []
    slice_plan = build_slice_plan([*question_anchors, *option_anchors], page_rects)
    pending_prefixes: dict[int, tuple[TextPart, ...]] = {}
    for index, question_anchor in enumerate(question_anchors):
        next_question = question_anchors[index + 1] if index + 1 < len(question_anchors) else None
        options = [
            anchor
            for anchor in option_anchors
            if anchor.position > question_anchor.position
            and (next_question is None or anchor.position < next_question.position)
        ]
        stem_end = options[0] if options else next_question
        stem_excludes = (
            _preview_boxes(
                stem_end,
                options[1] if len(options) > 1 else next_question,
                lines,
                slice_plan,
            )
            if stem_end is not None and stem_end.kind == "option"
            else ()
        )
        stem, stem_spill = _make_segment(
            question_anchor,
            stem_end,
            lines,
            slice_plan,
            prefix=pending_prefixes.pop(id(question_anchor), ()),
            exclude_boxes=stem_excludes,
        )
        if stem_spill and stem_end is not None:
            pending_prefixes[id(stem_end)] = stem_spill
        option_models: list[Option] = []
        for option_index, option_anchor in enumerate(options):
            option_end = options[option_index + 1] if option_index + 1 < len(options) else next_question
            next_boxes = (
                _preview_boxes(
                    option_end,
                    (options[option_index + 2] if option_index + 2 < len(options) else next_question),
                    lines,
                    slice_plan,
                )
                if option_index + 1 < len(options)
                else ()
            )
            option_segment, spill = _make_segment(
                option_anchor,
                option_end,
                lines,
                slice_plan,
                prefix=pending_prefixes.pop(id(option_anchor), ()),
                # Q38 kimi hündür stem/variant qlifinin bir neçə pikseli
                # midpoint sərhədini keçə bilər. İlk variantda stem qutularını
                # maskala; sonrakı variantlar üçün mövcud neighbor maskı daha
                # təhlükəsizdir (əlaqəsiz annotation-ları qoruyur).
                exclude_boxes=(*(stem.text_boxes if option_index == 0 else ()), *next_boxes),
            )
            if spill and option_end is not None:
                pending_prefixes[id(option_end)] = spill
            option_models.append(
                Option(
                    label=option_anchor.label,
                    segment=option_segment,
                )
            )

        labels = [option.label for option in option_models]
        if labels not in (["A", "B", "C", "D"], ["A", "B", "C", "D", "E"]):
            issues.append(
                f"sual {question_anchor.label}: variant anchor ardıcıllığı A-D[/E] deyil ({','.join(labels) or 'boş'})"
            )
        correct_labels = detect_correct_labels(option_models, highlights)
        if not correct_labels:
            correct_labels = detect_correct_labels(option_models, ink_fallbacks)
        if not correct_labels:
            baked = baked_answers.detect(option_models)
            if baked.ambiguous:
                issues.append(f"sual {question_anchor.label}: flattened sarı cavab işarəsi qeyri-müəyyəndir")
            else:
                correct_labels = baked.labels
        questions.append(
            Question(
                ordinal=index + 1,
                printed_q_no=int(question_anchor.label),
                stem=stem,
                options=tuple(option_models),
                correct_labels=correct_labels,
            )
        )
    return questions, issues


def _make_segment(
    start: _DetectedAnchor,
    end: _DetectedAnchor | None,
    lines: Sequence[_Line],
    slice_plan: SlicePlan,
    *,
    prefix: Sequence[TextPart] = (),
    exclude_boxes: Sequence[PageRect] = (),
) -> tuple[Segment, tuple[TextPart, ...]]:
    text, text_boxes, spill = segment_content(
        start,
        end,
        lines,
        slice_plan,
        prefix=prefix,
    )
    slices = slice_plan.segment_slices(
        start,
        end,
        text_boxes,
        [*[part.box for part in spill], *exclude_boxes],
    )
    return (
        Segment(
            text=text,
            anchor=start.public(),
            slices=slices,
            text_boxes=tuple(text_boxes),
        ),
        spill,
    )


def _preview_boxes(
    start: _DetectedAnchor,
    end: _DetectedAnchor | None,
    lines: Sequence[_Line],
    slice_plan: SlicePlan,
) -> tuple[PageRect, ...]:
    _, boxes, _ = segment_content(start, end, lines, slice_plan)
    return tuple(boxes)


def _highlight_regions(document: fitz.Document) -> tuple[_AnnotationRegion, ...]:
    regions: list[_AnnotationRegion] = []
    for page_index, page in enumerate(document):
        for annotation in page.annots() or ():
            if annotation.type[0] != fitz.PDF_ANNOT_HIGHLIGHT:
                continue
            vertices = annotation.vertices or ()
            quads = [
                _union([_point_rect(point) for point in vertices[offset : offset + 4]])
                for offset in range(0, len(vertices), 4)
                if len(vertices[offset : offset + 4]) == 4
            ]
            regions.append(_AnnotationRegion(page_index, tuple(quads) or (_rect(annotation.rect),)))
    return tuple(regions)


def _ink_fallback_regions(document: fitz.Document) -> tuple[_AnnotationRegion, ...]:
    regions: list[_AnnotationRegion] = []
    for page_index, page in enumerate(document):
        for annotation in page.annots() or ():
            if annotation.type[0] != fitz.PDF_ANNOT_INK:
                continue
            subject = str(annotation.info.get("subject") or "").strip().casefold()
            stroke = annotation.colors.get("stroke") or ()
            if subject != "highlight" or not _is_yellow(stroke):
                continue
            regions.append(_AnnotationRegion(page_index, (_rect(annotation.rect),)))
    return tuple(regions)


def _confidence_issues(
    question_anchors: Sequence[_DetectedAnchor],
    option_anchors: Sequence[_DetectedAnchor],
    questions: Sequence[Question],
    issues: Sequence[str],
) -> list[str]:
    result = list(issues)
    if not question_anchors:
        result.append("sual anchor-u tapılmadı")
        return result
    printed = [int(anchor.label) for anchor in question_anchors]
    if not _is_positive_contiguous(printed):
        result.append(f"sual anchor nömrələri müsbət və ardıcıl deyil: {printed}")
    assigned_count = sum(len(question.options) for question in questions)
    if assigned_count != len(option_anchors):
        result.append(
            f"variant anchor sayı uyğun deyil: tapılan={len(option_anchors)}, suallara bağlanan={assigned_count}"
        )
    return result


def _is_positive_contiguous(numbers: Sequence[int]) -> bool:
    if not numbers or numbers[0] < 1:
        return False
    return numbers == list(range(numbers[0], numbers[0] + len(numbers)))


def _canonical_text(questions: Iterable[Question]) -> str:
    blocks: list[str] = []
    for question in questions:
        lines = [f"{question.printed_q_no}. {_canonical_value(question.stem.text)}"]
        lines.extend(
            f"{'*' if option.label in question.correct_labels else ''}"
            f"{option.label}) {_canonical_value(option.segment.text)}"
            for option in question.options
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _canonical_value(value: object) -> str:
    return str(value or "").strip() or _VISUAL_ONLY_TEXT


def _is_yellow(stroke: Sequence[float]) -> bool:
    return len(stroke) >= 3 and stroke[0] >= 0.7 and stroke[1] >= 0.6 and stroke[2] <= 0.5


def _point_rect(point: fitz.Point | Sequence[float]) -> Rect:
    x = float(point.x) if hasattr(point, "x") else float(point[0])
    y = float(point.y) if hasattr(point, "y") else float(point[1])
    return Rect(x, y, x, y)


def _rect(value: fitz.Rect | Sequence[float]) -> Rect:
    return Rect(float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def _union(rects: Sequence[Rect]) -> Rect:
    if not rects:
        raise ValueError("Boş bbox birləşdirilə bilməz")
    return Rect(
        min(rect.x0 for rect in rects),
        min(rect.y0 for rect in rects),
        max(rect.x1 for rect in rects),
        max(rect.y1 for rect in rects),
    )
