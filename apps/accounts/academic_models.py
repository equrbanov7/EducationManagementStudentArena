"""İstifadəçinin özü idarə etdiyi akademik fəaliyyət qeydləri.

``models.py`` modul ölçü budcəsindən (SOFT_CAP=600) keçdiyi üçün ayrıldı —
MƏZMUN DƏYİŞMƏYİB. ``models`` faylı bu sinfi yenidən ixrac edir, ona görə
``from apps.accounts.models import AcademicProfileItem`` işləməyə davam edir.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy


class AcademicProfileItem(models.Model):
    """İstifadəçinin özü idarə etdiyi akademik fəaliyyət qeydi.

    Müəllim profilində məqalə/konfrans materialı/sertifikat/tədris etdiyi fənn
    kimi bəndlər; tələbə və digər rollar da öz nailiyyətlərini (sertifikat,
    məqalə və s.) əlavə edə bilir. Yalnız sahibinə redaktə icazəsi var —
    yoxlama servis qatındadır (apps.accounts.services.academic_profile).
    """

    class Kind(models.TextChoices):
        SUBJECT = "subject", pgettext_lazy("accounts.academic_item_kind", "Tədris etdiyi fənn")
        CERTIFICATE = "certificate", pgettext_lazy("accounts.academic_item_kind", "Sertifikat")
        PUBLICATION = "publication", pgettext_lazy("accounts.academic_item_kind", "Məqalə")
        CONFERENCE = "conference", pgettext_lazy("accounts.academic_item_kind", "Konfrans materialı")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="academic_items",
        verbose_name="İstifadəçi",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Növ")
    title = models.CharField(max_length=200, verbose_name="Başlıq")
    detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Ətraflı",
        help_text="Jurnal/konfrans adı, verən qurum, kafedra və s.",
    )
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="İl",
    )
    link = models.URLField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Keçid",
        help_text="DOI / sertifikat / nəşr keçidi (http-https)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akademik fəaliyyət qeydi"
        verbose_name_plural = "Akademik fəaliyyət qeydləri"
        ordering = ["kind", "-year", "-id"]
        indexes = [models.Index(fields=["user", "kind"])]

    def __str__(self):
        return f"{self.user_id} · {self.get_kind_display()} · {self.title[:40]}"


# Separate module keeps this already-large model module below the size budget.
