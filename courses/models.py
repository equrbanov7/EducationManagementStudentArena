"""
courses/models.py
─────────────────
Kurs modulu əsas modelləri.

Modelləri izah:
1. Course - Əsas kurs
2. CourseMembership - Kursda kim var (müəllim, tələbə, qrup)
3. CourseTopic - Mövzu/Həftə
4. CourseResource - Resurs (fayl, link)

Clean Code Prinsipləri:
✓ Verbose names (Azərbaycan dili)
✓ Related names (intuitive: course.topics, course.memberships)
✓ Docstrings (model nə üçün)
✓ Indexes (performans)
✓ Validators
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from django.utils.crypto import get_random_string
import itertools


# ════════════════════════════════════════════════════════════════════════════
# 1. COURSE MODEL
# ════════════════════════════════════════════════════════════════════════════

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
        ('draft', 'Draft (yayımlanmayıb)'),
        ('published', 'Yayımlandı'),
        ('archived', 'Arxivləndi'),
    )
    
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='taught_courses',
        verbose_name='Müəllif (Müəllim)',
        help_text='Kursun sahibi olan müəllim'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Kurs Adı'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Kurs Təsviri'
    )
    
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        verbose_name='URL Slug'
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='Status',
        help_text='Draft: tələbələr görmə, Published: görsün'
    )
    
    cover_image = models.ImageField(
        upload_to='course_covers/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Kurs Şəkli'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yaradılma Tarixi'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Yenilənmə Tarixi'
    )
    
    
    class Meta:
        verbose_name = 'Kurs'
        verbose_name_plural = 'Kurslar'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['slug']),
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
        
        super().save(*args, **kwargs)
    
    def is_owner(self, user):
        """Bu müəllim kursun sahibimi?"""
        return self.owner == user
    
    @property
    def topic_count(self):
        """Kursda neçə mövzu var?"""
        return self.topics.count()
    
    @property
    def student_count(self):
        """Neçə tələbə qeydiyyatdan keçib?"""
        return self.memberships.filter(role='student').count()


# ════════════════════════════════════════════════════════════════════════════
# 2. COURSE MEMBERSHIP MODEL
# ════════════════════════════════════════════════════════════════════════════

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
        ('teacher', 'Müəllim'),
        ('assistant', 'Asistant'),
        ('student', 'Tələbə'),
    )
    
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name='Kurs'
    )
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='course_memberships',
        verbose_name='İstifadəçi'
    )
    
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='student',
        verbose_name='Rol'
    )
    
    group_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Qrup Adı (isteğe bağlı)',
        help_text='Məs: "875i", "842A1". Tələbəyə aid qrup.'
    )
    
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Qoşulma Tarixi'
    )
    
    class Meta:
        verbose_name = 'Kurs Üzvü'
        verbose_name_plural = 'Kurs Üzvləri'
        unique_together = ('course', 'user')
        indexes = [
            models.Index(fields=['course', 'role']),
            models.Index(fields=['course', 'group_name']),
        ]
    
    def __str__(self):
        return f"{self.user.username} → {self.course.title} ({self.get_role_display()})"


# ════════════════════════════════════════════════════════════════════════════
# 3. COURSE TOPIC MODEL (Mövzu/Həftə)
# ════════════════════════════════════════════════════════════════════════════

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
        related_name='topics',
        verbose_name='Kurs',
        help_text='Bu mövzu hansı kursa aiddir'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Mövzu Adı'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Mövzu Təsviri'
    )
    
    order = models.PositiveIntegerField(
        default=1,
        verbose_name='Sıra Nömrəsi',
        help_text='1, 2, 3, ... (hansı mövzu əvvəl göstərilsin)'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yaradılma Tarixi'
    )
    
    class Meta:
        verbose_name = 'Kurs Mövzusu'
        verbose_name_plural = 'Kurs Mövzuları'
        ordering = ['course', 'order']
        unique_together = ('course', 'order')
        indexes = [
            models.Index(fields=['course', 'order']),
        ]
    
    def __str__(self):
        return f"{self.course.title} → {self.title}"


# ════════════════════════════════════════════════════════════════════════════
# 4. COURSE RESOURCE MODEL (Resurs/Fayl/Link)
# ════════════════════════════════════════════════════════════════════════════

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
        ('file', 'Fayl (PDF, ZIP, və s.)'),
        ('link', 'Xarici Link'),
        ('document', 'Sənəd'),
        ('video', 'Video'),
    )
    
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='resources',
        verbose_name='Kurs'
    )
    
    topic = models.ForeignKey(
        CourseTopic,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='resources',
        verbose_name='Mövzu (isteğe bağlı)',
        help_text='Bu resurs hansı mövzuya aid (boş olabilər - kurs səviyyəsində)'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Resurs Başlığı'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Açıqlama'
    )
    
    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPE_CHOICES,
        default='file',
        verbose_name='Resurs Tipi'
    )
    
    file = models.FileField(
        upload_to='course_resources/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Fayl',
        help_text='Fayl yükləyin (PDF, ZIP, IMG, və s.)'
    )
    
    url = models.URLField(
        blank=True,
        verbose_name='URL Linki',
        help_text='Məs: https://docs.python.org'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Yaradılma Tarixi'
    )
    
    class Meta:
        verbose_name = 'Kurs Resursu'
        verbose_name_plural = 'Kurs Resursları'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course', 'topic']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.get_resource_type_display()})"
    
    def is_file(self):
        """Bu resurs fayl mı?"""
        return bool(self.file)
    
    def is_link(self):
        """Bu resurs link mı?"""
        return bool(self.url) and not self.file