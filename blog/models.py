# blog/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.contrib.auth.models import Group
import itertools
from django.templatetags.static import static
from .validators import validate_file_extension, validate_file_size, validate_zip_contents

# ---- Models for Category functionality ----

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        verbose_name = "Kateqoriya"
        verbose_name_plural = "Kateqoriyalar"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Slug boşdursa və ya dəyişdirilibsə yenilə
        if not self.slug:
            self.slug = slugify(self.name)
            
            # Əgər bu slug artıq varsa, sonuna rəqəm artır (nadir halda)
            original_slug = self.slug
            for x in itertools.count(1):
                if not Category.objects.filter(slug=self.slug).exists():
                    break
                self.slug = '%s-%d' % (original_slug, x)
                
        super().save(*args, **kwargs)


# ---- Post Model ----

class Post(models.Model):
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    # Burada related_name="posts" qalsa yaxşıdır, kateqoriyadan postları çağırmaq üçün
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL, # Kateqoriya silinsə, məqalə silinməsin, kategoriyasız qalsın
        null=True,
        blank=True,
        related_name="posts", 
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True) # Blank=True qoyduq ki, admin paneldə məcburi istəməsin
    excerpt = models.TextField(blank=True)
    content = models.TextField()
    
    image_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    image = models.ImageField(upload_to='post_images/', blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # 1. Slug yarat (əgər yoxdursa)
        if not self.slug:
            self.slug = slugify(self.title)

        # 2. Unikallığı yoxla (Eyni adlı məqalə varsa xəta verməsin, sonuna rəqəm atsın)
        # Məsələn: "python-dersleri" varsa, "python-dersleri-1" olsun.
        original_slug = self.slug
        for x in itertools.count(1):
            if not Post.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                break
            self.slug = '%s-%d' % (original_slug, x)

        super().save(*args, **kwargs)

    @property
    def average_rating(self):
        # Comments modelin varsa bu işləyəcək
        agg = self.comments.aggregate(models.Avg("rating"))
        return agg["rating__avg"] or 0
    
    @property
    def get_image(self):
        """
        Bu metod yoxlayır:
        1. Fayl yüklənib? -> Faylın yolunu qaytar.
        2. URL var? -> URL-i qaytar.
        3. Heç biri yoxdur? -> Default şəkli qaytar.
        """
        if self.image:
            return self.image.url
        elif self.image_url:
            return self.image_url
        else:
            return static('img/default-post.jpg') # Default şəklin yeri

# ---- Models for Comment functionality ----

class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    text = models.TextField()
    rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(i, f"{i} ulduz") for i in range(1, 6)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # Diqqət: burada artıq unique_together və ya constraint YOXDUR,
        # yəni eyni user eyni post üçün bir neçə şərh yaza bilər.

    def __str__(self):
        return f"{self.user.username} → {self.post.title} ({self.rating})"

# ---- Models for Subscription functionality ----

class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    conf_token = models.CharField(max_length=64, blank=True, null=True) # Təsdiq linki üçün token
    is_active = models.BooleanField(default=False) # Təsdiq olunmayıbsa passivdir
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


# ---- Models for Question functionality ----

class Question(models.Model):
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Müəllif"
    )
    question_text = models.TextField("Sual")
    answer_text = models.TextField("Cavab", blank=True, null=True)

    # Hamı görə bilsin?
    visible_to_all = models.BooleanField(
        "Hamı görə bilər",
        default=False
    )

    # Yalnız seçilmiş user-lər görə bilsin deyirsə:
    visible_users = models.ManyToManyField(
        User,
        related_name="questions_can_see",
        blank=True,
        verbose_name="Görə bilən istifadəçilər"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sual"
        verbose_name_plural = "Suallar"

    def __str__(self):
        return self.question_text[:50]

    def can_user_see(self, user):
        """
        Bu funksiya ilə şablonda və view-lərdə yoxlaya bilərik:
        bu user bu sualı görməlidirmi, yoxsa yox.
        """
        if self.visible_to_all:
            return True
        if not user.is_authenticated:
            return False
        if user == self.author:
            return True
        return self.visible_users.filter(id=user.id).exists()
    

# ---- Models for Exam functionality ----

class Exam(models.Model):
    EXAM_TYPE_CHOICES = (
        ("test", "Test imtahanı"),
        ("written", "Yazılı / praktiki"),
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exams",
        verbose_name="Müəllif"
    )
    title = models.CharField("Blok adı", max_length=200)
    description = models.TextField("Qısa izah", blank=True)

    exam_type = models.CharField(
        "İmtahan tipi",
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default="test",
    )

    # Exam aktivdir?
    is_active = models.BooleanField(
        "Aktivdir?",
        default=False,
        help_text="Əgər söndürsəniz, tələbələr bu imtahanı görə bilməyəcək."
    )

    # Ümumi imtahan vaxtı (dəqiqə) – OPTIONAL
    total_duration_minutes = models.PositiveIntegerField(
        "Ümumi imtahan müddəti (dəqiqə)",
        blank=True,
        null=True,
        help_text="Məs: 30. Boş saxlasanız, ümumi vaxt limiti olmayacaq."
    )

    # Hər sual üçün default vaxt (saniyə) – OPTIONAL
    default_question_time_seconds = models.PositiveIntegerField(
        "Hər sual üçün default vaxt (saniyə)",
        blank=True,
        null=True,
        help_text="Məs: 60. Boş saxlasanız, sual basisində vaxt limiti olmayacaq."
    )

    # Bir user üçün maksimum cəhd sayı – OPTIONAL
    max_attempts_per_user = models.PositiveIntegerField(
        "Bir istifadəçi üçün maksimum cəhd sayı",
        blank=True,
        null=True,
        help_text="Məs: 1, 2, 3... Boş saxlasanız, attempts limitsiz olacaq."
    )

    slug = models.SlugField(max_length=220, unique=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "İmtahan bloku"
        verbose_name_plural = "İmtahan blokları"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_exam_type_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            self.slug = f"{base_slug}-{get_random_string(6)}"
        super().save(*args, **kwargs)

    # ---- İstifadəçi üçün attempt limiti ilə bağlı köməkçi metodlar ----

    def attempts_left_for(self, user) -> int | None:
        """
        Bu user üçün neçə attempt qalıb?
        None → limitsiz deməkdir.
        Draft attempt-lər limitsayımda nəzərə alınmır.
        """
        if not self.max_attempts_per_user:
            return None  # limitsiz

        used = self.attempts.filter(user=user).exclude(
            status="draft"
        ).count()
        left = self.max_attempts_per_user - used
        return max(left, 0)

    def can_user_start(self, user) -> bool:
        """
        View-də istifadə üçün: bu user yeni attempt başlada bilərmi?
        """
        if not self.is_active:
            return False
        if not self.max_attempts_per_user:
            return True
        return self.attempts_left_for(user) > 0


class ExamQuestion(models.Model):
    ANSWER_MODE_CHOICES = (
        ("single", "Tək düzgün cavab"),
        ("multiple", "Birdən çox düzgün cavab"),
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="İmtahan bloku"
    )
    text = models.TextField("Sual mətni")

    # Test üçün "ideal" cavab mətni lazım olsa, yazılı üçün də istifadə etmək olar
    correct_answer = models.TextField(
        "Düzgün cavab / ideal cavab (yazılı üçün)",
        blank=True
    )

    order = models.PositiveIntegerField("Sıra", default=1)

    # Bu sual testdirsə:
    answer_mode = models.CharField(
        "Cavab rejimi",
        max_length=20,
        choices=ANSWER_MODE_CHOICES,
        default="single",
        help_text="Yalnız test imtahanları üçün mənalıdır."
    )

    # Bu sual üçün xüsusi vaxt limiti (saniyə) – OPTIONAL
    time_limit_seconds = models.PositiveIntegerField(
        "Bu sual üçün vaxt limiti (saniyə)",
        blank=True,
        null=True,
        help_text="Boş saxlasanız, Exam.default_question_time_seconds istifadə olunacaq."
    )

    class Meta:
        verbose_name = "İmtahan sualı"
        verbose_name_plural = "İmtahan sualları"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} – {self.order}. sual"

    @property
    def effective_time_limit(self):
        """
        Bu sual üçün real vaxt limiti:
        1) öz time_limit_seconds, əgər doludursa
        2) yoxdursa exam.default_question_time_seconds
        3) heç biri yoxdursa → limitsiz (None)
        """
        if self.time_limit_seconds:
            return self.time_limit_seconds
        if self.exam.default_question_time_seconds:
            return self.exam.default_question_time_seconds
        return None

    # ---- Statistikaya köməkçi propertilər ----

    @property
    def total_answers(self):
        return self.answers.count()

    @property
    def correct_answers_count(self):
        return self.answers.filter(is_correct=True).count()

    @property
    def wrong_answers_count(self):
        return self.answers.filter(is_correct=False).count()

    @property
    def correct_ratio(self):
        """
        Düzgün cavab faizi (0-100).
        """
        total = self.total_answers
        if not total:
            return 0
        return round(self.correct_answers_count * 100 / total, 1)


class ExamQuestionOption(models.Model):
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Sual"
    )
    text = models.CharField("Variant mətni", max_length=255)
    is_correct = models.BooleanField("Düzgün variantdır?", default=False)

    class Meta:
        verbose_name = "Sual variantı"
        verbose_name_plural = "Sual variantları"

    def __str__(self):
        prefix = "✓" if self.is_correct else "•"
        return f"{prefix} {self.text[:50]}"


class ExamAttempt(models.Model):
    STATUS_CHOICES = (
        ("draft", "Draft (yarımçıq saxlanılıb)"),
        ("in_progress", "Davam edir"),
        ("submitted", "Təslim edilib"),
        ("expired", "Vaxt bitib"),
    )
    
    checked_by_teacher = models.BooleanField(
        "Müəllim tərəfindən yoxlanılıb?",
        default=False
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_attempts"
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    attempt_number = models.PositiveIntegerField(
        "Cəhd nömrəsi",
        default=1,
        help_text="Eyni user üçün 1, 2, 3 və s."
    )

    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress"
    )

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    duration_seconds = models.PositiveIntegerField(
        "Faktiki davametmə müddəti (saniyə)",
        blank=True,
        null=True
    )

    # Test üçün ümumi nəticə:
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    
    teacher_score = models.PositiveIntegerField(
        "Müəllimin verdiyi bal (%)",
        blank=True,
        null=True,
        help_text="0–100 arası bal."
    )

    teacher_feedback = models.TextField(
        "Müəllimin rəyi",
        blank=True,
    )

    class Meta:
        verbose_name = "İmtahan cəhdi"
        verbose_name_plural = "İmtahan cəhdləri"
        ordering = ["-started_at"]
        unique_together = ("user", "exam", "attempt_number")

    def __str__(self):
        return f"{self.user.username} → {self.exam.title} (#{self.attempt_number})"

    @property
    def is_finished(self):
        return self.status in ("submitted", "expired")

    @property
    def score_percent(self):
        total = self.correct_count + self.wrong_count
        if not total:
            return 0
        return round(self.correct_count * 100 / total, 1)

    def mark_finished(self, status="submitted"):
        """
        Attempt-i bitmiş kimi işarələyir, finished_at və duration_seconds hesablayır.
        """
        self.status = status
        # yalnız bir dəfə set etmək istəyirsənsə, bu cür də yaza bilərsən:
        # if not self.finished_at:
        self.finished_at = timezone.now()
        if self.finished_at and self.started_at:
            delta = self.finished_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        self.save(update_fields=["status", "finished_at", "duration_seconds"])
        
    def recalculate_score(self):
        """
        Bu attempt üçün düzgün/səhv cavab sayını yenidən hesablayır.
        """
        qs = self.answers.all()
        self.correct_count = qs.filter(is_correct=True).count()
        self.wrong_count = qs.filter(is_correct=False).count()
        self.save(update_fields=["correct_count", "wrong_count"])
    
    def mark_checked(self):
        self.checked_by_teacher = True
        self.save(update_fields=["checked_by_teacher"])




class ExamAnswer(models.Model):
    """
    Bir attempt daxilində konkret bir suala verilən cavab.
    Test + yazılı üçün birləşmiş model.
    """
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    

    # Test üçün: seçilən variantlar (single/multiple)
    selected_options = models.ManyToManyField(
        ExamQuestionOption,
        blank=True,
        related_name="selected_in_answers",
        verbose_name="Seçilmiş variantlar"
    )

    # Yazılı / praktiki üçün: mətndə cavab
    text_answer = models.TextField(
        "Yazılı cavab",
        blank=True
    )

    # Avtomatik hesablanmış nəticə (testdə istifadə olunacaq)
    is_correct = models.BooleanField(
        "Düzgündür?",
        default=False
    )
    
    
    # --- MÜƏLLİM YOXLAMASI (SUAL SƏVİYYƏSİNDƏ) ---
    teacher_score = models.PositiveIntegerField(
        "Müəllim balı (sual üzrə)",
        blank=True,
        null=True,
        help_text="Bu suala verilən bal. (məs: 0–10 və ya 0–20 və s.)"
    )

    teacher_feedback = models.TextField(
        "Müəllim rəyi (sual üzrə)",
        blank=True,
    )

    # Autosave və draft üçün vacib:
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sual cavabı"
        verbose_name_plural = "Sual cavabları"
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"{self.attempt} → {self.question}"

    def auto_evaluate(self):
        """
        Test imtahanlarında avtomatik yoxlama.
        - single: sadəcə 1 düzgün variant seçilməlidir.
        - multiple: seçilənlər dəqiq olaraq düzgün set-lə eyni olmalıdır.
        Yazılı tipdə bu funksiya istifadə olunmaya bilər.
        """
        exam = self.question.exam
        if exam.exam_type != "test":
            # Yazılı imtahanlarda bu funksiyanı çağırmaya bilərik.
            return

        correct_options = set(
            self.question.options.filter(is_correct=True).values_list("id", flat=True)
        )
        selected = set(
            self.selected_options.values_list("id", flat=True)
        )

        if not correct_options:
            # Düzgün variant təyin olunmayıbsa, heç nə etmirik
            self.is_correct = False
        else:
            # Seçilən variant set-i düzgün set-lə eyni olmalıdır
            self.is_correct = (selected == correct_options)

        self.save()


class ExamAnswerFile(models.Model):
    answer = models.ForeignKey(
        "ExamAnswer",
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Cavab"
    )
    file = models.FileField(
        "Fayl",
        upload_to="exam_uploads/",
        validators=[validate_file_extension, validate_file_size, validate_zip_contents]
    )
    uploaded_at = models.DateTimeField("Yüklənmə tarixi", auto_now_add=True)

    def filename(self):
        return self.file.name.split("/")[-1]

    def __str__(self):
        return f"{self.filename()} ({self.answer_id})"




def _user_is_teacher(self):
    return self.groups.filter(name='teacher').exists()

User.add_to_class('is_teacher', property(_user_is_teacher))