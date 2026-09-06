"""Bölmə autosave gövdəsinin FORMA yoxlaması (QA 2026-09-05 SYLLABUS-02/03).

HTTP səthi ixtiyari JSON qəbul edirdi: ``week.rows`` içində ``1``, ``null`` və ya
``{"topic": {"a": 1}}`` yazılır, sonra redaktor paneli ``.strip()`` çağıranda
500 verirdi — müəllim öz qaralamasını bir daha aça bilmirdi.  Uzunluq həddi də
yox idi (3 MB təsvir → hər önizləmə/PDF 3 MB).

Burada bölmə datası NORMALLAŞDIRILIR (``None`` → boş, rəqəm-sətir → int) və
uyğunsuz forma ``SectionShapeError`` (``section.invalid_shape`` / ``section.too_long``)
ilə rədd edilir; API onu 400 kimi qaytarır.
"""

from __future__ import annotations

import math

from ..constants import LESSON_HOUR_KINDS, MAX_LIST_ITEMS, MAX_TEXT_CHARS, MAX_WEEK_ROWS, SectionKey
from ..state_machine import TransitionDenied

_MAX_DEPTH = 8  # köçürülmüş `archived[].gelecek_sahe.nested[]` kimi iç-içə açarlar keçməlidir
_MAX_KEYS = 64
_MAX_KEY_CHARS = 64


class SectionShapeError(TransitionDenied):
    """Bölmə gövdəsi gözlənilən formada deyil — 400 (kliyent xətası).

    `__init__` QƏSDƏN override edilmir (flake8-bugbear B042) — nümunə
    `shape_error()` fabriki ilə qurulur, `field` orada təyin olunur.
    """

    field = ""


def shape_error(code: str, field: str, **params) -> SectionShapeError:
    """`SectionShapeError` qurucusu — `field`-i həm parametrlərə, həm atributa yazır."""
    error = SectionShapeError(code, "", {"field": field, **params})
    error.field = field
    return error


def _text(value, field: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise shape_error("section.invalid_shape", field)
    text = value if isinstance(value, str) else str(value)
    if len(text) > MAX_TEXT_CHARS:
        raise shape_error("section.too_long", field, max=MAX_TEXT_CHARS)
    return text


def _int(value, field: str) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise shape_error("section.invalid_shape", field)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise shape_error("section.invalid_shape", field)
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    raise shape_error("section.invalid_shape", field)


def _scalar_or_nested(value, field: str, depth: int):
    """Ümumi qayda: JSON skalyar / siyahı / lüğət — dərinlik, say və uzunluq həddi ilə."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise shape_error("section.invalid_shape", field)
        return value
    if isinstance(value, str):
        return _text(value, field)
    if depth >= _MAX_DEPTH:
        raise shape_error("section.invalid_shape", field)
    if isinstance(value, list):
        if len(value) > MAX_LIST_ITEMS:
            raise shape_error("section.too_long", field, max=MAX_LIST_ITEMS)
        return [_scalar_or_nested(item, f"{field}[{index}]", depth + 1) for index, item in enumerate(value)]
    if isinstance(value, dict):
        if len(value) > _MAX_KEYS:
            raise shape_error("section.too_long", field, max=_MAX_KEYS)
        out = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > _MAX_KEY_CHARS:
                raise shape_error("section.invalid_shape", field)
            out[key] = _scalar_or_nested(item, f"{field}.{key}", depth + 1)
        return out
    raise shape_error("section.invalid_shape", field)


def _string_list(value, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_text(value, field)]
    if not isinstance(value, list):
        raise shape_error("section.invalid_shape", field)
    if len(value) > MAX_LIST_ITEMS:
        raise shape_error("section.too_long", field, max=MAX_LIST_ITEMS)
    return [_text(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _week_rows(value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise shape_error("section.invalid_shape", "rows")
    if len(value) > MAX_WEEK_ROWS:
        raise shape_error("section.too_long", "rows", max=MAX_WEEK_ROWS)
    rows = []
    for index, raw in enumerate(value):
        field = f"rows[{index}]"
        if raw is None:
            rows.append({})
            continue
        if not isinstance(raw, dict):
            raise shape_error("section.invalid_shape", field)
        row = {}
        for key, item in raw.items():
            if not isinstance(key, str):
                raise shape_error("section.invalid_shape", field)
            if key in ("topic", "outcome"):
                row[key] = _text(item, f"{field}.{key}")
            elif key in LESSON_HOUR_KINDS:
                row[key] = _int(item, f"{field}.{key}")
            else:
                row[key] = _scalar_or_nested(item, f"{field}.{key}", 2)
        rows.append(row)
    return rows


_LIST_FIELDS = {
    SectionKey.OUT.value: ("outcomes",),
    SectionKey.METHOD.value: ("methods",),
    SectionKey.LIT.value: ("primary", "additional"),
}


def normalize_section_data(section_id: str, data: dict) -> dict:
    """Göndərilən açarları normallaşdırır; uyğunsuz forma → ``SectionShapeError``."""
    if not isinstance(data, dict):
        raise shape_error("section.invalid_shape", "data")
    out = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key or len(key) > _MAX_KEY_CHARS:
            raise shape_error("section.invalid_shape", "data")
        if section_id == SectionKey.WEEK.value and key == "rows":
            out[key] = _week_rows(value)
        elif key in _LIST_FIELDS.get(section_id, ()):
            out[key] = _string_list(value, key)
        else:
            out[key] = _scalar_or_nested(value, key, 1)
    return out


__all__ = ["SectionShapeError", "normalize_section_data"]
