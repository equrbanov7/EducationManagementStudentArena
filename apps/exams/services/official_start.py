"""Rəsmi (final/midterm) cəhdin yaradılması anında «bir gündə bir imtahan» qaydasının kilid altında yoxlanması.

2026-10-13 (gecə). Sahibin tələbi: «bir gündə tələbənin final imtahanında ancaq 1 fəndən imtahan
verə bilməsi». Qayda (2026-07, ``ExamAccessPolicyMixin._concurrent_or_same_day_block``) artıq
var idi — eyni anda bir imtahan + eyni gündə bir rəsmi (final/midterm) imtahan, imtahan
mərkəzinin «ikinci şans» qrantı istisnadır — AMMA:

1. Bilet axını (``begin_attempt_for_ticket`` — nəzarətçinin «Başlat»-ı, bilet PIN-i ilə giriş)
   ``can_user_start``-ı çağırmırdı → zal axınında eyni gündə ikinci final başlaya bilirdi.
2. Yoxlama kilidsiz idi: start actor-lock-u ``(imtahan, tələbə)`` üzrədir, yəni İKİ FƏRQLİ
   imtahanın eyni anda başladılması hər ikisini «bu gün heç nə verməyib» görüb keçirdi.

İndi cəhdi yaradan hər yol (``_create_attempt_or_get_active``) rəsmi imtahan üçün tələbənin
``auth_user`` sətrini ``SELECT … FOR UPDATE`` ilə kilidləyib qaydanı YENİDƏN yoxlayır —
paralel ikinci start birincinin commit-ini gözləyir və onun açıq cəhdini görür. Gün sərhədi
``timezone.localdate()`` — ``TIME_ZONE = "Asia/Baku"``.

Qiymət: yalnız YENİ rəsmi cəhd yaradılanda bir PK kilidi + mövcud yoxlamanın sorğuları;
davam (resume), sınaq cəhdi, müəllif və adi imtahanlar toxunulmur.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

OFFICIAL_DAY_RULE_KINDS = frozenset({"final", "midterm"})


class OfficialStartBlocked(Exception):
    """Yeni rəsmi cəhd qayda ilə bloklandı; ``reason`` — lokalizə olunmuş mesaj."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def official_day_rule_applies(exam, user, *, is_trial: bool = False) -> bool:
    if is_trial or getattr(exam, "exam_type_extended", None) not in OFFICIAL_DAY_RULE_KINDS:
        return False
    user_pk = getattr(user, "pk", None)
    return user_pk is not None and user_pk != getattr(exam, "author_id", None)


def lock_and_check_official_start(exam, user, *, is_trial: bool = False) -> None:
    """``transaction.atomic`` DAXİLİNDƏ çağırılır; bloklanıbsa ``OfficialStartBlocked``."""
    if not official_day_rule_applies(exam, user, is_trial=is_trial):
        return
    # Tələbə səviyyəli serializasiya: eyni tələbənin paralel rəsmi startları növbəyə düşür.
    get_user_model().objects.select_for_update().filter(pk=user.pk).values_list("pk", flat=True).first()
    blocked, reason = exam._concurrent_or_same_day_block(user)
    if blocked:
        raise OfficialStartBlocked(reason)


__all__ = [
    "OFFICIAL_DAY_RULE_KINDS",
    "OfficialStartBlocked",
    "lock_and_check_official_start",
    "official_day_rule_applies",
]
