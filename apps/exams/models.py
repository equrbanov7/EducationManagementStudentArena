# exams/models.py
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify
from django.utils.translation import pgettext, pgettext_lazy

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
        raise ValidationError(pgettext("exams.model.error", "video_size_exceeded").format(max_mb=max_mb))


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
        verbose_name=pgettext_lazy("exams.model.student_group.field", "teacher"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="student_groups",
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.student_group.field", "organization"),
    )
    name = models.CharField(
        max_length=50,
        verbose_name=pgettext_lazy("exams.model.student_group.field", "name"),
    )

    students = models.ManyToManyField(
        User,
        related_name="student_groups_as_student",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.student_group.field", "students"),
    )
    teachers = models.ManyToManyField(
        User,
        related_name="student_groups_as_teacher",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.student_group.field", "teachers"),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.student_group.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.student_group.meta", "plural")
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
        ("test", pgettext_lazy("exams.model.exam.choice.exam_type", "test")),
        ("written", pgettext_lazy("exams.model.exam.choice.exam_type", "written")),
    )

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exams",
        verbose_name=pgettext_lazy("exams.model.exam.field", "author"),
    )
    title = models.CharField(
        max_length=200,
        verbose_name=pgettext_lazy("exams.model.exam.field", "title"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "description"),
    )

    exam_type = models.CharField(
        pgettext_lazy("exams.model.exam.field", "exam_type"),
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default="test",
    )

    # ✅ YENİ: Başlama və Bitmə tarixləri
    start_datetime = models.DateTimeField(
        pgettext_lazy("exams.model.exam.field", "start_datetime"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "start_datetime"),
    )

    end_datetime = models.DateTimeField(
        pgettext_lazy("exams.model.exam.field", "end_datetime"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "end_datetime"),
    )

    # Exam aktivdir?
    is_active = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "is_active"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "is_active"),
    )

    # Ümumi imtahan vaxtı (dəqiqə) – OPTIONAL
    total_duration_minutes = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "total_duration_minutes"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "total_duration_minutes"),
    )

    # Hər sual üçün default vaxt (saniyə) – OPTIONAL
    default_question_time_seconds = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "default_question_time_seconds"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "default_question_time_seconds"),
    )

    # Bir user üçün maksimum cəhd sayı – OPTIONAL
    max_attempts_per_user = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "max_attempts_per_user"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "max_attempts_per_user"),
    )

    random_question_count = models.PositiveIntegerField(
        pgettext_lazy("exams.model.exam.field", "random_question_count"),
        default=10,
        help_text=pgettext_lazy("exams.model.exam.help", "random_question_count"),
    )

    default_question_points = models.PositiveIntegerField(default=1)

    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exams",
        verbose_name=pgettext_lazy("exams.model.exam.field", "course"),
    )

    # ══════════════════════════════════════════════════════════════════════════
    # SPRINT 9: YENİ SAHƏLƏR
    # ══════════════════════════════════════════════════════════════════════════

    organization_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "organization_id"),
        help_text=pgettext_lazy("exams.model.exam.help", "organization_id"),
        db_index=True,
    )

    EXAM_TYPE_EXTENDED_CHOICES = (
        ("quiz", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "quiz")),
        ("midterm", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "midterm")),
        ("final", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "final")),
        ("placement", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "placement")),
        ("practice", pgettext_lazy("exams.model.exam.choice.exam_type_extended", "practice")),
    )

    exam_type_extended = models.CharField(
        pgettext_lazy("exams.model.exam.field", "exam_type_extended"),
        max_length=20,
        choices=EXAM_TYPE_EXTENDED_CHOICES,
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.exam.help", "exam_type_extended"),
    )

    MODE_CHOICES = (
        ("online", pgettext_lazy("exams.model.exam.choice.mode", "online")),
        ("offline", pgettext_lazy("exams.model.exam.choice.mode", "offline")),
        ("hybrid", pgettext_lazy("exams.model.exam.choice.mode", "hybrid")),
    )

    mode = models.CharField(
        pgettext_lazy("exams.model.exam.field", "mode"),
        max_length=20,
        choices=MODE_CHOICES,
        default="online",
    )

    PROCTORING_LEVEL_CHOICES = (
        ("none", pgettext_lazy("exams.model.exam.choice.proctoring_level", "none")),
        ("basic", pgettext_lazy("exams.model.exam.choice.proctoring_level", "basic")),
        ("strict", pgettext_lazy("exams.model.exam.choice.proctoring_level", "strict")),
    )

    proctoring_level = models.CharField(
        pgettext_lazy("exams.model.exam.field", "proctoring_level"),
        max_length=20,
        choices=PROCTORING_LEVEL_CHOICES,
        default="none",
    )

    settings = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "settings"),
        help_text=pgettext_lazy("exams.model.exam.help", "settings"),
    )

    # --- Giriş məhdudiyyətləri ---

    is_public = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "is_public"),
        default=True,
        help_text=pgettext_lazy("exams.model.exam.help", "is_public"),
    )

    allowed_users = models.ManyToManyField(
        User,
        related_name="allowed_exams",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "allowed_users"),
        help_text=pgettext_lazy("exams.model.exam.help", "allowed_users"),
    )

    allowed_groups = models.ManyToManyField(
        StudentGroup,
        related_name="exams",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.exam.field", "allowed_groups"),
        help_text=pgettext_lazy("exams.model.exam.help", "allowed_groups"),
    )

    access_code = models.CharField(
        pgettext_lazy("exams.model.exam.field", "access_code"),
        max_length=6,
        blank=True,
        help_text=pgettext_lazy("exams.model.exam.help", "access_code"),
    )

    slug = models.SlugField(max_length=220, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    enable_paint = models.BooleanField(
        pgettext_lazy("exams.model.exam.field", "enable_paint"),
        default=False,
        help_text=pgettext_lazy("exams.model.exam.help", "enable_paint"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.exam.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.exam.meta", "plural")
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
        ("university", pgettext_lazy("exams.model.question_bank.choice.organization_type", "university")),
        ("school", pgettext_lazy("exams.model.question_bank.choice.organization_type", "school")),
        ("course_center", pgettext_lazy("exams.model.question_bank.choice.organization_type", "course_center")),
        ("individual", pgettext_lazy("exams.model.question_bank.choice.organization_type", "individual")),
    )

    name = models.CharField(
        max_length=255,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "name"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "description"),
    )

    subject = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "subject"),
        help_text=pgettext_lazy("exams.model.question_bank.help", "subject"),
    )

    organization_type = models.CharField(
        max_length=50,
        choices=ORGANIZATION_TYPE_CHOICES,
        default="individual",
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "organization_type"),
    )

    is_shared = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "is_shared"),
        help_text=pgettext_lazy("exams.model.question_bank.help", "is_shared"),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "is_active"),
        db_index=True,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="question_banks",
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "created_by"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "created_at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "updated_at"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_bank.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_bank.meta", "plural")
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
        verbose_name=pgettext_lazy("exams.model.question_block.field", "exam"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=pgettext_lazy("exams.model.question_block.field", "name"),
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.question_block.field", "order"),
    )

    # --- YENİ SAHƏ: Blok üçün vaxt limiti (dəqiqə ilə) ---
    time_limit_minutes = models.PositiveIntegerField(
        pgettext_lazy("exams.model.question_block.field", "time_limit_minutes"),
        null=True,
        blank=True,
        help_text=pgettext_lazy("exams.model.question_block.help", "time_limit_minutes"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_block.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_block.meta", "plural")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} - {self.name}"


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamQuestion
# ═══════════════════════════════════════════════════════════════════════════════


class ExamQuestion(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    points = models.PositiveIntegerField(default=1)
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    ANSWER_MODE_CHOICES = (
        ("single", pgettext_lazy("exams.model.question.choice.answer_mode", "single")),
        ("multiple", pgettext_lazy("exams.model.question.choice.answer_mode", "multiple")),
    )

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=pgettext_lazy("exams.model.question.field", "exam"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "is_active"),
    )

    # --- BURANI ƏLAVƏ EDİN (START) ---
    block = models.ForeignKey(
        QuestionBlock,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        verbose_name=pgettext_lazy("exams.model.question.field", "block"),
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
        verbose_name=pgettext_lazy("exams.model.question.field", "bank"),
        help_text=pgettext_lazy("exams.model.question.help", "bank"),
    )

    DIFFICULTY_CHOICES = (
        ("easy", pgettext_lazy("exams.model.question.choice.difficulty", "easy")),
        ("medium", pgettext_lazy("exams.model.question.choice.difficulty", "medium")),
        ("hard", pgettext_lazy("exams.model.question.choice.difficulty", "hard")),
    )

    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="medium",
        verbose_name=pgettext_lazy("exams.model.question.field", "difficulty"),
    )

    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "tags"),
        help_text=pgettext_lazy("exams.model.question.help", "tags"),
    )

    explanation = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "explanation"),
        help_text=pgettext_lazy("exams.model.question.help", "explanation"),
    )

    usage_count = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.question.field", "usage_count"),
        help_text=pgettext_lazy("exams.model.question.help", "usage_count"),
    )

    text = models.TextField(
        verbose_name=pgettext_lazy("exams.model.question.field", "text"),
    )

    # Test üçün "ideal" cavab mətni lazım olsa, yazılı üçün də istifadə etmək olar
    correct_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "correct_answer"),
    )

    order = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.question.field", "order"),
    )

    # Bu sual testdirsə:
    answer_mode = models.CharField(
        pgettext_lazy("exams.model.question.field", "answer_mode"),
        max_length=20,
        choices=ANSWER_MODE_CHOICES,
        default="single",
        help_text=pgettext_lazy("exams.model.question.help", "answer_mode"),
    )

    # Bu sual üçün xüsusi vaxt limiti (saniyə) – OPTIONAL
    time_limit_seconds = models.PositiveIntegerField(
        pgettext_lazy("exams.model.question.field", "time_limit_seconds"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.question.help", "time_limit_seconds"),
    )

    image = models.ImageField(
        upload_to=question_media_path,
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "image"),
    )

    video = models.FileField(
        pgettext_lazy("exams.model.question.field", "video"),
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
        help_text=pgettext_lazy("exams.model.question.help", "enable_paint"),
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "is_active"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "created_at"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question.meta", "plural")
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
        verbose_name=pgettext_lazy("exams.model.question_option.field", "question"),
    )
    text = models.CharField(
        max_length=255,
        verbose_name=pgettext_lazy("exams.model.question_option.field", "text"),
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.question_option.field", "is_correct"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_option.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_option.meta", "plural")

    def __str__(self):
        prefix = "✓" if self.is_correct else "•"
        return f"{prefix} {self.text[:50]}"


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL: ExamAttempt
# ═══════════════════════════════════════════════════════════════════════════════


class ExamAttempt(models.Model):
    STATUS_CHOICES = (
        ("draft", pgettext_lazy("exams.model.attempt.choice.status", "draft")),
        ("in_progress", pgettext_lazy("exams.model.attempt.choice.status", "in_progress")),
        ("submitted", pgettext_lazy("exams.model.attempt.choice.status", "submitted")),
        ("expired", pgettext_lazy("exams.model.attempt.choice.status", "expired")),
    )

    checked_by_teacher = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "checked_by_teacher"),
    )
    teacher_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_checked_at"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")

    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "attempt_number"),
        help_text=pgettext_lazy("exams.model.attempt.help", "attempt_number"),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "status"),
    )

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    duration_seconds = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "duration_seconds"),
    )

    # Test üçün ümumi nəticə:
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)

    teacher_score = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_score"),
        help_text=pgettext_lazy("exams.model.attempt.help", "teacher_score"),
    )

    teacher_feedback = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_feedback"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.attempt.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.attempt.meta", "plural")
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
        if not self.teacher_checked_at:
            self.teacher_checked_at = timezone.now()
            self.save(update_fields=["checked_by_teacher", "teacher_checked_at"])
            return
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
        verbose_name=pgettext_lazy("exams.model.answer.field", "selected_options"),
    )

    # Yazılı / praktiki üçün: mətndə cavab
    text_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "text_answer"),
    )

    # Avtomatik hesablanmış nəticə (testdə istifadə olunacaq)
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.answer.field", "is_correct"),
    )

    # --- MÜƏLLİM YOXLAMASI (SUAL SƏVİYYƏSİNDƏ) ---
    teacher_score = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "teacher_score"),
        help_text=pgettext_lazy("exams.model.answer.help", "teacher_score"),
    )

    teacher_feedback = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "teacher_feedback"),
    )

    # Autosave və draft üçün vacib:
    updated_at = models.DateTimeField(auto_now=True)

    has_paint = models.BooleanField(default=False)  # bu sualda paint aktivdir?
    paint_image = models.ImageField(upload_to="exam_paints/%Y/%m/", null=True, blank=True)
    paint_updated_at = models.DateTimeField(null=True, blank=True)

    # istəsən raw data (debug üçün) saxlaya bilərsən, amma vacib deyil
    paint_data_url = models.TextField(null=True, blank=True)  # optional

    class Meta:
        verbose_name = pgettext_lazy("exams.model.answer.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.answer.meta", "plural")
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
        verbose_name=pgettext_lazy("exams.model.answer_file.field", "answer"),
    )
    file = models.FileField(
        pgettext_lazy("exams.model.answer_file.field", "file"),
        upload_to="exam_uploads/",
        validators=[validate_file_extension, validate_file_size, validate_zip_contents],
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.answer_file.field", "uploaded_at"),
    )

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
        ("tab_switch", pgettext_lazy("exams.model.proctoring.choice.event_type", "tab_switch")),
        ("copy_paste", pgettext_lazy("exams.model.proctoring.choice.event_type", "copy_paste")),
        ("right_click", pgettext_lazy("exams.model.proctoring.choice.event_type", "right_click")),
        (
            "fullscreen_exit",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "fullscreen_exit"),
        ),
        ("focus_loss", pgettext_lazy("exams.model.proctoring.choice.event_type", "focus_loss")),
        (
            "browser_console",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "browser_console"),
        ),
        (
            "screenshot_attempt",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "screenshot_attempt"),
        ),
        (
            "multiple_windows",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "multiple_windows"),
        ),
        (
            "suspicious_activity",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "suspicious_activity"),
        ),
        (
            "network_disconnect",
            pgettext_lazy("exams.model.proctoring.choice.event_type", "network_disconnect"),
        ),
        ("other", pgettext_lazy("exams.model.proctoring.choice.event_type", "other")),
    )

    exam_attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="proctoring_logs",
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "exam_attempt"),
    )

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "event_type"),
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "timestamp"),
    )

    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "details"),
        help_text=pgettext_lazy("exams.model.proctoring.help", "details"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.proctoring.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.proctoring.meta", "plural")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["exam_attempt", "-timestamp"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return f"{self.exam_attempt.user.username} - {self.get_event_type_display()} @ {self.timestamp}"
