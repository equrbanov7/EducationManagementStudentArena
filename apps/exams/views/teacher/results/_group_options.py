"""results paketi — nəticələr səhifəsinin «Qrup» seçimləri (kohort + reyestr qrupu).

2026-09-14 (W5 `w5left`): kohortlar (`StudentGroup`, `"<int>"`) və reyestr qrupları
(`OrgUnit` GROUP, `"unit:<uuid>"`) TƏK siyahıdadır.

2026-10-25: məntiq `_group_index`-ə köçdü (sətir qrup sütunu, ana/alt qrup, çoxlu seçim,
«Qrupsuz», cəhd sayları) — bu modul köhnə çağıranlar üçün nazik giriş nöqtəsidir.
"""

from ._group_index import (
    KIND_COHORT,
    KIND_NONE,
    KIND_UNIT,
    GroupOption,
    build_group_index,
    normalize_group_value,
    resolve_group_options,
)


def available_group_options(exam) -> list[GroupOption]:
    """Kohortlar + reyestr qrupları (+ «Qrupsuz»), ada görə sıralı, tenant-scoped."""
    return build_group_index(exam).options


def resolve_group_option(exam, raw) -> GroupOption | None:
    """Yalnız bu imtahanın seçim siyahısındakı dəyər qəbul olunur (yad id → None)."""
    picked = resolve_group_options(build_group_index(exam), [raw])
    return picked[0] if picked else None


__all__ = [
    "GroupOption",
    "KIND_COHORT",
    "KIND_NONE",
    "KIND_UNIT",
    "available_group_options",
    "normalize_group_value",
    "resolve_group_option",
]
