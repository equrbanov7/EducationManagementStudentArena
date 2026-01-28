"""
labs/models.py
──────────────
Lab İşləri modulu.

Modellər:
1. Lab - Əsas lab işi
2. LabBlock - Sual bloku
3. LabQuestion - Sual
4. LabAssignment - Tələbəyə təyin olunan suallar
5. LabSubmission - Tələbənin cavabı
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
import hashlib
import random

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# 1. LAB MODEL
# ════════════════════════════════════════════════════════════════════════════

class Lab(models.Model):
    """
    Əsas Lab İşi modeli.
    
    Müəllim lab yaradır, suallar əlavə edir, tələbələrə paylayır.
    """
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Yayımlandı'),
        ('archived', 'Arxivləndi'),
    ]
    
    allowed_students = models.TextField(
        blank=True,
        verbose_name='İcazəli tələbələr (ID)',
        help_text='Vergüllə ayrılmış tələbə ID-ləri. Boş = qrup filtri istifadə olunur'
    )       
    
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='labs',
        verbose_name='Kurs'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Lab Adı'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Təsvir',
        help_text='Lab işinin təsviri, tələblər və s.'
    )
    
    # Tarixlər
    start_datetime = models.DateTimeField(
        verbose_name='Başlanğıc tarixi',
        help_text='Bu tarixdən sonra tələbələr labı görə bilər'
    )
    
    end_datetime = models.DateTimeField(
        verbose_name='Son tarix (Deadline)',
        help_text='Bu tarixdən sonra göndəriş qəbul olunmur'
    )
    
    # Qiymətləndirmə
    max_score = models.PositiveIntegerField(
        default=100,
        verbose_name='Maksimum bal'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='Status'
    )
    
    # Gecikmə
    allow_late_submission = models.BooleanField(
        default=False,
        verbose_name='Gecikmiş göndərişə icazə ver'
    )
    
    late_penalty_percent = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        verbose_name='Gecikmə cəzası (%)',
        help_text='Hər gün üçün neçə % çıxılsın'
    )
    
    # Müəllim faylları
    teacher_files = models.FileField(
        upload_to='labs/teacher_files/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Müəllim faylı',
        help_text='PDF, ZIP, DOC və s.'
    )
    
    teacher_instructions = models.TextField(
        blank=True,
        verbose_name='Müəllim təlimatları',
        help_text='Tələbələr üçün əlavə təlimat (text formatında)'
    )
    
    # Submission ayarları
    allow_file_upload = models.BooleanField(
        default=True,
        verbose_name='Fayl yükləməyə icazə'
    )
    
    allow_link_submission = models.BooleanField(
        default=True,
        verbose_name='Link göndərməyə icazə'
    )
    
    allowed_extensions = models.CharField(
        max_length=255,
        default='zip,pdf,docx,png,jpg,txt,py,java,cpp',
        verbose_name='İcazə verilən fayl tipləri',
        help_text='Vergüllə ayırın: zip,pdf,docx'
    )
    
    max_file_size_mb = models.PositiveIntegerField(
        default=50,
        verbose_name='Maks fayl ölçüsü (MB)'
    )
    
    # Random sual ayarları
    questions_per_student = models.PositiveIntegerField(
        default=0,
        verbose_name='Hər tələbəyə düşən sual sayı',
        help_text='0 = bütün suallar, >0 = random seçim'
    )
    
    # Qrup filtri (optional)
    allowed_groups = models.TextField(
        blank=True,
        verbose_name='İcazəli qruplar',
        help_text='Vergüllə ayırın: 850,860. Boş = bütün kurs'
    )
    
    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_labs',
        verbose_name='Yaradan'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lab İşi'
        verbose_name_plural = 'Lab İşləri'
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    @property
    def is_open(self):
        """Lab açıqdır?"""
        now = timezone.now()
        return self.status == 'published' and self.start_datetime <= now <= self.end_datetime
    
    @property
    def is_upcoming(self):
        """Lab hələ açılmayıb?"""
        return self.status == 'published' and timezone.now() < self.start_datetime
    
    @property
    def is_closed(self):
        """Lab bağlanıb?"""
        return timezone.now() > self.end_datetime
    
    @property
    def total_questions(self):
        """Ümumi sual sayı"""
        return LabQuestion.objects.filter(block__lab=self).count()
    
    def get_allowed_groups_list(self):
        """İcazəli qrupları list kimi qaytar"""
        if not self.allowed_groups:
            return []
        return [g.strip() for g in self.allowed_groups.split(',') if g.strip()]
    
    def get_allowed_extensions_list(self):
        """İcazəli extension-ları list kimi qaytar"""
        return [ext.strip().lower() for ext in self.allowed_extensions.split(',') if ext.strip()]


# ════════════════════════════════════════════════════════════════════════════
# 2. LAB BLOCK MODEL
# ════════════════════════════════════════════════════════════════════════════

class LabBlock(models.Model):
    """
    Sual Bloku.
    
    Müəllim sualları bloklara ayıra bilər.
    Hər blokdan neçə sual düşəcəyini təyin edə bilər.
    """
    
    lab = models.ForeignKey(
        Lab,
        on_delete=models.CASCADE,
        related_name='blocks',
        verbose_name='Lab'
    )
    
    title = models.CharField(
        max_length=255,
        verbose_name='Blok adı',
        help_text='Məs: "Asan suallar", "Orta", "Çətin"'
    )
    
    description = models.TextField(
        blank=True,
        verbose_name='Blok təsviri'
    )
    
    order = models.PositiveIntegerField(
        default=1,
        verbose_name='Sıra'
    )
    
    # Bu blokdan neçə sual düşsün?
    questions_to_pick = models.PositiveIntegerField(
        default=0,
        verbose_name='Bu blokdan seçiləcək sual sayı',
        help_text='0 = bütün suallar'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['lab', 'order']
        verbose_name = 'Sual Bloku'
        verbose_name_plural = 'Sual Blokları'
    
    def __str__(self):
        return f"{self.lab.title} - {self.title}"
    
    @property
    def question_count(self):
        return self.questions.count()


# ════════════════════════════════════════════════════════════════════════════
# 3. LAB QUESTION MODEL
# ════════════════════════════════════════════════════════════════════════════

class LabQuestion(models.Model):
    """
    Lab Sualı.
    
    Hər sual bir bloka aiddir.
    Müəllim tək-tək və ya toplu əlavə edə bilər.
    """
    
    block = models.ForeignKey(
        LabBlock,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Blok'
    )
    
    question_number = models.PositiveIntegerField(
        default=1,
        verbose_name='Sual nömrəsi'
    )
    
    question_text = models.TextField(
        verbose_name='Sual mətni'
    )
    
    # Əlavə materiallar
    attachment = models.FileField(
        upload_to='labs/questions/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Əlavə fayl'
    )
    
    # Sual balı (optional, əgər suallar fərqli bal daşıyırsa)
    points = models.PositiveIntegerField(
        default=0,
        verbose_name='Bal',
        help_text='0 = bərabər paylanacaq'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['block', 'question_number']
        verbose_name = 'Lab Sualı'
        verbose_name_plural = 'Lab Sualları'
    
    def __str__(self):
        return f"Sual {self.question_number}: {self.question_text[:50]}..."


# ════════════════════════════════════════════════════════════════════════════
# 4. LAB ASSIGNMENT MODEL (Tələbəyə təyin olunan suallar)
# ════════════════════════════════════════════════════════════════════════════

class LabAssignment(models.Model):
    """
    Tələbə ↔ Lab bağlantısı.
    
    Hər tələbəyə random suallar təyin olunur və burada saxlanılır.
    Bu, eyni tələbənin hər dəfə eyni sualları görməsini təmin edir.
    """
    
    lab = models.ForeignKey(
        Lab,
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Lab'
    )
    
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='lab_assignments',
        verbose_name='Tələbə'
    )
    
    # Təyin olunan suallar (ManyToMany)
    assigned_questions = models.ManyToManyField(
        LabQuestion,
        related_name='assignments',
        verbose_name='Təyin olunan suallar'
    )
    
    # Nə vaxt təyin olundu
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('lab', 'student')
        verbose_name = 'Lab Təyinatı'
        verbose_name_plural = 'Lab Təyinatları'
    
    def __str__(self):
        return f"{self.student.username} - {self.lab.title}"
    
    @classmethod
    def get_or_create_for_student(cls, lab, student):
        """
        Tələbə üçün assignment yarat və ya mövcud olanı qaytar.
        Random sualları deterministic şəkildə seç (həmişə eyni).
        """
        assignment, created = cls.objects.get_or_create(
            lab=lab,
            student=student
        )
        
        if created:
            # Sualları seç
            assignment._assign_questions()
        
        return assignment
    
    def _assign_questions(self):
        """Random sualları seç və təyin et"""
        all_questions = []
        
        for block in self.lab.blocks.all():
            block_questions = list(block.questions.all())
            
            if block.questions_to_pick > 0 and block.questions_to_pick < len(block_questions):
                # Deterministic random: həmişə eyni seed
                seed = int(hashlib.md5(
                    f"{self.lab.id}-{self.student.id}-{block.id}".encode()
                ).hexdigest(), 16)
                rng = random.Random(seed)
                selected = rng.sample(block_questions, block.questions_to_pick)
                all_questions.extend(selected)
            else:
                # Bütün sualları əlavə et
                all_questions.extend(block_questions)
        
        # Lab səviyyəsində limit varsa
        if self.lab.questions_per_student > 0 and self.lab.questions_per_student < len(all_questions):
            seed = int(hashlib.md5(
                f"{self.lab.id}-{self.student.id}-total".encode()
            ).hexdigest(), 16)
            rng = random.Random(seed)
            all_questions = rng.sample(all_questions, self.lab.questions_per_student)
        
        self.assigned_questions.set(all_questions)


# ════════════════════════════════════════════════════════════════════════════
# 5. LAB SUBMISSION MODEL
# ════════════════════════════════════════════════════════════════════════════

class LabSubmission(models.Model):
    """
    Tələbənin Lab Cavabı.
    
    Fayl və/və ya link göndərə bilər.
    """
    
    STATUS_CHOICES = [
        ('submitted', 'Göndərilib'),
        ('late', 'Gecikmiş'),
        ('graded', 'Qiymətləndirilib'),
        ('returned', 'Qaytarıldı'),
    ]
    
    assignment = models.ForeignKey(
        LabAssignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='Təyinat'
    )
    
    # Cavab
    submission_text = models.TextField(
        blank=True,
        verbose_name='Cavab mətni',
        help_text='Əlavə qeyd, izahat'
    )
    
    submission_file = models.FileField(
        upload_to='labs/submissions/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Fayl'
    )
    
    submission_link = models.URLField(
        blank=True,
        verbose_name='Link',
        help_text='GitHub, Google Drive, Figma və s.'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted',
        verbose_name='Status'
    )
    
    # Qiymətləndirmə
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Qiymət'
    )
    
    feedback = models.TextField(
        blank=True,
        verbose_name='Müəllim rəyi'
    )
    
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='graded_lab_submissions',
        verbose_name='Qiymətləndirən'
    )
    
    graded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Qiymətləndirmə tarixi'
    )
    
    # Metadata
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Attempt tracking
    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name='Cəhd nömrəsi'
    )
    
    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Lab Cavabı'
        verbose_name_plural = 'Lab Cavabları'
    
    def __str__(self):
        return f"{self.assignment.student.username} - {self.assignment.lab.title} (Cəhd {self.attempt_number})"
    
    @property
    def is_late(self):
        """Gecikmiş göndəriş?"""
        return self.submitted_at > self.assignment.lab.end_datetime
    
    def save(self, *args, **kwargs):
        # Gecikmiş göndərişi avtomatik işarələ
        if not self.pk and self.is_late:
            self.status = 'late'
        super().save(*args, **kwargs)