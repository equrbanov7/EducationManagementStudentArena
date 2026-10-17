"""Monitorinq mətnlərinin təmizlənməsi — sirr və şəxsi məlumat süzgəci (2026-10-01).

İki ayrı süzgəc, iki ayrı məqsəd:

* ``redact_secrets`` — UI-a gedən log/alert mətnlərində SİRLƏRİ gizlədir
  (DSN içindəki parol, ``password=…``, ``token=…``, ``Authorization: Bearer …``,
  API açarı formaları, sessiya/CSRF cookie-ləri). Superadmin də daxil hamıya
  tətbiq olunur: log sətri ekranda sirr göstərməməlidir.
* ``scrub_personal`` — xarici AI-yə (Gemini) göndərilən xülasədə ŞƏXSİ
  məlumatı çıxarır: e-poçt, IPv4/IPv6, ``ad.soyad`` formalı istifadəçi adları
  (layihənin rəsmi username formatı). Xülasə onsuz da yalnız aqreqat saylardan
  qurulur — bu, ikinci (müdafiə-dərinliyi) qatdır.

Hər iki funksiya saf-dır (DB/şəbəkə yoxdur) və heç vaxt exception atmır.
"""

from __future__ import annotations

import re

_SECRET_KEYS = (
    r"password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"authorization|cookie|sessionid|csrftoken|csrfmiddlewaretoken|x-goog-api-key|dsn"
)

_SECRET_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    # scheme://user:password@host → scheme://***@host
    (re.compile(r"\b([a-z][a-z0-9+.-]{1,20})://[^\s/@:]+:[^\s/@]+@", re.IGNORECASE), r"\1://***@"),
    # Authorization: Bearer <token> / Basic <b64>
    (re.compile(r"\b(Bearer|Basic|Token)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE), r"\1 ***"),
    # key=value / key: value / "key": "value"
    (
        re.compile(rf"(?i)([\"']?(?:{_SECRET_KEYS})[\"']?\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&}}\]]+)"),
        r"\1***",
    ),
    # Google API açarı (AIza…), OpenAI/Anthropic üslublu açarlar (sk-…), GitHub tokenləri.
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "***"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"), "***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), "***"),
    # JWT (üç base64url hissə).
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "***"),
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
#: IPv6 namizədi; yalnız hex hərf və ya «::» daşıyırsa əvəz olunur (``12:30:45`` vaxtı toxunulmur).
_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}(?![\w:])")
#: Layihənin istifadəçi adı formatı `ad.soyad` (2026-09-14 kimlik qərarı) — AZ
#: hərfləri daxil. `system.monitoring` kimi açarlar xülasəyə düşmür (whitelist).
_USERNAME_RE = re.compile(r"\b[a-zçəğıöşü]{2,}\.[a-zçəğıöşü]{2,}\d*\b", re.IGNORECASE)
_LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")


def _ipv6_replacement(match: re.Match) -> str:
    candidate = match.group(0)
    if "::" in candidate or re.search(r"[a-fA-F]", candidate):
        return "[ip]"
    return candidate


def redact_secrets(text) -> str:
    """Log/alert mətnindəki sirləri ``***`` ilə əvəz edir."""
    if not text:
        return ""
    value = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        try:
            value = pattern.sub(replacement, value)
        except Exception:  # pragma: no cover - regex heç vaxt sorğunu yıxmamalıdır
            continue
    return value


def scrub_personal(text) -> str:
    """E-poçt, IP, ``ad.soyad`` istifadəçi adı və uzun rəqəm ardıcıllıqlarını çıxarır."""
    if not text:
        return ""
    value = redact_secrets(text)
    value = _EMAIL_RE.sub("[email]", value)
    value = _IPV4_RE.sub("[ip]", value)
    value = _IPV6_RE.sub(_ipv6_replacement, value)
    value = _USERNAME_RE.sub("[user]", value)
    value = _LONG_DIGITS_RE.sub("[n]", value)
    return value


#: Tokenli yollar: ``/accounts/reset/<uidb64>/<token>/`` (bərpa linki), sual idxalı tokeni.
_TOKEN_PATH_RE = re.compile(r"(/reset/)(?!done(?:/|\b))[^/\s\"'?#]+(?:/[^/\s\"'?#]+)?", re.IGNORECASE)
_IMPORT_TOKEN_RE = re.compile(r"(/question-imports/)[^/\s\"'?#]+", re.IGNORECASE)
#: Yolda istifadəçi adı: ``/accounts/users/<username>/`` (ictimai profil).
_USERS_PATH_RE = re.compile(r"(/users/)[^/\s\"'?#]+", re.IGNORECASE)
#: Sorğu sətrində və strukturlaşdırılmış logda şəxsi açarlar (``?username=…``, ``"email": "…"``).
_PERSONAL_KEYS = r"username|user_name|user|email|e-mail|login|fin|phone"
_QUERY_PERSONAL_RE = re.compile(rf"(?i)([?&](?:{_PERSONAL_KEYS})=)[^&\s\"'#]*")
_KV_PERSONAL_RE = re.compile(
    rf"(?i)([\"']?\b(?:{_PERSONAL_KEYS})[\"']?\s*[=:]\s*)(?!\[x\])(\"[^\"]*\"|'[^']*'|[^\s,;&}}\]]+)"
)


def scrub_log_line(text) -> str:
    """«Loglar» tabı (SEC-1 F4, 2026-10-17): sirlər + şəxsi məlumat — İP, e-poçt, yoldakı istifadəçi adı,
    sorğu / log açarlarındakı istifadəçi adı, bərpa linki tokeni. Superadmin də daxil HƏR KƏSƏ (təhlükəsiz variant):
    texniki diaqnostika üçün yol, status, vaxt, konteyner kifayətdir. ``scrub_personal``-dan fərqli olaraq modul /
    fayl adlarına (``apps.accounts``, ``main.css``) toxunmur — sətir oxunaqlı qalır."""
    if not text:
        return ""
    value = redact_secrets(text)
    for pattern, replacement in (
        (_TOKEN_PATH_RE, r"\1***"),
        (_IMPORT_TOKEN_RE, r"\1***"),
        (_USERS_PATH_RE, r"\1[user]"),
        (_QUERY_PERSONAL_RE, r"\1[x]"),
        (_KV_PERSONAL_RE, r"\1[x]"),
        (_EMAIL_RE, "[email]"),
        (_IPV4_RE, "[ip]"),
    ):
        try:
            value = pattern.sub(replacement, value)
        except Exception:  # pragma: no cover - regex heç vaxt sorğunu yıxmamalıdır
            continue
    try:
        value = _IPV6_RE.sub(_ipv6_replacement, value)
    except Exception:  # pragma: no cover
        pass
    return value


def scrub_path(path) -> str:
    """Endpoint yolunu AI xülasəsi üçün təmizləyir (seqment səviyyəsində)."""
    if not path:
        return ""
    segments = []
    for segment in str(path)[:200].split("/"):
        cleaned = scrub_personal(segment)
        if cleaned != segment:
            cleaned = "<x>"
        segments.append(cleaned)
    return "/".join(segments)


__all__ = ["redact_secrets", "scrub_log_line", "scrub_path", "scrub_personal"]
