"""Kabinet qabığı üçün ``UserProfile``-ın request boyu BİR dəfə yüklənməsi.

2026-09-13 (Codex audit §14/§21 — kabinet qabığı sorğu büdcəsi). Əvvəl hər
kabinet səhifəsi profili iki dəfə oxuyurdu: ``OrganizationMiddleware``
``user.is_superadmin`` üçün ``user.profile``-ı yükləyir (əks-O2O keşi user
instansında qalır), sonra ``_stage_1`` eyni sətri ``get_or_create`` ilə təzədən
SELECT edirdi. Burada əvvəlcə instansdakı keş yoxlanılır; profil YOXDURSA
davranış köhnə ilə eynidir — ``get_or_create`` yaradır.
"""

from django.core.exceptions import ObjectDoesNotExist

from ...models import UserProfile


def _load_user_profile(user):
    """``(profile, created)`` — ``UserProfile.objects.get_or_create(user=user)``-in
    keş-xəbərdar ekvivalenti.

    * Middleware ``user.profile``-ı artıq yükləyibsə → 0 sorğu (eyni sətir,
      eyni request; arada yazı yoxdur).
    * Keş yoxdursa → 1 SELECT (əvvəlki ``get_or_create`` ilə eyni).
    * Sətir yoxdursa → ``get_or_create`` yaradır və instans keşinə yazır ki,
      sonrakı ``user.profile`` oxunuşları (``is_superadmin`` və s.) da təzədən
      sorğu etməsin.
    """
    try:
        profile = user.profile
    except (ObjectDoesNotExist, AttributeError):
        profile = None
    if profile is not None:
        return profile, False
    profile, created = UserProfile.objects.get_or_create(user=user)
    try:
        user.profile = profile
    except Exception:  # noqa: BLE001 — dəyişməz/mock user obyektləri üçün (nadir)
        pass
    return profile, created
