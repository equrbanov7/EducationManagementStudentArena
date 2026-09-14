"""Köhnə imtahan kohortu (`StudentGroup`) səthinin yığışdırılması — 2026-09-14 (W7 `w7cohort`).

Sahibin qərarı (2026-09-07): «qrup reyestri əsasdır; köhnə imtahan-kohort
bölməsi silinməyə gedir». Reyestr qrupları (`Exam.allowed_units` → OrgUnit
GROUP) sehrbaz, giriş siyasəti, siyahılar, PIN, statistika və istisnalar
üzrə uçdan-uca işləyir; prod-bənzər klonda `exams_studentgroup` və
`exams_exam_allowed_groups` cədvəlləri BOŞDUR.

Bu dalğada məlumat silinmir, model qalır, cədvəl atan miqrasiya YOXDUR —
yalnız SƏTH gizlədilir: kohortu olmayan təşkilatda `/exams/groups/` və
`/exams/groups/create/form/` boş siyahı + yaratma forması əvəzinə kiçik
«bu səth reyestr qrupları ilə əvəz olunub» kartı göstərir; kohortu OLAN
tenant-da hər şey əvvəlki kimidir. Yeganə açar buradakı
:func:`organization_has_legacy_cohorts` funksiyasıdır ki, bütün səthlər
eyni meyardan oxusun (bir EXISTS sorğusu).
"""

from __future__ import annotations

from apps.exams.domain.access_policy import StudentGroup


def organization_has_legacy_cohorts(organization) -> bool:
    """Təşkilatda ən azı bir köhnə imtahan kohortu (`StudentGroup`) varmı — bir EXISTS sorğusu.

    Aktorun əhatəsinə görə deyil, TƏŞKİLAT səviyyəsində yoxlanır: dekanın
    öz alt-ağacında kohort olmasa da təşkilatda varsa, səth əvvəlki kimi
    qalmalıdır (tenant hələ kohortdan istifadə edir). `None` təşkilat →
    `False` (səth onsuz da aktiv təşkilat tələb edir).
    """
    if organization is None:
        return False
    return StudentGroup.objects.filter(organization=organization).exists()


__all__ = ["organization_has_legacy_cohorts"]
