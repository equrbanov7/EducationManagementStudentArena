"""Giriş qapılarının sessiyada yaddaşa alınan ucuz faktları (HTTP yazır, WebSocket oxuyur).

Təhlükəsizlik dizaynı 2026-10-08 (WebSocket qapısı): WS qoşulması HTTP-nin admin 2FA və
şəbəkə zonası qaydalarından keçir, amma hər qoşulmada profil (``role == superadmin``) və
üzvlük (hesab növü) sorğusu vermək canlı imtahanın yüzlərlə eyni-anlı qoşulmasında
lazımsız DB yüküdür. HTTP middleware-ləri bu faktları ONSUZ DA hesablayır (prod-da admin
2FA qapısı hər autentifikasiyalı sorğuda superadmin predikatını yoxlayır; zona qapısı
kənar zonada hesab növünü). Onlar burada sessiyaya yazılır — yalnız DƏYİŞƏNDƏ (sessiya
hər sorğuda yenidən saxlanmır) — WS qapısı isə yüklənmiş sessiyadan oxuyur.

* Açar istifadəçi id-sinə bağlıdır (``uid``): başqa hesabın faktı heç vaxt işlənmir.
* Sessiya server tərəfindədir; müştəri bu dəyəri yaza bilməz.
* Fakt yoxdursa (köhnə sessiya, ilk sorğu) WS qapısı DB-dən hesablayır — fail-closed.
* Köhnəlmə pəncərəsi = son HTTP sorğusu ilə WS qoşulması arası (adətən socket-i açan
  səhifənin özü); rol dəyişikliyi növbəti HTTP sorğusunda yenilənir.
"""

from __future__ import annotations

ACCESS_FACTS_SESSION_KEY = "_ems_access_facts"
FACT_SUPERADMIN = "sa"
FACT_ACCOUNT_KIND = "kind"


def cached_access_facts(session, user_pk) -> dict:
    """Bu istifadəçinin sessiyadakı faktları (yoxdursa / başqa uid-dirsə ``{}``)."""
    if session is None or not user_pk:
        return {}
    try:
        raw = session.get(ACCESS_FACTS_SESSION_KEY)
    except Exception:  # noqa: BLE001 — sessiya oxunmursa fakt yoxdur (fail-closed hesablanır)
        return {}
    if isinstance(raw, dict) and raw.get("uid") == user_pk:
        return raw
    return {}


def remember_access_facts(request, user, **facts) -> None:
    """Faktları sessiyaya birləşdir — dəyər dəyişmirsə sessiya ``modified`` olmur."""
    session = getattr(request, "session", None)
    user_pk = getattr(user, "pk", None)
    if session is None or not user_pk or not getattr(user, "is_authenticated", False):
        return
    current = cached_access_facts(session, user_pk)
    merged = {**current, **facts, "uid": user_pk}
    if merged != current:
        try:
            session[ACCESS_FACTS_SESSION_KEY] = merged
        except Exception:  # noqa: BLE001 — fakt yalnız optimallaşdırmadır; cavabı sındırmasın
            pass


__all__ = [
    "ACCESS_FACTS_SESSION_KEY",
    "FACT_ACCOUNT_KIND",
    "FACT_SUPERADMIN",
    "cached_access_facts",
    "remember_access_facts",
]
