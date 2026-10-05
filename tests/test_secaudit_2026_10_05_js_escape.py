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
    # 2026-10-05 (ikinci dalğa): düzəliş, dərs yükü, sistem monitorinqi, view-as.
    ("apps/registrar/static/registrar/js/correction.js", "esc"),
    ("apps/registrar/static/registrar/js/correction_history.js", "esc"),
    ("apps/accounts/static/accounts/js/profile/workload_distribution.js", "esc"),
    ("apps/accounts/static/accounts/js/profile/workload_distribution_render.js", "esc"),
    ("apps/accounts/static/accounts/js/profile/workload_my.js", "esc"),
    ("apps/accounts/static/accounts/js/monitoring/system_monitoring_format.js", "escapeHtml"),
    ("static/js/view_as.js", "escapeHtml"),
    ("apps/accounts/static/accounts/js/statistics/utils.js", "escapeHtml"),
]

_ESCAPER_DEF = re.compile(
    r"(?:function\s+([\w$]+)\s*\([^)]*\)|(?:const|let|var)\s+([\w$]+)\s*=\s*(?:function\s*)?\([^)]*\)\s*(?:=>)?)\s*\{"
)
_RETURNS_INNER_HTML = re.compile(r"return\s+[\w$.]*innerHTML")


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


def _shipped_js_files():
    for pattern in ("apps/*/static/**/*.js", "static/js/**/*.js"):
        for path in ROOT.glob(pattern):
            if "vendor" in path.parts or ".min." in path.name:
                continue
            yield path


def test_no_quote_unsafe_textcontent_escaper_anywhere():
    """Ümumi qapı: ``x.textContent = s; return x.innerHTML`` köməkçisi dırnaqları da çevirməlidir.

    Köməkçinin nəticəsi bu gün yalnız mətn kontekstində işlənsə də, sabah ``"…"``
    atributuna düşə bilər — siyahı əsaslı yoxlama yeni faylı tutmurdu.
    """
    offenders = []
    for path in _shipped_js_files():
        source = path.read_text(encoding="utf-8", errors="ignore")
        if "textContent" not in source:
            continue
        for match in _ESCAPER_DEF.finditer(source):
            depth, index = 1, match.end()
            while depth and index < len(source):
                depth += {"{": 1, "}": -1}.get(source[index], 0)
                index += 1
            body = source[match.end() : index]
            if len(body) > 600 or "textContent" not in body or not _RETURNS_INNER_HTML.search(body):
                continue
            if "&quot;" not in body or not ("&#39;" in body or "&#x27;" in body):
                offenders.append(f"{path.relative_to(ROOT)}:{match.group(1) or match.group(2)}")
    assert offenders == [], f"Dırnaqları escape etməyən textContent→innerHTML köməkçiləri: {offenders}"
