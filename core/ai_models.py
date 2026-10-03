"""Gemini model adlarının mərkəzi həlli (sahib 2026-10-01).

Google yeni API açarlarına ``gemini-2.5-*`` modellərini artıq vermir — çağırış HTTP 404
«This model … is no longer available to new users» qaytarır (prod diaqnostikası 2026-10-01,
``prod-ai-key.yml`` diagnose rejimi). Bazada (``AIConfiguration``), env-də və kodda qalan köhnə
adlar çağırış anında cari modellərə çevrilir; ona görə köhnə sazlamalar səssizcə sınmır.

Operator xəritəni env ilə dəyişə bilər: ``GEMINI_MODEL_ALIASES='{"gemini-2.5-flash": "…"}'``.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Köhnə ad → cari model (Google-un özünün tövsiyə etdiyi əvəzlər, 2026-10-01).
LEGACY_MODEL_ALIASES: dict[str, str] = {
    "gemini-2.5-flash": "gemini-3.8-flash",
    "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-2.5-pro": "gemini-pro-latest",
}

# «Düşünmə» səviyyəsi: 3.x modellərdə default düşünmə sadə suala da yüzlərlə token xərcləyir və
# cavab tavanını (maxOutputTokens) yeyə bilir; «low» keyfiyyəti saxlayır, xərci kəsir.
_DEFAULT_THINKING_LEVEL = "low"
_THINKING_LEVELS = {"minimal", "low", "medium", "high"}


def _aliases() -> dict[str, str]:
    raw = (os.getenv("GEMINI_MODEL_ALIASES") or "").strip()
    if not raw:
        return LEGACY_MODEL_ALIASES
    try:
        extra = json.loads(raw)
    except ValueError:
        logger.warning("GEMINI_MODEL_ALIASES is not valid JSON; using built-in aliases.")
        return LEGACY_MODEL_ALIASES
    if not isinstance(extra, dict):
        return LEGACY_MODEL_ALIASES
    merged = dict(LEGACY_MODEL_ALIASES)
    merged.update({str(k).strip(): str(v).strip() for k, v in extra.items() if str(k).strip() and str(v).strip()})
    return merged


def resolve_model(name: str | None) -> str:
    """Köhnə model adını cari modelə çevir; naməlum adı olduğu kimi qaytar."""
    model = (name or "").strip()
    return _aliases().get(model, model)


def preferred_model() -> str:
    """«Sistem tənzimləmələri»ndə RİM rəhbərinin seçdiyi model (2026-10-03); «Avtomatik» → boş sətir."""
    try:
        from core import runtime_settings

        return resolve_model(runtime_settings.override("ai.model") or "")
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa mövcud qayda işləsin
        return ""


def resolve_chain(chain) -> tuple[str, ...]:
    """Model zəncirini həll et, təkrarları at (sıra saxlanır). Seçilmiş model varsa zəncirin BAŞINDADIR."""
    seen: list[str] = []
    for name in (preferred_model(), *chain):
        model = resolve_model(name)
        if model and model not in seen:
            seen.append(model)
    return tuple(seen)


def thinking_config(model: str) -> dict | None:
    """REST ``generationConfig.thinkingConfig`` — model ailəsinə görə, yoxdursa ``None``."""
    model = (model or "").strip()
    if model.startswith("gemini-3") or model in {"gemini-flash-latest", "gemini-flash-lite-latest"}:
        level = (os.getenv("GEMINI_THINKING_LEVEL") or _DEFAULT_THINKING_LEVEL).strip().lower()
        if level not in _THINKING_LEVELS:
            level = _DEFAULT_THINKING_LEVEL
        return {"thinkingLevel": level}
    if model.startswith("gemini-2.5-flash"):
        return {"thinkingBudget": 0}
    return None
