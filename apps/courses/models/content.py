"""courses model paketi — mövzu/resurs."""

from django.db import models

from .course import (
    Course,
)


class CourseTopic(models.Model):
    """
    Kurs Mövzusu (Həftə, Bölmə, Unit, və s.).

    Nə üçün:
    - Kurs mövzulara bölünür (məsələn: "Həftə 1", "Həftə 2")
    - Hər mövzunun resursları, açıklaması, sırası var

    Atributlar:
    - course: Hansı kursa aiddir
    - title: Mövzu adı (məs: "Həftə 1: Giriş")
    - description: Mövzu təsviri
    - order: Sıra nömrəsi (1, 2, 3, ...)
    - created_at: Yaradılma tarixi

    Misal:
    - CourseTopic(course=Python101, title="Həftə 1: Giriş", order=1)
    - CourseTopic(course=Python101, title="Həftə 2: Dəyişkənlər", order=2)

    Related:
    - resources: topic.resources.all() → Bu mövzuya aid resurslar
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="topics",
        verbose_name="Kurs",
        help_text="Bu mövzu hansı kursa aiddir",
    )

    title = models.CharField(max_length=255, verbose_name="Mövzu Adı")

    description = models.TextField(blank=True, verbose_name="Mövzu Təsviri")

    order = models.PositiveIntegerField(
        default=1,
        verbose_name="Sıra Nömrəsi",
        help_text="1, 2, 3, ... (hansı mövzu əvvəl göstərilsin)",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma Tarixi")

    class Meta:
        verbose_name = "Kurs Mövzusu"
        verbose_name_plural = "Kurs Mövzuları"
        ordering = ["course", "order"]
        unique_together = ("course", "order")
        indexes = [
            models.Index(fields=["course", "order"]),
        ]

    def __str__(self):
        return f"{self.course.title} → {self.title}"


class CourseResource(models.Model):
    """
    Kurs Resursu (Fayl, Link, Video, Sənəd, və s.).

    Nə üçün:
    - Tələbələr kurs materiallarına ehtiyac duyur
    - Müəllim PDF, Link, Video, və s. paylaşır
    - Mövzuya aiddir (topic), amma isteğe bağlı

    Atributlar:
    - course: Hansı kursa aiddir
    - topic: İsteğe bağlı, hansı mövzuya aid
    - title: Resurs adı
    - description: Açıqlama
    - resource_type: file / link / document / video
    - file: Yüklənmiş fayl (FileField)
    - url: Xarici link (URLField)
    - created_at: Yaradılma tarixi

    Misal:
    - CourseResource(course=Python101, title="Giriş PDF", file="intro.pdf")
    - CourseResource(course=Python101, title="Python Docs", url="https://docs.python.org")
    """

    RESOURCE_TYPE_CHOICES = (
        ("file", "Fayl (PDF, ZIP, və s.)"),
        ("link", "Xarici Link"),
        ("document", "Sənəd"),
        ("video", "Video"),
    )

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="resources", verbose_name="Kurs")

    topic = models.ForeignKey(
        CourseTopic,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resources",
        verbose_name="Mövzu (isteğe bağlı)",
        help_text="Bu resurs hansı mövzuya aid (boş olabilər - kurs səviyyəsində)",
    )

    title = models.CharField(max_length=255, verbose_name="Resurs Başlığı")

    description = models.TextField(blank=True, verbose_name="Açıqlama")

    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPE_CHOICES,
        default="file",
        verbose_name="Resurs Tipi",
    )

    file = models.FileField(
        upload_to="course_resources/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Fayl",
        help_text="Fayl yükləyin (PDF, ZIP, IMG, və s.)",
    )

    url = models.URLField(blank=True, verbose_name="URL Linki", help_text="Məs: https://docs.python.org")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma Tarixi")

    class Meta:
        verbose_name = "Kurs Resursu"
        verbose_name_plural = "Kurs Resursları"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["course", "topic"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_resource_type_display()})"

    def is_file(self):
        """Bu resurs fayl mı?"""
        return bool(self.file)

    def is_link(self):
        """Bu resurs link mı?"""
        return bool(self.url) and not self.file
