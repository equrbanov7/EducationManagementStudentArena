"""Sillabusun 10 bölməsi — versiya başına bir sətir/bölmə.

Niyə JSON sahə, niyə ayrıca cədvəl DEYİL: bölmələrin daxili strukturu bir-birinə
BƏNZƏMİR (mətn, siyahı, 16 sətirlik saat cədvəli, checkbox dəsti). Hər biri üçün
ayrıca cədvəl 8 əlavə model deməkdir, halbuki sorğu ehtiyacı yoxdur — bölmə
həmişə TAM oxunur/yazılır. Buna görə ``data`` JSON-dur, amma bölmənin ÖZÜ
sətirdir: autosave (PATCH) bölmə səviyyəsində gedir, ``revision`` sayğacı
optimistik kilid verir (redaktorun ``conflict``/``stale`` vəziyyətləri).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import SectionKey

_CTX = "syllabus.model"


class SyllabusSection(UUIDModel, TimeStampedModel):
    """Bir versiyanın bir bölməsi."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="syllabus_sections"
    )
    version = models.ForeignKey("syllabus.SyllabusVersion", on_delete=models.CASCADE, related_name="sections")
    section_id = models.CharField(
        max_length=16,
        choices=SectionKey.choices,
        help_text="Bölmə açarı — dizayn paketindəki `id` ilə eyni (info/desc/out/…).",
    )
    data = models.JSONField(default=dict, blank=True)
    is_complete = models.BooleanField(
        default=False,
        help_text="Biznes qaydası ödənilibmi (servis hesablayır; doldurulmuş input sayı DEYİL).",
    )
    revision = models.PositiveIntegerField(
        default=0,
        help_text="Optimistik kilid sayğacı — hər uğurlu autosave-də 1 artır.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sillabus bölməsi")
        verbose_name_plural = pgettext_lazy(_CTX, "sillabus bölmələri")
        ordering = ["version", "section_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "version", "section_id"],
                name="uniq_syllabus_section_per_version",
            ),
        ]
        indexes = [models.Index(fields=["organization", "version"])]

    def __str__(self):
        return f"{self.version_id} · {self.section_id}"
