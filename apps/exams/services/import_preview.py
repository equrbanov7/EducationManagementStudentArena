"""QuestionSubmission reviewer-i üçün scope-lu, cavab işarəsiz vizual preview."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from apps.exams.services.import_media import _assert_manifest_scope, _load_manifest, _load_source
from apps.exams.services.pdf_layout import render_segments

_GAP = 10
_LABEL_WIDTH = 44


def render_stashed_question_preview(
    token,
    source_index,
    *,
    owner_id=None,
    organization_id=None,
):
    """Bir sualın stem + A-D[/E] source crop-larını vahid PNG-yə yığ."""

    if isinstance(source_index, bool) or not isinstance(source_index, int):
        raise ValueError("source_index tam ədəd olmalıdır")
    manifest = _load_manifest(token)
    _assert_manifest_scope(
        manifest,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    questions = manifest.get("questions")
    if not isinstance(questions, list) or source_index < 0 or source_index >= len(questions):
        raise ValueError("source_index manifest xaricindədir")
    question = questions[source_index]
    if not isinstance(question, dict):
        raise ValueError("Manifest sualı yanlışdır")
    stem = question.get("stem")
    options = question.get("options")
    if not isinstance(stem, dict) or not isinstance(options, dict):
        raise ValueError("Manifest stem/options saxlamır")

    source = _load_source(token, manifest)
    labels = ["", *[str(label) for label in options]]
    payloads = render_segments(source, [stem, *options.values()])
    images = [Image.open(BytesIO(payload)).convert("RGB") for payload in payloads]
    width = max(image.width + (_LABEL_WIDTH if label else 0) for label, image in zip(labels, images))
    height = sum(image.height for image in images) + _GAP * (len(images) - 1)
    output = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(output)
    y = 0
    for label, image in zip(labels, images):
        x = _LABEL_WIDTH if label else 0
        if label:
            draw.text((12, y + 12), f"{label})", fill="black")
        output.paste(image, (x, y))
        y += image.height + _GAP

    buffer = BytesIO()
    output.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


__all__ = ["render_stashed_question_preview"]
