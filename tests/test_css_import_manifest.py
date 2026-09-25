"""CSS istinadları production manifest-i ilə uyğun olmalıdır.

Django `ManifestStaticFilesStorage` `url()`/`@import` hədəfini yalnız `#fragment`
atıb axtarır; `?v=…` sorğusu olan hədəf manifest keşində tapılmır və ORİJİNAL
məzmunun hash-i yazılır. Hədəf faylın özündə də `@import`/`url()` varsa, onun
real (emal olunmuş) hash-i fərqli çıxır → production-da 404 (2026-09-25: kabinet
sidebar-ı stilsiz qaldı, `profile.css` → `sidebar.<köhnə-hash>.css`).

Qayda: içində başqa istinad olan CSS faylına `?v=` sorğusu ilə istinad edilmir
(manifest hash-i onsuz da keşi yeniləyir).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_RE = re.compile(r"""@import\s+(?:url\()?\s*["']?([^"')\s;]+)|url\(\s*["']?([^"')]+)["']?\s*\)""")


def _static_css_files():
    for base in [ROOT / "static", *sorted((ROOT / "apps").glob("*/static"))]:
        yield from base.rglob("*.css")


def _refs(text: str):
    for imp, url in REF_RE.findall(text):
        ref = (imp or url).strip()
        if ref and not ref.startswith(("data:", "http:", "https:", "//", "#", "/")):
            yield ref


def _has_refs(path: Path) -> bool:
    return any(True for _ in _refs(path.read_text(encoding="utf-8", errors="ignore")))


def test_no_query_string_reference_to_css_with_nested_refs():
    offenders = []
    for css in _static_css_files():
        for ref in _refs(css.read_text(encoding="utf-8", errors="ignore")):
            if "?" not in ref:
                continue
            target = (css.parent / ref.split("?", 1)[0].split("#", 1)[0]).resolve()
            if target.suffix == ".css" and target.is_file() and _has_refs(target):
                offenders.append(f"{css.relative_to(ROOT)} → {ref}")
    assert not offenders, "?v= ilə iç-içə CSS importu (production-da 404):\n" + "\n".join(offenders)
