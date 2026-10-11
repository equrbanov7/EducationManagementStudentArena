"""Jurnalda tələbənin göstərilən adı — «Soyad Ad Ata adı».

Jurnalın bütün tablarının sütun başlığı «№ · SOYAD AD ATA ADI»-dır, sətirlər isə
``get_full_name`` («Ad Soyad», ata adı YOX) göstərirdi. Ad-soyadı eyni olan iki
tələbəni ayırmaq üçün ata adı (``UserProfile.patronymic``) da yazılır və sıra
başlıqla eyniləşdirilir (sahib 2026-10-10).

⚠️ Sətir sorğusu ``select_related("student__profile")`` daşımalıdır — əks halda
hər tələbə üçün profilə ayrıca sorğu gedir (bax ``gradebook.get_offering_journal``
və tab builder-ləri).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist


def journal_student_name(user) -> str:
    """«Soyad Ad Ata adı»; boş hissələr atılır, heç biri yoxdursa ``username``."""
    if user is None:
        return ""
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        profile = None
    parts = (
        (getattr(user, "last_name", "") or "").strip(),
        (getattr(user, "first_name", "") or "").strip(),
        (getattr(profile, "patronymic", "") or "").strip(),
    )
    return " ".join(part for part in parts if part) or (getattr(user, "username", "") or "")


__all__ = ["journal_student_name"]
