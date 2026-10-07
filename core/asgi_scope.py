"""ASGI (WebSocket) scope → HTTP qapılarının gözlədiyi ``request.META`` səthi.

Təhlükəsizlik dizaynı 2026-10-08: WebSocket qapısı HTTP-nin şəbəkə zonası / admin 2FA
funksiyalarını EYNİ ilə çağırır, ona görə müştəri IP-si də EYNİ qayda ilə tapılmalıdır —
``core.utils.get_client_ip`` (``X-Forwarded-For``-un SAĞINDAN ``TRUSTED_PROXY_HOPS``;
müştərinin sola yazdığı üzvlərə inanılmır), başlıq yoxdursa ``REMOTE_ADDR`` =
``scope["client"]``. Başlıqlar Django-nun ``ASGIRequest``-i kimi ``HTTP_<AD>`` açarına
çevrilir; təkrarlanan başlıq vergüllə birləşdirilir.

Bu modul DB-yə və sessiyaya toxunmur (event loop-da təhlükəsizdir).
"""

from __future__ import annotations

from core.utils import get_client_ip


def scope_meta(scope) -> dict[str, str]:
    """``{"HTTP_X_FORWARDED_FOR": …, "REMOTE_ADDR": …}`` — Django ``request.META`` forması."""
    meta: dict[str, str] = {}
    for raw_name, raw_value in scope.get("headers") or ():
        try:
            name = raw_name.decode("latin1")
            value = raw_value.decode("latin1")
        except (AttributeError, UnicodeDecodeError):
            continue
        key = "HTTP_" + name.upper().replace("-", "_")
        meta[key] = f"{meta[key]},{value}" if key in meta else value
    client = scope.get("client")
    meta["REMOTE_ADDR"] = str(client[0]) if client and isinstance(client, (list, tuple)) and client[0] else ""
    return meta


class _MetaOnly:
    __slots__ = ("META",)

    def __init__(self, meta):
        self.META = meta


def scope_client_ip(scope, meta: dict[str, str] | None = None) -> str:
    """HTTP ilə EYNİ etibarlı-proxy semantikası (``get_client_ip``); tapılmasa ``""``."""
    return get_client_ip(_MetaOnly(meta if meta is not None else scope_meta(scope))) or ""


__all__ = ["scope_client_ip", "scope_meta"]
