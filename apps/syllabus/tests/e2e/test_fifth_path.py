"""BEŞİNCİ YOL: `assess.project` — müəllim bala TOXUNMADAN bölgü yaranır."""

from __future__ import annotations

import copy
import json

import pytest
from test_real_js_roundtrip import (  # noqa: F401  (fixture)
    editable,
    render_html,
    run_shipped_js,
)

from apps.syllabus import document as syl_document
from apps.syllabus import services
from apps.syllabus.services.drafts import section_data_map

pytestmark = pytest.mark.django_db


def _assessment_block(data_map):
    blocks = syl_document.build_document_blocks(data_map) if hasattr(
        syl_document, "build_document_blocks"
    ) else None
    return blocks


def test_lit_flattening_is_reader_equivalent(editable):  # noqa: F811
    """`lit.primary` siyahısı yastılanır — OXUCU üçün fərq VARMI?"""
    version = editable["version"]
    before = copy.deepcopy(section_data_map(version))
    html = render_html(user=editable["teacher"], organization=editable["org"], version=version)
    collected = run_shipped_js(html, "lit")
    for section_id, data in collected.items():
        services.save_section(version=version, section_id=section_id, data=data, actor=editable["actor"])
    after = section_data_map(version)
    assert syl_document._prose_lines(before["lit"]["primary"]) == syl_document._prose_lines(
        after["lit"]["primary"]
    ), "ədəbiyyat OXUCUYA fərqli çatır"


def test_untouched_assessment_gains_a_score_split_the_source_never_had(editable):  # noqa: F811
    """🔴 Müəllim SÜRÜŞDÜRÜCÜYƏ TOXUNMUR — yalnız `assess` bölməsi saxlanılır."""
    version = editable["version"]
    before = copy.deepcopy(section_data_map(version))
    assert before["assess"]["midterm"] == 0 and before["assess"]["project"] == 0
    assert syl_document._assessment_weights(before["assess"]) is None, "başlanğıcda bölgü YOXDUR"

    html = render_html(user=editable["teacher"], organization=editable["org"], version=version)
    collected = run_shipped_js(html, "assess")
    # SADƏCƏ «Qaralama saxla» — aktiv addım `assess` olanda JS məhz bunu göndərir.
    services.save_section(
        version=version, section_id="assess", data=collected["assess"], actor=editable["actor"]
    )
    after = section_data_map(version)

    print("\nBEFORE assess:", json.dumps(
        {k: v for k, v in before["assess"].items() if k != "note"}, ensure_ascii=False))
    print("AFTER  assess:", json.dumps(
        {k: v for k, v in after["assess"].items() if k != "note"}, ensure_ascii=False))
    print("weights BEFORE:", syl_document._assessment_weights(before["assess"]))
    print("weights AFTER :", syl_document._assessment_weights(after["assess"]))

    assert syl_document._assessment_weights(after["assess"]) is None, (
        "🔴 BEŞİNCİ YOL: müəllim bala toxunmadan tələbəyə mənbədə OLMAYAN "
        f"bal bölgüsü göstərilir: {syl_document._assessment_weights(after['assess'])}"
    )
