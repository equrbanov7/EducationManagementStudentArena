"""courses model paketi — üzvlük/təlimatçı/qrup."""

from django.db import models

from ._base import (
    User,
)
from .course import (
    Course,
)


class CourseMembership(models.Model):
    """
    Kurs üzvlüyü (kim bu kursda var?).

    Nə üçün:
    - Müəllim kurs yaradır (owner)
    - Tələbələr kursa qeydiyyatdan keçirlər (student)
    - Asistanlar kurs dəstəyi verir (assistant)
    - Qruplar tələbələri təşkil edir (group_name)

    Atributlar:
    - course: Hansı kurs
    - user: Hansı istifadəçi
    - role: müəllim / asistant / tələbə
    - group_name: Qrup adı (məs: "875i", "842A1")
    - joined_at: Qoşulma tarixi

    Misal:
    - CourseMembership(course=Python101, user=elvin, role='teacher')
    - CourseMembership(course=Python101, user=ayse, role='student', group_name='875i')
    - CourseMembership(course=Python101, user=ali, role='student', group_name='875i')
    """

    ROLE_CHOICES = (
        ("teacher", "Müəllim"),
        ("assistant", "Asistant"),
        ("student", "Tələbə"),
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name="Kurs",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="course_memberships",
        verbose_name="İstifadəçi",
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student", verbose_name="Rol")

    group_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Qrup Adı (isteğe bağlı)",
        help_text='Məs: "875i", "842A1". Tələbəyə aid qrup.',
    )

    joined_at = models.DateTimeField(auto_now_add=True, verbose_name="Qoşulma Tarixi")

    class Meta:
        verbose_name = "Kurs Üzvü"
        verbose_name_plural = "Kurs Üzvləri"
        unique_together = ("course", "user")
        indexes = [
            models.Index(fields=["course", "role"]),
            models.Index(fields=["course", "group_name"]),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.course.title} ({self.get_role_display()})"


class CourseInstructor(models.Model):
    """
    Kurs Müəllimləri və Asistantları.

    Nə üçün:
    - Bir kursda əsas müəllim və asistantlar ola bilər
    - Hər müəllimin fərqli səlahiyyətləri ola bilər
    - Qonaq müəllimlər dəvət edilə bilər

    Atributlar:
    - course: Hansı kurs
    - user: Hansı istifadəçi (müəllim/asistant)
    - role: primary (əsas), assistant (köməkçi), guest (qonaq)
    - permissions: JSON formatında səlahiyyətlər
    """

    ROLE_CHOICES = (
        ("primary", "Əsas Müəllim"),
        ("assistant", "Asistant"),
        ("guest", "Qonaq Müəllim"),
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="instructors",
        verbose_name="Kurs",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="instructor_courses",
        verbose_name="Müəllim/Asistant",
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="assistant",
        verbose_name="Rol",
    )

    permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Səlahiyyətlər",
        help_text="JSON: {'can_grade': true, 'can_edit': false, ...}",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Əlavə Edilmə Tarixi")

    class Meta:
        verbose_name = "Kurs Müəllimi"
        verbose_name_plural = "Kurs Müəllimləri"
        unique_together = ("course", "user")
        indexes = [
            models.Index(fields=["course", "role"]),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.course.title} ({self.get_role_display()})"


class CourseGroup(models.Model):
    """
    Kurs Qrupları (Praktikum/Laboratoriya qrupları).

    Nə üçün:
    - Böyük kurslar kiçik qruplara bölünə bilər
    - Hər qrupun öz cədvəli və müəllimi ola bilər
    - Tələbə sayı məhdudlaşdırıla bilər

    Atributlar:
    - course: Hansı kursa aid
    - name: Qrup adı (məs: "Qrup A", "Lab 1")
    - schedule: Cədvəl məlumatı (JSON)
    - instructor: Qrup müəllimi/asistantı
    - max_students: Maksimum tələbə sayı
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="course_groups",
        verbose_name="Kurs",
    )

    name = models.CharField(
        max_length=100,
        verbose_name="Qrup Adı",
        help_text="Məs: Qrup A, Lab 1, Praktikum 2",
    )

    schedule = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Cədvəl",
        help_text="JSON: {'day': 'Monday', 'time': '10:00', 'room': '301'}",
    )

    instructor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="instructed_groups",
        verbose_name="Qrup Müəllimi",
        help_text="Bu qrupu tədris edən müəllim/asistant",
    )

    max_students = models.PositiveIntegerField(
        default=30,
        verbose_name="Maksimum Tələbə Sayı",
        help_text="Bu qrupa daxil ola biləcək maksimum tələbə sayı",
    )

    members = models.ManyToManyField(
        User,
        blank=True,
        related_name="course_group_memberships",
        verbose_name="Qrup Üzvləri",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma Tarixi")

    class Meta:
        verbose_name = "Kurs Qrupu"
        verbose_name_plural = "Kurs Qrupları"
        unique_together = ("course", "name")
        indexes = [
            models.Index(fields=["course"]),
            models.Index(fields=["instructor"]),
        ]

    def __str__(self):
        return f"{self.course.title} - {self.name}"

    @property
    def student_count(self):
        """Bu qrupda neçə tələbə var?"""
        return self.members.count()

    @property
    def is_full(self):
        """Qrup dolubmu?"""
        return self.student_count >= self.max_students
