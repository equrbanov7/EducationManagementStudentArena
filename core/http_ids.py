"""İstifadəçi girişindən gələn açar (pk) dəyərlərinin təhlükəsiz çevrilməsi.

NƏ ÜÇÜN (backend auditi 2026-09-13, F-01): POST gövdəsindən / sorğu
parametrindən gələn ``"abc"`` kimi qeyri-UUID və ya qeyri-tam dəyər birbaşa
``filter(pk=...)`` / ``get_object_or_404(Model, pk=...)`` içinə düşəndə Django
``ValidationError`` («…is not a valid UUID») və ya ``ValueError`` atır və
autentifikasiyalı istifadəçi **HTTP 500** görür (Sentry səs-küyü, «server
xətası» səhifəsi). Sandbox-da dörd endpoint-də təkrarlandı (``workload:assign``,
``workload:row_save``, ``registrar:schedule`` slot əlavəsi,
``accounts:superadmin_organizations``).

Eyni köməkçinin bir neçə nüsxəsi artıq var idi (``workload/services/people.py
parse_uuid``, ``accounts/views/syllabus/lookup.py safe_uuid``,
``accounts/services/people/movements.py _uuid_or_none``) — bu modul ORTAQ
nüsxədir ki, növbəti çağıran yenidən yazmasın. Çağıran ``None`` alanda 404/400
qaytarır; heç bir istisna sızmır.
"""

from __future__ import annotations

import uuid


def parse_uuid(raw) -> uuid.UUID | None:
    """Xam dəyəri ``UUID``-ə çevirir; hazır ``UUID`` olduğu kimi qayıdır, pozuq → ``None``.

    ``uuid.UUID(<UUID>)`` ``TypeError`` atdığı üçün hazır obyekt ayrıca
    qaytarılır (URL ``<uuid:>`` konvertoru obyekt, gövdə isə mətn verir).
    """
    if isinstance(raw, uuid.UUID):
        return raw
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def parse_int(raw) -> int | None:
    """Xam dəyəri tam ədədə çevirir; pozuq / boş → ``None``.

    ``bool`` qəbul edilmir (``True`` → 1 sürprizi), onluq kəsr (``"7.5"``) də
    rədd olunur — pk həmişə tam ədəddir.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


__all__ = ["parse_int", "parse_uuid"]
