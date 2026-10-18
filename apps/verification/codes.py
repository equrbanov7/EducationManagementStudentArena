"""Yoxlama kodu — ``QKU-7F3K-9M2P-XA4Q-1B2C`` (prefiks + 80 bit təsadüfi Crockford base32).

* **Prefiks** təşkilatın slug-ından (``qku`` → ``QKU``) — yalnız oxunaqlıq üçündür, təhlükəsizlik vermir.
* **Gövdə** 16 simvol × 5 bit = **80 bit** ``secrets`` təsadüfiliyi: kodu təxmin etmək / sadalamaq praktik
  deyil (üstəlik publik səhifə İP üzrə limitlidir).
* **Crockford əlifbası** (``I L O U`` yoxdur) — telefonda diktə və ya əllə yazanda qarışmır; daxil edilən
  ``O`` → ``0``, ``I``/``L`` → ``1`` kimi oxunur (yalnız gövdədə; prefiks olduğu kimi qalır).
"""

from __future__ import annotations

import re
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
BODY_LENGTH = 16
GROUP = 4
PREFIX_MAX = 6
DEFAULT_PREFIX = "EMS"
#: Ən uzun kanonik kod: prefiks (6) + 4 qrup × (1 tire + 4 simvol).
CODE_MAX_LENGTH = PREFIX_MAX + (BODY_LENGTH // GROUP) * (GROUP + 1)

_CROCKFORD_FIX = str.maketrans({"O": "0", "I": "1", "L": "1"})
_ALNUM = re.compile(r"[^0-9A-Z]")
_BODY_OK = re.compile(rf"^[{ALPHABET}]{{{BODY_LENGTH}}}$")
_PREFIX_OK = re.compile(rf"^[A-Z0-9]{{2,{PREFIX_MAX}}}$")


def org_prefix(slug: str) -> str:
    """Təşkilat slug-ından kod prefiksi — ``qku`` → ``QKU``; yararsızdırsa ``EMS``."""
    cleaned = _ALNUM.sub("", str(slug or "").upper())[:PREFIX_MAX]
    return cleaned if len(cleaned) >= 2 else DEFAULT_PREFIX


def _format(prefix: str, body: str) -> str:
    groups = [body[i : i + GROUP] for i in range(0, BODY_LENGTH, GROUP)]
    return "-".join([prefix, *groups])


def generate(prefix: str) -> str:
    """Yeni kanonik kod (80 bit). Unikallıq DB-dəki ``UNIQUE`` ilə təmin olunur (toqquşma ehtimalı ~2⁻⁸⁰)."""
    body = "".join(secrets.choice(ALPHABET) for _ in range(BODY_LENGTH))
    return _format(org_prefix(prefix), body)


def normalize(raw) -> str | None:
    """İstifadəçinin yazdığı kodu KANONİK formaya salır; yararsızdırsa ``None``.

    Boşluq/tire/kiçik hərf fərqi qəbul olunur. Son 16 simvol gövdədir (Crockford düzəlişi yalnız orada),
    qalan hissə prefiksdir. Format səhv olanda heç bir DB sorğusu getmir.
    """
    text = _ALNUM.sub("", str(raw or "").upper())
    if len(text) <= BODY_LENGTH or len(text) > BODY_LENGTH + PREFIX_MAX:
        return None
    prefix, body = text[:-BODY_LENGTH], text[-BODY_LENGTH:].translate(_CROCKFORD_FIX)
    if not _PREFIX_OK.match(prefix) or not _BODY_OK.match(body):
        return None
    return _format(prefix, body)


__all__ = ["CODE_MAX_LENGTH", "generate", "normalize", "org_prefix"]
