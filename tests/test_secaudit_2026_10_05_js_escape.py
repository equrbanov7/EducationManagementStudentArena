"""Təhlükəsizlik auditi 2026-10-05 — atribut kontekstində quote-unsafe escape köməkçiləri.

``div.textContent = s; return div.innerHTML`` yalnız ``& < >`` simvollarını escape
edir, dırnaqları YOX. Aşağıdakı faylların ``esc()`` / ``escapeHtml()`` nəticəsi
``"…"`` atributlarının (``value=``, ``title=``, ``data-*``, ``href=``) içinə yazılır —
adı/mətni ``" autofocus onfocus=…`` olan dəyər atributdan çıxıb hadisə işləyicisi
qoşurdu. Bu qapı həmin köməkçilərin dırnaqları da entity-yə çevirdiyini yoxlayır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

ATTRIBUTE_CONTEXT_ESCAPERS = [
    ("apps/exams/static/exams/js/final_center/room_monitor.js", "esc"),
    ("apps/exams/static/exams/js/final_center/room_aggregate.js", "esc"),
    ("apps/exams/static/exams/js/final_center/proctor_identity.js", "esc"),
    ("apps/accounts/static/accounts/js/profile/exam_center_stats_boot.js", "esc"),
    ("apps/accounts/static/accounts/js/profile/appeal_stats.js", "esc"),
    ("apps/labs/static/labs/js/utils/escape.js", "escapeHtml"),
]


def _function_body(source: str, name: str) -> str:
    match = re.search(r"function\s+" + re.escape(name) + r"\s*\([^)]*\)\s*\{", source)
    assert match, f"{name}() tapılmadı"
    depth, index = 1, match.end()
    while depth and index < len(source):
        depth += {"{": 1, "}": -1}.get(source[index], 0)
        index += 1
    return source[match.end() : index]


@pytest.mark.parametrize(("relative_path", "name"), ATTRIBUTE_CONTEXT_ESCAPERS)
def test_escape_helper_encodes_quotes(relative_path, name):
    body = _function_body((ROOT / relative_path).read_text(encoding="utf-8"), name)
    assert "&quot;" in body, f'{relative_path}: {name}() dırnağı (") escape etmir'
    assert "&#39;" in body or "&#x27;" in body, f"{relative_path}: {name}() apostrofu (') escape etmir"
