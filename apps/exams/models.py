# exams/models.py
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.exams.validators import validate_file_extension, validate_file_size, validate_zip_contents

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def question_media_path(instance, filename):
    return f"question_media/exam_{instance.exam_id}/q_{instance.id or 'new'}/{filename}"


def validate_video_size(f):
    # 30MB limit nümunə (istəsən dəyiş)
    max_mb = 30
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(
            pgettext("exams.model.error", "video_size_exceeded").format(max_mb=max_mb)
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: StudentGroup
# ═══════════════════════════════════════════════════════════════════════════════


class StudentGroup(models.Model):
    """
    Müəllimin yaratdığı tələbə qrupu.
    Məs: 875i, 842A1 və s.
    """

    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="student_groups",
        verbose_name="Müəllim",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="student_groups",
        null=True,
        blank=True,
        verbose_name="Təşkilat",
    )
    name = models.CharField("Qrup adı / nömrəsi", max_length=50)

    students = models.ManyToManyField(
        User,
        related_name="student_groups_as_student",
        blank=True,
        verbose_name="Tələbələr",
    )
    teachers = models.ManyToManyField(
        User,
        related_name="student_groups_as_teacher",
        blank=True,
        verbose_name="Təyin olunmuş müəllimlər",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tələbə qrupu"
        verbose_name_plural = "Tələbə qrupları"
        unique_together = (
            "organization",
            "teacher",
            "name",
        )  # eyni müəllimdə eyni adda iki qrup olmasın
        ordering = ["name"]

    def __str__(self):
        if self.organization:
            return f"{self.name} ({self.teacher.username} @ {self.organization.name})"
        return f"{self.name} ({self.teacher.username})"

    def clean(self):
        errors = {}

        if self.organization_id is None:
            errors["organization"] = pgettext("exams.model.error", "group_organization_required")

        if self.teacher_id:
            try:
                profile = self.teacher.profile
            except Exception:
                profile = None
            teacher_org = getattr(profile, "organization", None)
            teacher_is_allowed = self.teacher.is_superuser or getattr(self.teacher, "is_superadmin", False)
            if not teacher_is_allowed and hasattr(self.teacher, "has_role"):
                teacher_is_allowed = self.teacher.has_role(ProfileRole.TEACHER) or self.teacher.has_role(
                    ProfileRole.ASSISTANT_TEACHER
                )
            if not teacher_is_allowed:
                teacher_role = getattr(profile, "role", None)
                teacher_is_allowed = teacher_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}

            if not teacher_is_allowed:
                errors["teacher"] = pgettext("exams.model.error", "group_primary_teacher_role_required")

            if self.organization_id and teacher_org != self.organization:
                errors["teacher"] = pgettext("exams.model.error", "group_primary_teacher_tenant_mismatch")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def has_student(self, user: User) -> bool:
        """
        Verilən user bu qrupun üzvüdürmü?
        """
        return self.students.filter(id=user.id).exists()

    def has_teacher(self, user: User) -> bool:
        """
        Verilən user qrupun primary və ya assigned müəllimidir?
        """
        if user is None:
            return False
        return self.teacher_id == user.id or self.teachers.filter(id=user.id).exists()


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: Exam
# ═══════════════════════════════════════════════════════════════════════════════


class Exam(models.Model):

    EXAM_TYPE_CHOICES = (
        ("test", "Test imtahanı"),
        ("written", "Yazılı / praktiki"),
    )

    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exams", verbose_name="Müəllif")
    title = models.CharField("Blok adı", max_length=200)
    description = models.TextField("Qısa izah", blank=True)

    exam_type = models.CharField(
        "İmtahan tipi",
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default="test",
    )

    # ✅ YENİ: Başlama və Bitmə tarixləri
    start_datetime = models.DateTimeField(
        "Başlama tarixi və vaxtı",
        blank=True,
        null=True,
        help_text="İmtahan bu tarixdən əvvəl başlamaq olmaz. Boş saxlasanız, hər zaman başlamaq olar.",
    )

    end_datetime = models.DateTimeField(
        "Bitmə tarixi və vaxtı",
        blank=True,
        null=True,
        help_text="İmtahan bu tarixdən sonra başlamaq olmaz. Boş saxlasanız, son tarix olmaz.",
    )

    # Exam aktivdir?
    is_active = models.BooleanField(
        "Aktivdir?",
        default=False,
        help_text="Əgər söndürsəniz, tələbələr bu imtahanı görə bilməyəcək.",
    )

    # Ümumi imtahan vaxtı (dəqiqə) – OPTIONAL
    total_duration_minutes = models.PositiveIntegerField(
        "Ümumi imtahan müddəti (dəqiqə)",
        blank=True,
        null=True,
        help_text="Məs: 30. Boş saxlasanız, ümumi vaxt limiti olmayacaq.",
    )

    # Hər sual üçün default vaxt (saniyə) – OPTIONAL
    default_question_time_seconds = models.PositiveIntegerField(
        "Hər sual üçün default vaxt (saniyə)",
        blank=True,
        null=True,
        help_text="Məs: 60. Boş saxlasanız, sual basisində vaxt limiti olmayacaq.",
    )

    # Bir user üçün maksimum cəhd sayı – OPTIONAL
    max_attempts_per_user = models.PositiveIntegerField(
        "Bir istifadəçi üçün maksimum cəhd sayı",
        blank=True,
        null=True,
        help_text="Məs: 1, 2, 3... Boş saxlasanız, attempts limitsiz olacaq.",
    )

    random_question_count = models.PositiveIntegerField(
        "Tələbəyə göstəriləcək sual sayı",
        default=10,
        help_text=(
            "Əgər 0 olarsa, bütün suallar düşür. Əgər rəqəm yazılarsa (məs: 7), "
            "bloklardan qarışıq şəkildə cəmi o qədər sual seçilir."
        ),
    )

    default_question_points = models.PositiveIntegerField(default=1)

    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exams",
        verbose_name="Kurs",
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SPRINT 9: YENİ SAHƏLƏR
    # ══════════════════════════════════════════════════════════════════════════

    organization_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Təşkilat ID",
        help_text="Gələcəkdə organizations.Organization FK olacaq",
        db_index=True,
    )

    EXAM_TYPE_EXTENDED_CHOICES = (
        ("quiz", "Kviz"),
        ("midterm", "Midterm İmtahan"),
        ("final", "Final İmtahan"),
        ("placement", "Yerləşdirmə İmtahanı"),
        ("practice", "Məşq İmtahanı"),
    )

    exam_type_extended = models.CharField(
        "İmtahan tipi (genişləndirilmiş)",
        max_length=20,
        choices=EXAM_TYPE_EXTENDED_CHOICES,
        blank=True,
        null=True,
        help_text="Əlavə imtahan tipləri",
    )

    MODE_CHOICES = (
        ("online", "Onlayn"),
        ("offline", "Oflayn"),
        ("hybrid", "Hibrid"),
    )

    mode = models.CharField(
        "İmtahan rejimi",
        max_length=20,
        choices=MODE_CHOICES,
        default="online",
    )

    PROCTORING_LEVEL_CHOICES = (
        ("none", "Nəzarət Yoxdur"),
        ("basic", "Əsas Nəzarət"),
        ("strict", "Sərt Nəzarət"),
    )

    proctoring_level = models.CharField(
        "Nəzarət səviyyəsi",
        max_length=20,
        choices=PROCTORING_LEVEL_CHOICES,
        default="none",
    )

    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Əlavə Parametrlər",
        help_text="JSON formatında əlavə tənzimləmələr",
    )

    # --- Giriş məhdudiyyətləri ---

    is_public = models.BooleanField(
        "Hamı üçün açıqdır?",
        default=True,
        help_text="Aktivdirsə, imtahan tələbə siyahısı məhdudiyyəti olmadan görünə bilər.",
    )

    allowed_users = models.ManyToManyField(
        User,
        related_name="allowed_exams",
        blank=True,
        verbose_name="İcazəli tələbələr (fərdi)",
        help_text="Yalnız bu istifadəçilər imtahanı görə / başlaya bilsin (qrupdan əlavə olaraq).",
    )

    allowed_groups = models.ManyToManyField(
        StudentGroup,
        related_name="exams",
        blank=True,
        verbose_name="İcazəli qruplar",
        help_text="Bu qruplardakı bütün tələbələr imtahana giriş icazəsi alır.",
    )

    access_code = models.CharField(
        "İmtahan kodu (6 rəqəm)",
        max_length=6,
        blank=True,
        help_text="İstəyə görə əlavə təhlükəsizlik üçün 6 rəqəmli kod.",
    )

    slug = models.SlugField(max_length=220, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    enable_paint = models.BooleanField(
        "Paint cavabı aktiv olsun",
        default=False,
        help_text="Aktiv edilsə, tələbə cavabı paint ilə çəkib göndərə bilər.",
    )

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

    # ✅ YENİ: Tarix yoxlaması metodları
    def is_before_start(self) -> bool:
        """İmtahan hələ başlamayıb?"""
        if not self.start_datetime:
            return False

        return timezone.now() < self.start_datetime

    def is_after_end(self) -> bool:
        """İmtahan bitib?"""
        if not self.end_datetime:
            return False

        return timezone.now() > self.end_datetime

    def is_currently_active(self) -> bool:
        """İmtahan indi aktiv vaxt aralığındadır?"""
        return not self.is_before_start() and not self.is_after_end()

    # ---------- ATTEMPT LIMIT MƏNTİQİ ----------

    def attempts_left_for(self, user: User) -> int | None:
        """
        Bu user üçün neçə attempt qalıb?
        None → limitsiz deməkdir.
        """
        if not self.max_attempts_per_user:
            return None

        used = self.attempts.filter(user=user).exclude(status="draft").count()
        left = self.max_attempts_per_user - used
        return max(left, 0)

    # ---------- ACCESS NƏZARƏTİ ----------

    def _user_in_allowed_groups(self, user: User) -> bool:
        """User hər hansı icazəli qrupun üzvüdürmü?"""
        return self.allowed_groups.filter(students=user).exists()

    def _user_in_assigned_course(self, user: User) -> bool:
        """User bu imtahana bağlı kursa tələbə kimi təyin olunubmu?"""
        if not self.course_id:
            return False
        return self.course.memberships.filter(user=user, role="student").exists()

    def can_user_see(self, user: User) -> bool:
        """Student imtahan kartını görməlidirmi?"""
        if user == self.author:
            return True

        if not self.is_active:
            return False

        # Public exams are globally visible in the exams list for all authenticated users.
        if self.is_public:
            return True

        if self.allowed_users.filter(id=user.id).exists():
            return True

        if self._user_in_allowed_groups(user):
            return True

        if self._user_in_assigned_course(user):
            return True

        if self.access_code:
            return True

        return False

    def can_user_start(self, user: User, code: str | None = None) -> tuple[bool, str | None]:
        """
        Student yeni attempt başlaya bilərmi?
        """
        # 1) Aktiv deyil
        if not self.is_active:
            return False, pgettext("exams.model.access", "exam_not_active")

        # ✅ YENİ: Tarix yoxlaması
        if self.is_before_start():

            start_str = self.start_datetime.strftime("%d.%m.%Y %H:%M")
            return False, pgettext("exams.model.access", "exam_not_started").format(start_str=start_str)

        if self.is_after_end():
            return False, pgettext("exams.model.access", "exam_ended")

        # 2) Cəhd limiti
        left = self.attempts_left_for(user)
        if left is not None and left <= 0:
            return False, pgettext("exams.model.access", "attempt_limit_reached")

        # 3) Müəllif
        if user == self.author:
            return True, None

        in_allowed_any = (
            self.allowed_users.filter(id=user.id).exists()
            or self._user_in_allowed_groups(user)
            or self._user_in_assigned_course(user)
        )

        # 4) Kod yoxdursa
        if not self.access_code:
            if self.is_public:
                return True, None
            if in_allowed_any:
                return True, None
            return False, pgettext("exams.model.access", "no_exam_access")

        # 5) Kod varsa: əvvəlcə visibility/assignment icazəsi olmalıdır.
        if not self.is_public and not in_allowed_any:
            return False, pgettext("exams.model.access", "no_exam_access")

        if not code:
            return False, pgettext("exams.model.access", "access_code_required")
        if code != self.access_code:
            return False, pgettext("exams.model.access", "access_code_invalid")

        return True, None

    def requires_code_for(self, user: User) -> bool:
        """Bu user imtahana başlamaq üçün kod yazmalıdırmı?"""
        if user == self.author or getattr(user, "is_teacher", False):
            return False

        if not self.is_active:
            return False

        if not self.access_code:
            return False

        return True


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: QuestionBank (Sprint 9)
# ═══════════════════════════════════════════════════════════════════════════════


class QuestionBank(models.Model):
    """
    Sual Bankı - sualları təşkil etmək üçün.

    Nə üçün:
    - Sualları mövzulara görə qruplaşdırmaq
    - Sualları paylaşmaq və təkrar istifadə etmək
    - Müxtəlif təşkilatlar üçün sual kitabxanaları yaratmaq
    """

    ORGANIZATION_TYPE_CHOICES = (
        ("university", "Universitet"),
        ("school", "Məktəb"),
        ("course_center", "Kurs Mərkəzi"),
        ("individual", "Fərdi"),
    )

    name = models.CharField(max_length=255, verbose_name="Sual Bankı Adı")

    description = models.TextField(blank=True, verbose_name="Təsvir")

    subject = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Fənn/Mövzu",
        help_text="Məs: Riyaziyyat, Fizika, Proqramlaşdırma",
    )

    organization_type = models.CharField(
        max_length=50,
        choices=ORGANIZATION_TYPE_CHOICES,
        default="individual",
        verbose_name="Təşkilat Tipi",
    )

    is_shared = models.BooleanField(
        default=False,
        verbose_name="Paylaşılıb?",
        help_text="Digər istifadəçilər istifadə edə bilər",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Aktivdir?",
        db_index=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="question_banks",
        verbose_name="Yaradan",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma Tarixi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yenilənmə Tarixi")

    class Meta:
        verbose_name = "Sual Bankı"
        verbose_name_plural = "Sual Bankları"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["is_active", "is_shared"]),
        ]

    def __str__(self):
        return self.name

    @property
    def question_count(self):
        """Bu bankda neçə sual var?"""
        return self.bank_questions.count()


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: QuestionBlock
# ═══════════════════════════════════════════════════════════════════════════════


class QuestionBlock(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="question_blocks",
        verbose_name="İmtahan",
    )
    name = models.CharField("Blok adı", max_length=100)
    order = models.PositiveIntegerField("Sıra", default=1)

    # --- YENİ SAHƏ: Blok üçün vaxt limiti (dəqiqə ilə) ---
    time_limit_minutes = models.PositiveIntegerField(
        "Blok vaxtı (dəqiqə)",
        null=True,
        blank=True,
        help_text="Bu blokdakı sualları həll etmək üçün ayrılan vaxt. Boş olsa, limit yoxdur.",
    )

    class Meta:
        verbose_name = "Sual Bloku"
        verbose_name_plural = "Sual Blokları"
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} - {self.name}"


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamQuestion
# ═══════════════════════════════════════════════════════════════════════════════


class ExamQuestion(models.Model):
    points = models.PositiveIntegerField(default=1)
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    ANSWER_MODE_CHOICES = (
        ("single", "Tək düzgün cavab"),
        ("multiple", "Birdən çox düzgün cavab"),
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="İmtahan bloku",
    )

    # --- BURANI ƏLAVƏ EDİN (START) ---
    block = models.ForeignKey(
        QuestionBlock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        verbose_name="Sual Bloku",
    )
    # --- BURANI ƏLAVƏ EDİN (END) ---

    # ══════════════════════════════════════════════════════════════════════════
    # SPRINT 9: YENİ SAHƏLƏR
    # ══════════════════════════════════════════════════════════════════════════

    bank = models.ForeignKey(
        QuestionBank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_questions",
        verbose_name="Sual Bankı",
        help_text="Bu sual hansı sual bankından götürülüb",
    )

    DIFFICULTY_CHOICES = (
        ("easy", "Asan"),
        ("medium", "Orta"),
        ("hard", "Çətin"),
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="medium",
        verbose_name="Çətinlik Səviyyəsi",
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Etiketlər",
        help_text="JSON siyahısı: ['algebra', 'equations', ...]",
    )

    explanation = models.TextField(
        blank=True,
        verbose_name="İzahat",
        help_text="Sualın həlli və ya izahatı",
    )

    usage_count = models.PositiveIntegerField(
        default=0,
        verbose_name="İstifadə Sayı",
        help_text="Bu sual neçə dəfə istifadə olunub",
    )

    text = models.TextField("Sual mətni")

    # Test üçün "ideal" cavab mətni lazım olsa, yazılı üçün də istifadə etmək olar
    correct_answer = models.TextField("Düzgün cavab / ideal cavab (yazılı üçün)", blank=True)

    order = models.PositiveIntegerField("Sıra", default=1)

    # Bu sual testdirsə:
    answer_mode = models.CharField(
        "Cavab rejimi",
        max_length=20,
        choices=ANSWER_MODE_CHOICES,
        default="single",
        help_text="Yalnız test imtahanları üçün mənalıdır.",
    )

    # Bu sual üçün xüsusi vaxt limiti (saniyə) – OPTIONAL
    time_limit_seconds = models.PositiveIntegerField(
        "Bu sual üçün vaxt limiti (saniyə)",
        blank=True,
        null=True,
        help_text="Boş saxlasanız, Exam.default_question_time_seconds istifadə olunacaq.",
    )

    image = models.ImageField("Sual şəkli (optional)", upload_to=question_media_path, blank=True, null=True)

    video = models.FileField(
        "Sual videosu (optional)",
        upload_to=question_media_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov"]),
            validate_video_size,
        ],
    )

    enable_paint = models.BooleanField(
        default=False,
        help_text="Yalnız yazılı imtahanda tələbə cavab üçün çəkim (paint) edə bilsin.",
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


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamQuestionOption
# ═══════════════════════════════════════════════════════════════════════════════


class ExamQuestionOption(models.Model):
    LABEL_CHOICES = (
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
        ("E", "E"),
    )
    label = models.CharField(max_length=1, choices=LABEL_CHOICES, null=True, blank=True)
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Sual",
    )
    text = models.CharField("Variant mətni", max_length=255)
    is_correct = models.BooleanField("Düzgün variantdır?", default=False)

    class Meta:
        verbose_name = "Sual variantı"
        verbose_name_plural = "Sual variantları"

    def __str__(self):
        prefix = "✓" if self.is_correct else "•"
        return f"{prefix} {self.text[:50]}"


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamAttempt
# ═══════════════════════════════════════════════════════════════════════════════


class ExamAttempt(models.Model):
    STATUS_CHOICES = (
        ("draft", "Draft (yarımçıq saxlanılıb)"),
        ("in_progress", "Davam edir"),
        ("submitted", "Təslim edilib"),
        ("expired", "Vaxt bitib"),
    )

    checked_by_teacher = models.BooleanField("Müəllim tərəfindən yoxlanılıb?", default=False)
    teacher_checked_at = models.DateTimeField("Yoxlanma tarixi", null=True, blank=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")

    attempt_number = models.PositiveIntegerField("Cəhd nömrəsi", default=1, help_text="Eyni user üçün 1, 2, 3 və s.")

    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default="in_progress")

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    duration_seconds = models.PositiveIntegerField("Faktiki davametmə müddəti (saniyə)", blank=True, null=True)

    # Test üçün ümumi nəticə:
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)

    teacher_score = models.PositiveIntegerField(
        "Müəllimin verdiyi bal (%)", blank=True, null=True, help_text="0–100 arası bal."
    )

    teacher_feedback = models.TextField(
        "Müəllimin rəyi",
        blank=True,
    )

    class Meta:
        verbose_name = "İmtahan cəhdi"
        verbose_name_plural = "İmtahan cəhdləri"
        ordering = ["-started_at"]
        # ✅ DƏYİŞİKLİK: unique_together silindi
        # unique_together = ("user", "exam", "attempt_number")  # SİLİNDİ

        # ✅ ƏLAVƏ: Performans üçün index-lər
        indexes = [
            models.Index(fields=["user", "exam", "status"]),
            models.Index(fields=["user", "exam", "-started_at"]),
        ]

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


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamAnswer
# ═══════════════════════════════════════════════════════════════════════════════


class ExamAnswer(models.Model):
    """
    Bir attempt daxilində konkret bir suala verilən cavab.
    Test + yazılı üçün birləşmiş model.
    """

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name="answers")

    # Test üçün: seçilən variantlar (single/multiple)
    selected_options = models.ManyToManyField(
        ExamQuestionOption,
        blank=True,
        related_name="selected_in_answers",
        verbose_name="Seçilmiş variantlar",
    )

    # Yazılı / praktiki üçün: mətndə cavab
    text_answer = models.TextField("Yazılı cavab", blank=True)

    # Avtomatik hesablanmış nəticə (testdə istifadə olunacaq)
    is_correct = models.BooleanField("Düzgündür?", default=False)

    # --- MÜƏLLİM YOXLAMASI (SUAL SƏVİYYƏSİNDƏ) ---
    teacher_score = models.PositiveIntegerField(
        "Müəllim balı (sual üzrə)",
        blank=True,
        null=True,
        help_text="Bu suala verilən bal. (məs: 0–10 və ya 0–20 və s.)",
    )

    teacher_feedback = models.TextField(
        "Müəllim rəyi (sual üzrə)",
        blank=True,
    )

    # Autosave və draft üçün vacib:
    updated_at = models.DateTimeField(auto_now=True)

    has_paint = models.BooleanField(default=False)  # bu sualda paint aktivdir?
    paint_image = models.ImageField(upload_to="exam_paints/%Y/%m/", null=True, blank=True)
    paint_updated_at = models.DateTimeField(null=True, blank=True)

    # istəsən raw data (debug üçün) saxlaya bilərsən, amma vacib deyil
    paint_data_url = models.TextField(null=True, blank=True)  # optional

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

        correct_options = set(self.question.options.filter(is_correct=True).values_list("id", flat=True))
        selected = set(self.selected_options.values_list("id", flat=True))

        if not correct_options:
            # Düzgün variant təyin olunmayıbsa, heç nə etmirik
            self.is_correct = False
        else:
            # Seçilən variant set-i düzgün set-lə eyni olmalıdır
            self.is_correct = selected == correct_options

        self.save()


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamAnswerFile
# ═══════════════════════════════════════════════════════════════════════════════


class ExamAnswerFile(models.Model):
    answer = models.ForeignKey(
        "ExamAnswer",
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Cavab",
    )
    file = models.FileField(
        "Fayl",
        upload_to="exam_uploads/",
        validators=[validate_file_extension, validate_file_size, validate_zip_contents],
    )
    uploaded_at = models.DateTimeField("Yüklənmə tarixi", auto_now_add=True)

    def filename(self):
        return self.file.name.split("/")[-1]

    def __str__(self):
        return f"{self.filename()} ({self.answer_id})"


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ProctoringLog (Sprint 9)
# ═══════════════════════════════════════════════════════════════════════════════


class ProctoringLog(models.Model):
    """
    Proktoring hadisələrinin qeyd edilməsi.

    Nə üçün:
    - İmtahan zamanı şübhəli fəaliyyətləri qeyd etmək
    - Tələbənin davranışını izləmək
    - Akademik ədaləti təmin etmək

    Hadisə tipləri:
    - tab_switch: Tələbə başqa tabə keçib
    - copy_paste: Kopyala-yapışdır cəhdi
    - right_click: Sağ klik istifadəsi
    - fullscreen_exit: Tam ekran rejimindən çıxış
    - focus_loss: Fokus itkisi
    - browser_console: Developer console açılıb
    """

    EVENT_TYPE_CHOICES = (
        ("tab_switch", "Tab Dəyişməsi"),
        ("copy_paste", "Kopyala-Yapışdır"),
        ("right_click", "Sağ Klik"),
        ("fullscreen_exit", "Tam Ekrandan Çıxış"),
        ("focus_loss", "Fokus İtkisi"),
        ("browser_console", "Developer Console"),
        ("screenshot_attempt", "Ekran Görüntüsü Cəhdi"),
        ("multiple_windows", "Çoxlu Pəncərə"),
        ("suspicious_activity", "Şübhəli Fəaliyyət"),
        ("network_disconnect", "Şəbəkə Kəsilməsi"),
        ("other", "Digər"),
    )

    exam_attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="proctoring_logs",
        verbose_name="İmtahan Cəhdi",
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name="Hadisə Tipi",
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Vaxt",
    )

    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Təfərrüatlar",
        help_text="JSON: {ip, browser, location, ...}",
    )

    class Meta:
        verbose_name = "Proktoring Qeydi"
        verbose_name_plural = "Proktoring Qeydləri"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["exam_attempt", "-timestamp"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return f"{self.exam_attempt.user.username} - {self.get_event_type_display()} @ {self.timestamp}"
