"""Girişdə «Hesabınız dayandırılıb» bildirişi (sahib 2026-10-03).

Sahib: «tələbə username/parolunu yazanda o çıxsın (səbəb + kimə yaxınlaşmalı ki, blokdan çıxsın), amma başqa
heç nəyə daxil ola bilməsin». Ona görə:

* bildiriş YALNIZ parol DÜZGÜN olduqda qaytarılır — istifadəçi adını təxmin edən biri hesabın
  dayandırıldığını və səbəbini öyrənə bilməz (parol səhvdirsə adi «yanlış giriş» xətası qalır);
* SESSİYA AÇILMIR — görünüş yalnız məlumat səhifəsi render edir, kabinetə heç bir keçid yoxdur;
* yalnız MÜVƏQQƏTİ blok (``is_active=False``, silinməmiş). Silinmiş, arxiv (məzun/xaric) və idxal
  mərhələsindəki hesablar üçün bildiriş YOXDUR — onlar əvvəlki kimi adi xəta alır.
"""

from __future__ import annotations

from . import account_block_reasons as block_reasons


def blocked_login_notice(username: str, password: str) -> dict | None:
    """Doğru parolla daxil olmaq istəyən DAYANDIRILMIŞ hesab üçün göstəriləcək məlumat, yoxsa ``None``."""
    from ..backends import single_login_candidate
    from ..identity import user_access_is_login_blocked

    if not username or not password:
        return None
    user = single_login_candidate(username)
    if user is None or user.is_active:
        return None
    profile = getattr(user, "profile", None)
    if profile is None or getattr(profile, "is_deleted", False) or user_access_is_login_blocked(user):
        return None
    if not user.check_password(password):
        return None
    reason_code = profile.block_reason_code or ""
    return {
        "reason": block_reasons.reason_label(reason_code),
        "contact": block_reasons.contact_label(profile.block_contact_code, reason_code),
        "note": profile.block_contact_note or "",
        "blocked_at": profile.blocked_at,
        "has_reason": bool(reason_code),
    }


__all__ = ["blocked_login_notice"]
