"""Tenant tənzimləməsi — ``Organization.settings["surveys"]`` (kod dəyişmədən).

Açarlar (hamısı opsional; yanlış dəyər → defolt):

* ``auto_open`` (bool, defolt ``True``) — jurnal bağlananda kampaniya özü açılsın;
* ``close_after_days`` (int, 1–180, defolt 30) — açılışdan bağlanmaya qədər gün;
* ``grace_days`` (int, 0–60, defolt 3) — «Sonra doldur» imkanı olan günlər;
* ``min_group_size`` (int, 3–50, defolt 3) — yeni kampaniyanın k-həddi;
* ``mandatory`` (bool, defolt ``True``) — kampaniya kabineti bağlayırmı.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import (
    DEFAULT_CLOSE_AFTER_DAYS,
    DEFAULT_GRACE_DAYS,
    DEFAULT_MIN_GROUP_SIZE,
    MAX_CAMPAIGN_DAYS,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    SETTINGS_KEY,
)


@dataclass(frozen=True)
class SurveyConfig:
    auto_open: bool = True
    close_after_days: int = DEFAULT_CLOSE_AFTER_DAYS
    grace_days: int = DEFAULT_GRACE_DAYS
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE
    mandatory: bool = True


def _bounded_int(raw, default, low, high):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


def survey_config(organization) -> SurveyConfig:
    raw = getattr(organization, "settings", None)
    raw = raw.get(SETTINGS_KEY) if isinstance(raw, dict) else None
    if not isinstance(raw, dict):
        return SurveyConfig()
    return SurveyConfig(
        auto_open=bool(raw.get("auto_open", True)),
        close_after_days=_bounded_int(raw.get("close_after_days"), DEFAULT_CLOSE_AFTER_DAYS, 1, MAX_CAMPAIGN_DAYS),
        grace_days=_bounded_int(raw.get("grace_days"), DEFAULT_GRACE_DAYS, 0, 60),
        min_group_size=_bounded_int(
            raw.get("min_group_size"), DEFAULT_MIN_GROUP_SIZE, MIN_GROUP_SIZE_FLOOR, MIN_GROUP_SIZE_CEIL
        ),
        mandatory=bool(raw.get("mandatory", True)),
    )
