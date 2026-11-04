"""RİM — «İşdən ayrılıb» arxivinin (müəllim / əməkdaş) TƏK tərifi (sahib 2026-11-04).

Sahib: «açdım useri — məzun ya da arxiv olanda çıxara bilim». Tələbə məzun əmri ilə arxivə keçir
(``access_state='archived'``, registrar hərəkəti). Müəllim / əməkdaş üçün ``access_state`` yolu YARAMIR:
oradan çıxış (accounts 0018/0021 funksiyaları) hesabın təşkilatda DƏQİQ BİR üzvlüyünü tələb edir, müəllimlərin
isə çox vaxt bir neçə üzvlüyü var — arxiv birtərəfli qapı olardı.

Ona görə əməkdaş arxivi mövcud iki mexanizmin birləşməsidir (yeni sxem / miqrasiya yoxdur):

* giriş ``block_account`` ilə bağlanır, səbəb kodu ``employment_ended`` («İşdən ayrılıb / müqavilə bitib»,
  müraciət — Kadrlar şöbəsi; giriş səhifəsi bunu göstərir);
* təşkilatdakı aktiv üzvlüklər deaktiv olur və ``updated_at`` = ``profile.blocked_at`` damğası ilə İZ qoyur —
  soft-delete-in ``deleted_at`` izi ilə eyni naxış (``account_deletion._restore_deactivated_memberships``).
  «Arxivdən çıxar» məhz bu izi geri açır; sətirlər heç vaxt silinmir.

Arxiv hesabı aktiv üzvlüksüz qalır, ona görə RİM siyasəti onu SİLİNMİŞ hesab kimi görür: idarə sahəsində qalır və
iyerarxiya BÜTÜN üzvlüklərlə hesablanır (arxivdəki prorektoru kiçik operator geri aça bilməz).
"""

from __future__ import annotations

from django.db.models import Q

#: ``account_block_reasons.REASONS`` kodu — arxivin bayrağı (kataloqda «İşdən ayrılıb / müqavilə bitib»).
EMPLOYMENT_ENDED = "employment_ended"
#: Arxivlənən əməkdaşın müraciət ünvanı (``account_block_reasons.CONTACTS``).
EMPLOYMENT_CONTACT = "hr"


def staff_archived_q(prefix: str = "") -> Q:
    """``User`` sorğusu üçün: bloklanıb, səbəbi «işdən ayrılıb», silinməyib."""
    return Q(
        **{
            f"{prefix}is_active": False,
            f"{prefix}profile__block_reason_code": EMPLOYMENT_ENDED,
        }
    ) & ~Q(**{f"{prefix}profile__is_deleted": True})


def is_staff_archived(user) -> bool:
    """Hesab «işdən ayrılıb» arxivindədirmi (sorğusuz — profil artıq yüklənib)."""
    if user is None or getattr(user, "is_active", True):
        return False
    profile = getattr(user, "profile", None)
    if profile is None or getattr(profile, "is_deleted", False):
        return False
    return str(getattr(profile, "block_reason_code", "") or "") == EMPLOYMENT_ENDED


__all__ = ["EMPLOYMENT_CONTACT", "EMPLOYMENT_ENDED", "is_staff_archived", "staff_archived_q"]
