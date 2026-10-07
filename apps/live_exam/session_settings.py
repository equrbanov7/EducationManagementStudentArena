"""
Session settings helpers for live exam hosting.

İki görünüş var (Audit 2026-09-28 LX-BE):

* ``get_host_session_settings`` — TAM ayarlar (müəllim/host üçün), o cümlədən
  ``typed_questions`` (yazılı cavab sualları + QƏBUL OLUNAN CAVABLAR);
* ``get_session_settings`` — İCTİMAİ görünüş (oyunçu/izləyici səhifələri, lobby və
  oyunçu WS yayımları): ``PRIVATE_SETTING_KEYS`` çıxarılır, çünki qəbul olunan
  cavablar oyunçuya getsə düzgün cavab əvvəlcədən sızar.
"""

from __future__ import annotations

import secrets
from copy import deepcopy
from typing import Any

from django.utils.translation import pgettext

from apps.accounts.public import ProfileRole
from apps.live_exam.domain.session import coerce_question_seconds
from apps.live_exam.text_safety import sanitize_player_text
from apps.live_exam.typed_answers import ACCEPTED_MAX_ITEMS, TEXT_MAX_LENGTH, dedupe_accepted, typed_eligibility

THEME_KEYS = {"standard", "winter", "aurora", "sweet"}
LANGUAGE_KEYS = {"system", "az", "en", "ru", "tr"}
LOBBY_MUSIC_KEYS = {"original", "focus", "silent"}
MULTI_SCORING_PARTIAL = "partial"
MULTI_SCORING_STRICT = "strict"
MULTI_SCORING_KEYS = {MULTI_SCORING_PARTIAL, MULTI_SCORING_STRICT}
# Audit 2026-09-28 LX-BE: 150 nəfərlik mühazirə axını — əvvəlki 100 həddi (müəllim onu
# artıra da bilmirdi) 101-ci tələbəni «iştirakçı limiti» ilə qapıda saxlayırdı.
DEFAULT_MAX_PARTICIPANTS = 200
PRIVILEGED_MAX_PARTICIPANTS = 500
#: Yazılı cavab xəritəsində maksimal sual sayı (sağlamlıq həddi).
TYPED_QUESTIONS_MAX = 200

DEFAULT_SESSION_SETTINGS: dict[str, Any] = {
    "show_questions_on_devices": True,
    "characters_enabled": True,
    "theme_key": "aurora",
    "language": "system",
    "lobby_music": "original",
    "increase_contrast": False,
    "reactions_enabled": True,
    "randomize_questions": True,
    "randomize_answers": True,
    "autoplay": True,
    "qna_enabled": False,
    "team_selection_enabled": False,
    "team_talk_enabled": False,
    "nickname_generator": False,
    "two_step_join": True,
    "max_participants": DEFAULT_MAX_PARTICIPANTS,
    "sfx_volume": 70,
    # Yazılı cavab + çox seçimli bal rejimi (sahib 2026-09-28).
    "typed_typo_tolerance": True,
    "multi_scoring": MULTI_SCORING_PARTIAL,
    "typed_questions": {},
    # 2026-10-08 (L2): «Hər sual üçün vaxt» — ``None`` = standart (sualın / imtahanın vaxtı,
    # boşdursa 30 s); rəqəm = HƏR sual bu qədər saniyə (5–300). Növbəti sualdan tətbiq olunur.
    "question_time_seconds": None,
}

#: Oyunçulara / anonim izləyicilərə HEÇ VAXT göndərilməyən açarlar.
PRIVATE_SETTING_KEYS = frozenset({"typed_questions"})

BOOLEAN_SETTING_KEYS = {
    "show_questions_on_devices",
    "characters_enabled",
    "increase_contrast",
    "reactions_enabled",
    "randomize_questions",
    "randomize_answers",
    "autoplay",
    "qna_enabled",
    "team_selection_enabled",
    "team_talk_enabled",
    "nickname_generator",
    "two_step_join",
    "typed_typo_tolerance",
}

NICKNAME_ADJECTIVES = (
    "Swift",
    "Nova",
    "Bold",
    "Bright",
    "Clever",
    "Echo",
    "Pixel",
    "Rocket",
    "Storm",
    "Lucky",
)

NICKNAME_NOUNS = (
    "Falcon",
    "Comet",
    "Panda",
    "Otter",
    "Ranger",
    "Spark",
    "Turtle",
    "Tiger",
    "Wizard",
    "Voyager",
)


class SessionSettingsError(ValueError):
    """Host ayarları yararsızdır — mesaj istifadəçiyə göstərilir (HTTP 400)."""


def default_session_settings() -> dict[str, Any]:
    return deepcopy(DEFAULT_SESSION_SETTINGS)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def allowed_max_participants_for_user(user) -> int:
    if user is None:
        return DEFAULT_MAX_PARTICIPANTS

    level = 0
    if getattr(user, "is_superuser", False):
        return PRIVILEGED_MAX_PARTICIPANTS
    if hasattr(user, "_highest_role_level"):
        try:
            level = int(user._highest_role_level())
        except Exception:
            level = 0
    elif hasattr(user, "profile") and getattr(user.profile, "role_level", None) is not None:
        level = int(user.profile.role_level or 0)

    return (
        PRIVILEGED_MAX_PARTICIPANTS
        if level > ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)
        else DEFAULT_MAX_PARTICIPANTS
    )


def _typed_error(msgid: str, **params) -> SessionSettingsError:
    message = pgettext("live_exam.view.message", msgid)
    return SessionSettingsError(message.format(**params) if params else message)


def _accepted_list(value: Any, *, strict: bool) -> list[str]:
    raw = value.get("accepted") if isinstance(value, dict) else value
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        if strict:
            raise _typed_error("typed_questions_invalid")
        return []
    if strict and len(raw) > ACCEPTED_MAX_ITEMS:
        raise _typed_error("typed_accepted_too_many")
    items = []
    for item in raw:
        if not isinstance(item, (str, int, float)):
            if strict:
                raise _typed_error("typed_questions_invalid")
            continue
        cleaned = sanitize_player_text(str(item), max_length=TEXT_MAX_LENGTH * 4)
        if len(cleaned) > TEXT_MAX_LENGTH:
            if strict:
                raise _typed_error("typed_accepted_too_long")
            continue
        items.append(cleaned)
    return dedupe_accepted(items)[:ACCEPTED_MAX_ITEMS]


def normalize_typed_questions(raw: Any, *, session=None) -> dict[str, dict[str, list[str]]]:
    """``{"<qid>": {"accepted": [...]}}`` — TAM əvəzləmə xəritəsi.

    ``session`` verilibsə (host yazısı) — ciddi yoxlama: sual bu imtahana aid və
    yazılı cavab üçün UYĞUN olmalıdır, əks halda ``SessionSettingsError``.
    ``session`` yoxdursa (saxlanmış ayarların oxunması) — yalnız forma təmizlənir.
    """
    strict = session is not None
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        if strict:
            raise _typed_error("typed_questions_invalid")
        return {}
    if strict and len(raw) > TYPED_QUESTIONS_MAX:
        raise _typed_error("typed_questions_invalid")

    catalog = {}
    if strict:
        from apps.exams.models import ExamQuestion

        questions = ExamQuestion.objects.filter(exam_id=session.exam_id).prefetch_related("options")
        catalog = {question.id: question for question in questions.order_by("order", "id")}
        positions = {question_id: index for index, question_id in enumerate(catalog, start=1)}

    result: dict[str, dict[str, list[str]]] = {}
    for key, value in raw.items():
        try:
            question_id = int(str(key).strip())
        except (TypeError, ValueError):
            if strict:
                raise _typed_error("typed_questions_invalid") from None
            continue
        accepted = _accepted_list(value, strict=strict)
        if strict:
            question = catalog.get(question_id)
            if question is None:
                raise _typed_error("typed_question_not_in_exam")
            eligible, _defaults = typed_eligibility(question)
            if not eligible:
                raise _typed_error("typed_question_not_eligible", index=positions[question_id])
        result[str(question_id)] = {"accepted": accepted}
    return result


def normalize_session_setting_updates(
    raw: dict[str, Any] | None,
    *,
    max_participants_cap: int = PRIVILEGED_MAX_PARTICIPANTS,
    session=None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    updates: dict[str, Any] = {}
    for key in BOOLEAN_SETTING_KEYS:
        if key in raw:
            updates[key] = _coerce_bool(raw.get(key), DEFAULT_SESSION_SETTINGS[key])

    if "theme_key" in raw:
        value = str(raw.get("theme_key") or "").strip().lower()
        updates["theme_key"] = value if value in THEME_KEYS else DEFAULT_SESSION_SETTINGS["theme_key"]

    if "language" in raw:
        value = str(raw.get("language") or "").strip().lower()
        updates["language"] = value if value in LANGUAGE_KEYS else DEFAULT_SESSION_SETTINGS["language"]

    if "lobby_music" in raw:
        value = str(raw.get("lobby_music") or "").strip().lower()
        updates["lobby_music"] = value if value in LOBBY_MUSIC_KEYS else DEFAULT_SESSION_SETTINGS["lobby_music"]

    if "multi_scoring" in raw:
        value = str(raw.get("multi_scoring") or "").strip().lower()
        updates["multi_scoring"] = value if value in MULTI_SCORING_KEYS else DEFAULT_SESSION_SETTINGS["multi_scoring"]

    if "max_participants" in raw:
        try:
            value = int(raw.get("max_participants"))
        except (TypeError, ValueError):
            value = DEFAULT_SESSION_SETTINGS["max_participants"]
        updates["max_participants"] = max(1, min(value, max(1, int(max_participants_cap or DEFAULT_MAX_PARTICIPANTS))))

    if "sfx_volume" in raw:
        try:
            value = int(raw.get("sfx_volume"))
        except (TypeError, ValueError):
            value = DEFAULT_SESSION_SETTINGS["sfx_volume"]
        updates["sfx_volume"] = max(0, min(100, value))

    if "typed_questions" in raw:
        updates["typed_questions"] = normalize_typed_questions(raw.get("typed_questions"), session=session)

    if "question_time_seconds" in raw:
        updates["question_time_seconds"] = _question_seconds_update(raw.get("question_time_seconds"), strict=session)

    return updates


def _question_seconds_update(value: Any, *, strict) -> int | None:
    """``None``/""/0/"default" → standart; rəqəm → [5, 300]; yararsız mətn → host yazısında 400."""
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "default", "standard", "0"}):
        return None
    seconds = coerce_question_seconds(value)
    if seconds is None and strict is not None and not (isinstance(value, (int, float)) and value <= 0):
        raise SessionSettingsError(pgettext("live_exam.host_settings", "Sual vaxtı 5–300 saniyə olmalıdır."))
    return seconds


def normalize_session_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    """TAM (host) ayarlar — saxlanmış xam ``host_settings``-dən."""
    settings = default_session_settings()
    settings.update(normalize_session_setting_updates(raw, max_participants_cap=PRIVILEGED_MAX_PARTICIPANTS))
    return settings


def public_session_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Oyunçu/izləyici üçün təhlükəsiz görünüş (qəbul cavabları YOXDUR)."""
    return {key: value for key, value in (settings or {}).items() if key not in PRIVATE_SETTING_KEYS}


def get_host_session_settings(session) -> dict[str, Any]:
    return normalize_session_settings(getattr(session, "host_settings", None) or {})


def get_session_settings(session) -> dict[str, Any]:
    """İctimai ayarlar (oyunçu səhifələri, lobby/oyunçu yayımları) — default təhlükəsizdir."""
    return public_session_settings(get_host_session_settings(session))


def update_session_settings(
    session,
    updates: dict[str, Any] | None,
    *,
    max_participants_cap: int = PRIVILEGED_MAX_PARTICIPANTS,
) -> dict[str, Any]:
    """Ayarları yazır və TAM (host) görünüşü qaytarır.

    ``typed_questions`` verilibsə ciddi yoxlanır (``SessionSettingsError``).
    Mühərrikin gizli açarları (``_question_phase_override``, ``_question_config``)
    saxlanılır.
    """
    raw = getattr(session, "host_settings", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    merged = normalize_session_settings(raw)
    merged.update(
        normalize_session_setting_updates(updates, max_participants_cap=max_participants_cap, session=session)
    )
    for key, value in raw.items():
        if key not in DEFAULT_SESSION_SETTINGS:
            merged[key] = value
    session.host_settings = merged
    session.save(update_fields=["host_settings"])

    # Invalidate the cache so the next read picks up the fresh settings.
    try:
        from core.cache import invalidate_session_settings_cache

        invalidate_session_settings_cache(session)
    except Exception:
        pass

    return {key: value for key, value in merged.items() if key in DEFAULT_SESSION_SETTINGS}


def host_question_catalog(session) -> list[dict[str, Any]]:
    """Host ayarlar çekməcəsi üçün imtahanın BÜTÜN sualları (imtahan sırası ilə).

    ``{"id", "index" (1-dən), "text", "typed_eligible", "typed_default_accepted",
    "typed" (hazırda yazılı rejimdədir), "accepted" (müəllimin siyahısı; boş = default)}``.
    YALNIZ host kontekstində istifadə olunur — qəbul cavabları ehtiva edir.
    """
    from apps.exams.models import ExamQuestion
    from apps.live_exam.domain.session import get_question_text

    typed_map = get_host_session_settings(session).get("typed_questions") or {}
    questions = ExamQuestion.objects.filter(exam_id=session.exam_id).prefetch_related("options").order_by("order", "id")
    catalog = []
    for index, question in enumerate(questions, start=1):
        eligible, defaults = typed_eligibility(question)
        entry = typed_map.get(str(question.id))
        catalog.append(
            {
                "id": question.id,
                "index": index,
                "text": get_question_text(question),
                "typed_eligible": eligible,
                "typed_default_accepted": defaults,
                "typed": bool(entry is not None and eligible),
                "accepted": list((entry or {}).get("accepted") or []),
            }
        )
    return catalog


def session_join_path(session) -> str:
    settings = get_session_settings(session)
    return "/live/" if settings.get("two_step_join", True) else session.join_url_path()


def generate_guest_nickname() -> str:
    return (
        f"{secrets.choice(NICKNAME_ADJECTIVES)} " f"{secrets.choice(NICKNAME_NOUNS)} " f"{secrets.randbelow(90) + 10}"
    )
