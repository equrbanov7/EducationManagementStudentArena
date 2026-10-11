"""Girişdə «Hesabınız dayandırılıb» bildirişi (sahib 2026-10-03).

Sahib: «tələbə username/parolunu yazanda o çıxsın (səbəb + kimə yaxınlaşmalı ki, blokdan çıxsın), amma başqa
heç nəyə daxil ola bilməsin». Ona görə:

* bildiriş YALNIZ parol DÜZGÜN olduqda qaytarılır — istifadəçi adını təxmin edən biri hesabın
  dayandırıldığını və səbəbini öyrənə bilməz (parol səhvdirsə adi «yanlış giriş» xətası qalır);
* SESSİYA AÇILMIR — görünüş yalnız məlumat səhifəsi render edir, kabinetə heç bir keçid yoxdur;
* yalnız MÜVƏQQƏTİ blok (``is_active=False``, silinməmiş). Silinmiş, arxiv (məzun/xaric) və idxal
  mərhələsindəki hesablar üçün bildiriş YOXDUR — onlar əvvəlki kimi adi xəta alır.

2026-10-11 (sahib): səhifə hər kəsə «tələbə» dili ilə danışmasın — ``audience`` (``student`` / ``staff``)
ilə mətn seçilir; «Digər» səbəbdə operatorun yazdığı izah göstərilir.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.rls import bypass_rls

from . import account_block_reasons as block_reasons
from .people.constants import TEACHER_ROLE_NAMES

_STUDENT_PROFILE_ROLES = frozenset({"student", "lead_student"})
_STUDENT_ROLES = frozenset({"student", "lead_student", "alumni"})
_TEACHING_ROLES = frozenset(TEACHER_ROLE_NAMES)


def audience_of(user) -> str:
    """``student`` — tələbə/məzun (profil rolu və ya tələbə üzvlüyü, müəllim rolu YOX); qalanları ``staff``."""
    profile = getattr(user, "profile", None)
    if getattr(profile, "role", "") in _STUDENT_PROFILE_ROLES:
        return block_reasons.AUDIENCE_STUDENT
    membership = django_apps.get_model("organizations", "Membership")
    # Giriş POST-unda tenant konteksti hələ yoxdur — yalnız ŞƏXSİN ÖZ üzvlükləri bypass ilə oxunur
    # (``views.auth.login.classify_user_portal`` ilə eyni yol).
    with bypass_rls():
        roles = set(membership.objects.filter(user=user, is_active=True).values_list("role__name", flat=True))
    if roles & _STUDENT_ROLES and not roles & _TEACHING_ROLES:
        return block_reasons.AUDIENCE_STUDENT
    return block_reasons.AUDIENCE_STAFF


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
        "reason": block_reasons.display_reason(reason_code, profile.block_reason),
        "audience": audience_of(user),
        "contact": block_reasons.contact_label(profile.block_contact_code, reason_code),
        "note": profile.block_contact_note or "",
        "blocked_at": profile.blocked_at,
        "has_reason": bool(reason_code),
    }


__all__ = ["audience_of", "blocked_login_notice"]
