"""courses model paketi — Course (əsas)."""

import itertools

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify
from django.utils.translation import pgettext_lazy

from ._base import (
    User,
)


class Course(models.Model):
    """
    Əsas Kurs modeli.

    Nə üçün:
    - Müəllim bir neçə kurs yarada bilər
    - Hər kursun öz mövzuları, işləri, resursları var

    Atributlar:
    - owner: Müəllim (FK → User)
    - title: Kurs adı
    - description: Kurs təsviri
    - slug: URL-də istifadə üçün (otomatik)
    - status: draft / published / archived
    - cover_image: Kurs şəkli
    - created_at, updated_at: Vaxt məlumatı

    Related (sorğu üçün):
    - topics: course.topics.all() → Mövzular
    - memberships: course.memberships.all() → Üzvlər (tələbələr, qruplar)
    - resources: course.resources.all() → Resurslar
    """

    STATUS_CHOICES = (
        ("draft", "Draft (yayımlanmayıb)"),
        ("published", "Yayımlandı"),
        ("archived", "Arxivləndi"),
    )

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="taught_courses",
        verbose_name="Müəllif (Müəllim)",
        help_text="Kursun sahibi olan müəllim",
    )

    title = models.CharField(max_length=255, verbose_name="Kurs Adı")

    description = models.TextField(blank=True, verbose_name="Kurs Təsviri")

    slug = models.SlugField(max_length=255, unique=True, blank=True, verbose_name="URL Slug")

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="Status",
        help_text="Draft: tələbələr görmə, Published: görsün",
    )

    cover_image = models.ImageField(
        upload_to="course_covers/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Kurs Şəkli",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma Tarixi")

    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yenilənmə Tarixi")

    # ══════════════════════════════════════════════════════════════════════════
    # SPRINT 7: YENİ SAHƏLƏR
    # ══════════════════════════════════════════════════════════════════════════

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="courses",
        verbose_name="Təşkilat",
        help_text="Kursun aid olduğu təşkilat",
    )

    unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses",
        verbose_name="Kafedra/Şöbə",
        help_text="Kursun aid olduğu kafedra və ya şöbə",
    )

    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses",
        verbose_name="Akademik Dövr",
        help_text="Kursun aid olduğu akademik dövr (semestr, trisemestr, və s.)",
    )

    GRADING_TYPE_CHOICES = (
        ("percentage", "Faiz (0-100)"),
        ("letter", "Hərf (A, B, C, D, F)"),
        ("pass_fail", "Keç/Qal"),
        ("points", "Xal sistemi"),
    )

    grading_type = models.CharField(
        max_length=20,
        choices=GRADING_TYPE_CHOICES,
        default="percentage",
        verbose_name="Qiymətləndirmə Tipi",
        help_text="Kursun qiymətləndirmə metodunu seçin",
    )

    passing_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Keçid Qiyməti",
        help_text="Minimum keçid balı (məs: 50.00)",
    )

    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Əlavə Parametrlər",
        help_text="JSON formatında əlavə tənzimləmələr",
    )

    class Meta:
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """
        Slug avtomatik generasiya (əgər yoxdursa).

        Misal:
        - title: "Python Başlanğıc"
        - slug: "python-baslangic-a1b2c3"
        (Unikallığı təmin etmək üçün sonunda random string əlavə edilir)
        """
        if not self.slug:
            base_slug = slugify(self.title)

            # Əgər həmin slug artıq varsa, rəqəm əlavə et
            original_slug = base_slug
            for x in itertools.count(1):
                if not Course.objects.filter(slug=base_slug).exists():
                    break
                base_slug = f"{original_slug}-{x}"

            self.slug = base_slug

        if self.organization_id is None and self.owner_id:
            profile = getattr(self.owner, "profile", None)
            self.organization = getattr(profile, "organization", None)

        if self.organization_id is None:
            raise ValidationError(pgettext_lazy("courses.model.course.error", "organization_required"))

        super().save(*args, **kwargs)

    def is_owner(self, user):
        """Bu müəllim kursun sahibimi?"""
        return self.owner == user

    @property
    def cover_image_url(self):
        """Return the cover image URL only when the file still exists in storage."""
        if not self.cover_image:
            return ""

        name = getattr(self.cover_image, "name", "")
        if not name:
            return ""

        try:
            if not self.cover_image.storage.exists(name):
                return ""
            return self.cover_image.url
        except Exception:
            return ""

    @property
    def topic_count(self):
        """Kursda neçə mövzu var?"""
        return self.topics.count()

    @property
    def student_count(self):
        """Neçə tələbə qeydiyyatdan keçib?"""
        return self.memberships.filter(role="student").count()
