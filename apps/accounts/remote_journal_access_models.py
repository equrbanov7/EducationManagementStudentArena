"""«Kənardan jurnal girişi» — universitet şəbəkəsindən kənarda jurnala girə bilən hesablar (sahib 2026-11-20).

Sahib: «Bu profilə access ver ki, kənardan mən kimi daxil ola bilsin … sistem tənzimləmələri yerində olsun, ordan
mən bunları əlavə edib çıxara bilim». Əvvəl istisna YALNIZ mühit dəyişənində idi (``JOURNAL_REMOTE_USER_IDS``,
deploy tələb edirdi); indi RİM rəhbəri / superadmin kabinetdən hesab əlavə edib geri ala bilir. Mühit siyahısı
olduğu kimi işləyir (sahibin öz hesabı) — yoxlama ``journal_remote_access.journal_remote_access_allowed``-dadır.

Bir sətir = bir icazə. ``revoked_at`` boşdursa icazə QÜVVƏDƏDİR; geri alınanda sətir silinmir (tarixçə qalır),
yenidən verilmək üçün təzə sətir yaranır. Eyni hesabın EYNİ ANDA yalnız bir aktiv icazəsi ola bilər (qismən unikal
indeks). Cədvəl tenant-sızdır — şəbəkə istisnası bütün sistemə aiddir (mühit siyahısı kimi), nginx-in
``auth_request`` yoxlaması tenant kontekstindən asılı olmasın; RLS siyasəti yoxdur, yazmaq yalnız RİM rəhbəri /
superadmin (``services.remote_journal_access``). Rol, RBAC, admin 2FA və digər zona qaydaları DƏYİŞMİR.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q


class RemoteJournalAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="remote_journal_access_grants",
        verbose_name="Hesab",
    )
    note = models.CharField(max_length=255, blank=True, default="", verbose_name="Qeyd")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Verən",
    )
    granted_at = models.DateTimeField(auto_now_add=True, verbose_name="Verilmə vaxtı")
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Geri alan",
    )
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="Geri alınma vaxtı")

    class Meta:
        verbose_name = "Kənardan jurnal girişi"
        verbose_name_plural = "Kənardan jurnal girişləri"
        ordering = ("-granted_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=Q(revoked_at__isnull=True),
                name="accounts_remote_journal_access_one_active",
            )
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:
        return f"remote-journal:{self.user_id}{'' if self.revoked_at is None else ' (revoked)'}"
