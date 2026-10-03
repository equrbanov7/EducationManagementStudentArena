"""«Sistem tənzimləmələri» — RİM rəhbərinin işləmə vaxtı dəyişdirdiyi limitlər (sahib 2026-10-03).

Bir sətir = bir açar (``core.runtime_settings.SPECS``). Sətir YOXDURSA kodun / mühitin defoltu işləyir;
sətir varsa onun ``value``-su. Tarixçə audit jurnalındadır (``runtime_settings.save_values``).
Cədvəl tenant-sız (bütün sistemə aiddir) — RLS siyasəti yoxdur; yazmaq yalnız RİM rəhbəri / superadmin.

⚠️ ``journal.mark_edit_hours`` açarını Postgres trigger-i də oxuyur (registrar 0084) — açar adını dəyişməyin.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class RuntimeSetting(models.Model):
    key = models.CharField(max_length=64, unique=True, verbose_name="Açar")
    value = models.JSONField(verbose_name="Dəyər")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="Dəyişən",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dəyişmə vaxtı")

    class Meta:
        verbose_name = "Sistem tənzimləməsi"
        verbose_name_plural = "Sistem tənzimləmələri"
        ordering = ("key",)

    def __str__(self) -> str:
        return f"{self.key}={self.value!r}"
