from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.exams.constants import EXAM_LANGUAGE_CHOICES
from apps.exams.domain.grade_events import ExamGradeEventManager, _immutable_error
from apps.exams.question_timer_protocol import default_question_timing
from apps.exams.validators import validate_file_extension, validate_file_size, validate_zip_contents

from .grading import AnswerGradingMixin, AttemptGradingMixin

User = get_user_model()


class ExamAttempt(AttemptGradingMixin, models.Model):
    STATUS_CHOICES = (
        ("draft", pgettext_lazy("exams.model.attempt.choice.status", "draft")),
        ("in_progress", pgettext_lazy("exams.model.attempt.choice.status", "in_progress")),
        ("submitted", pgettext_lazy("exams.model.attempt.choice.status", "submitted")),
        ("expired", pgettext_lazy("exams.model.attempt.choice.status", "expired")),
    )

    SUPERVISION_STATUS_CHOICES = (
        ("active", pgettext_lazy("exams.model.attempt.choice.supervision_status", "active")),
        ("warned", pgettext_lazy("exams.model.attempt.choice.supervision_status", "warned")),
        ("locked", pgettext_lazy("exams.model.attempt.choice.supervision_status", "locked")),
        ("removed", pgettext_lazy("exams.model.attempt.choice.supervision_status", "removed")),
        ("resumed", pgettext_lazy("exams.model.attempt.choice.supervision_status", "resumed")),
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
    # Academic attempts outlive teacher-facing exam deletion actions.  Draft
    # exams without attempts may still be physically removed, while any
    # delivered attempt forces archive/soft-delete semantics.
    exam = models.ForeignKey("exams.Exam", on_delete=models.PROTECT, related_name="attempts")
    # Student imtahana başlayarkən seçdiyi dil. Çoxdilli imtahanlarda yalnız bu
    # dilin sualları yüklənir; tək-dilli imtahanlarda boş qala bilər.
    language = models.CharField(
        max_length=10,
        choices=EXAM_LANGUAGE_CHOICES,
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "language"),
    )
    language_variant = models.ForeignKey(
        "exams.ExamLanguageVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "language_variant"),
    )
    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "attempt_number"),
        help_text=pgettext_lazy("exams.model.attempt.help", "attempt_number"),
    )
    # Müəllimin "Sınaq keç" (trial run) cəhdi — nəticələrə/statistikaya sayılmır.
    is_trial = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "is_trial"),
    )
    # Cəhdin fiziki yeri — girişdə qeydli zal kompüterindən (MAC/IP) həll
    # olunur (bax exam_center_gate.resolve_room_computer). Zal monitoru
    # biletsiz (ExamStudentPin) cəhdləri bu sahələrlə göstərir; otaq
    # izolyasiyası (imtahan hansı zalda gedirsə, yalnız oradan giriş) buna
    # əsaslanır. Qeydli kompüter olmayan girişlərdə boş qalır.
    room = models.ForeignKey(
        "exams.ExamRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "room"),
    )
    room_computer = models.ForeignKey(
        "exams.ExamRoomComputer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "room_computer"),
    )
    marked_question_ids = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "marked_question_ids"),
        help_text=pgettext_lazy("exams.model.attempt.help", "marked_question_ids"),
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
    # EXAM (re-audit §5.6/P1-18): ilk manual qiymətləndirən müəllim. Appeal
    # reviewer independence-i dərinləşdirir — öz qiymətinə baxan şəxs müstəqil
    # reviewer ola bilməz. İlk grading POST-unda set olunur, sonra dəyişmir.
    graded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_exam_attempts",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "graded_by"),
    )
    # EXAM-P1-06: autosave optimistic concurrency. Hər uğurlu server yazısında
    # artır; client öz base_revision-unu göndərir. Uyğunsuzluq (başqa tab daha
    # yeni yazıb) → 409, stale overwrite qarşısı alınır.
    autosave_revision = models.PositiveIntegerField(default=0)
    # EXAM-P1-04: server-authoritative per-question timer. Sual İLK dəfə
    # göstəriləndə {question_id: ISO started_at} yazılır; server deadline =
    # started_at + effective_time_limit + grace. Müddəti keçmiş sualın POST
    # sahələri saxlanmır (client timer-i devtools ilə uzatmaq işləmir).
    question_timing = models.JSONField(default=default_question_timing, blank=True)
    supervision_status = models.CharField(
        max_length=20,
        choices=SUPERVISION_STATUS_CHOICES,
        default="active",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_status"),
    )
    supervision_violation_count = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_violation_count"),
    )
    supervision_extra_chances = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_extra_chances"),
    )
    # Set when a teacher/auto-resume puts the attempt back into "resumed".
    supervision_resumed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_resumed_at"),
    )
    # Set the moment the attempt becomes "locked" (violation limit reached).
    # The teacher then has `resume_window_seconds` to resume the student;
    # if they do not, the backend auto-finishes the attempt with whatever the
    # student has answered so far.  Cleared when the teacher resumes.
    supervision_locked_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_locked_at"),
    )
    # True when the *teacher* manually paused the attempt ("Müvəqqəti blokla"),
    # as opposed to an automatic lock triggered by exceeding the violation
    # limit.  A manual lock is the teacher's own decision — it must always be
    # resumable regardless of the exam's recovery_policy, and (unlike an
    # auto-lock) it does NOT start the auto-finish countdown.
    supervision_manual_lock = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_manual_lock"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.attempt.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.attempt.meta", "plural")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "exam", "status"]),
            models.Index(fields=["user", "exam", "-started_at"]),
        ]
        constraints = [
            # DB-level last line of defence against double-start races.
            # The cache-based _exam_start_actor_lock degrades to "no lock"
            # when Redis is unavailable; these constraints guarantee exam
            # data integrity regardless of the cache state.
            models.UniqueConstraint(
                fields=["user", "exam"],
                condition=models.Q(status="in_progress"),
                name="uniq_active_attempt_per_user_exam",
            ),
            models.UniqueConstraint(
                fields=["user", "exam", "attempt_number"],
                name="uniq_attempt_number_per_user_exam",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.exam.title} (#{self.attempt_number})"

    @property
    def is_finished(self):
        return self.status in ("submitted", "expired")

    @property
    def deadline_at(self):
        if not self.started_at:
            return None
        duration_minutes = getattr(self.exam, "total_duration_minutes", None)
        if not duration_minutes:
            return None
        return self.started_at + timedelta(minutes=duration_minutes)

    @property
    def score_percent(self):
        if getattr(self.exam, "exam_type", None) == "test":
            from apps.exams.services.result_calculation import calculate_test_attempt_result

            return float(calculate_test_attempt_result(self).percentage)

        total = self.correct_count + self.wrong_count
        if not total:
            return 0
        return round(self.correct_count * 100 / total, 1)

    def is_time_limit_reached(self, *, at_time=None):
        deadline = self.deadline_at
        if deadline is None:
            return False
        return (at_time or timezone.now()) >= deadline

    @property
    def is_resume_time_expired(self):
        return self.is_time_limit_reached()

    def expire_if_time_limit_reached(self, *, at_time=None):
        if self.is_finished or not self.is_time_limit_reached(at_time=at_time):
            return False
        self.mark_finished(status="expired")
        return True

    @property
    def supervision_resume_deadline(self):
        """
        Deadline by which the teacher must resume a locked attempt.  Counts
        from the moment the attempt was locked (violation limit reached).
        While "locked" the teacher has `resume_window_seconds` to act; if the
        window elapses the backend auto-finishes the attempt with the answers
        the student has so far.  Returns None when no window applies.
        """
        if self.supervision_status != "locked" or not self.supervision_locked_at:
            return None
        # A teacher's manual pause is open-ended: the teacher decides when to
        # resume, so it must never auto-finish the attempt.
        if self.supervision_manual_lock:
            return None
        config = getattr(self.exam, "supervision_config", None)
        if config is None or not config.enabled:
            return None
        window = config.resume_window_seconds or 0
        if window <= 0:
            return None
        return self.supervision_locked_at + timedelta(seconds=window)

    @property
    def is_resume_window_expired(self):
        deadline = self.supervision_resume_deadline
        if deadline is None:
            return False
        return timezone.now() >= deadline

    def expire_if_resume_window_expired(self, *, at_time=None):
        """
        If the attempt was locked and the teacher did not resume it within the
        configured window, auto-finish it (submit) with whatever the student
        has answered so far.  Kept side-effect-light so it can be called lazily
        (on monitor reads / student polling) and from the periodic Celery
        sweep.  Returns True if it was finished here.
        """
        if self.is_finished:
            return False
        deadline = self.supervision_resume_deadline
        if deadline is None:
            return False
        if (at_time or timezone.now()) < deadline:
            return False

        self.supervision_status = "removed"
        # Submit (not "expired") so the student's current answers are kept and
        # graded — the attempt finishes with what they had at lock time.
        self.mark_finished(status="submitted", extra_update_fields=["supervision_status"])

        # Audit trail.  Imported lazily to avoid a circular import at module load.
        from apps.exams.models import SupervisionIncident

        SupervisionIncident.objects.create(
            organization=self.exam.organization,
            exam=self.exam,
            attempt=self,
            student=self.user,
            event_type="resume_window_expired",
            severity="critical",
            metadata={
                "reason": "teacher_did_not_resume_in_time",
                "locked_at": self.supervision_locked_at.isoformat() if self.supervision_locked_at else None,
                "deadline": deadline.isoformat(),
            },
            violation_count_at_time=self.supervision_violation_count,
            teacher_action="auto_locked_window_expired",
        )
        return True

    def mark_finished(self, status="submitted", extra_update_fields=None):
        was_finished = self.is_finished
        self.status = status
        finished_at = timezone.now()
        # Gecikmiş bitirmə (lazy expire, sweep, tələbənin günlər sonra qayıtması)
        # halında real bitmə vaxtı imtahan limitini keçə bilməz — əks halda
        # müddət "30:41:56" kimi absurd görünür. Deadline ilə clamp edirik.
        deadline = self.deadline_at
        if deadline and finished_at > deadline:
            finished_at = deadline
        self.finished_at = finished_at
        if self.finished_at and self.started_at:
            delta = self.finished_at - self.started_at
            self.duration_seconds = max(int(delta.total_seconds()), 0)
        update_fields = ["status", "finished_at", "duration_seconds"]
        if extra_update_fields:
            update_fields.extend(extra_update_fields)
        self.save(update_fields=list(dict.fromkeys(update_fields)))
        if not was_finished:
            from apps.exams.metrics import record_attempt_submitted

            record_attempt_submitted(getattr(self.exam, "exam_type", "unknown"), status)

    def recalculate_score(self):
        if getattr(self.exam, "exam_type", None) == "test":
            from apps.exams.services.result_calculation import sync_test_attempt_counts

            sync_test_attempt_counts(self)
            return

        qs = self.answers.all()
        self.correct_count = qs.filter(is_correct=True).count()
        self.wrong_count = qs.filter(is_correct=False).count()
        self.save(update_fields=["correct_count", "wrong_count"])


class ExamAnswer(AnswerGradingMixin, models.Model):
    """
    Bir attempt daxilində konkret bir suala verilən cavab.
    Test + yazılı üçün birləşmiş model.
    """

    attempt = models.ForeignKey("exams.ExamAttempt", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("exams.ExamQuestion", on_delete=models.CASCADE, related_name="answers")
    selected_options = models.ManyToManyField(
        "exams.ExamQuestionOption",
        blank=True,
        related_name="selected_in_answers",
        verbose_name=pgettext_lazy("exams.model.answer.field", "selected_options"),
    )
    text_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "text_answer"),
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.answer.field", "is_correct"),
    )
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
    updated_at = models.DateTimeField(auto_now=True)
    has_paint = models.BooleanField(default=False)
    paint_image = models.ImageField(upload_to="exam_paints/%Y/%m/", null=True, blank=True)
    paint_updated_at = models.DateTimeField(null=True, blank=True)
    paint_data_url = models.TextField(null=True, blank=True)
    # Immutable sual snapshot-u (EXAM-INTEGRITY-001): sual çatdırılan anda balı,
    # cavab rejimi və variantlarının düzgünlüyü dondurulur. Test tipli
    # qiymətləndirmə (result_calculation) snapshot varsa ondan hesablanır — belə
    # ki, sonradan sualın/variantın redaktəsi keçmiş cəhdlərin balını GERİYƏ
    # DÖNÜK dəyişməsin. Boş olduqda (köhnə cəhdlər) qiymət canlı suala görə
    # hesablanır (tam geriyə-uyğunluq). Format: {"v":1,"points":int,
    # "answer_mode":str,"options":[{"id":int,"is_correct":bool}, ...]}.
    question_snapshot = models.JSONField(default=dict, blank=True)
    # EXAM-P0-03: tələbənin seçdiyi variant ID-ləri cavab yazılan anda burada
    # dondurulur. selected_options M2M-i canlıdır — variant redaktəsi
    # (delete/recreate) through sətirlərini silib keçmiş seçimi itirə bilər.
    # None = köhnə cavab (canlı M2M-ə düşülür); list (boş da ola bilər) =
    # avtoritativ dondurulmuş seçim.
    selected_option_ids_snapshot = models.JSONField(null=True, blank=True, default=None)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.answer.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.answer.meta", "plural")
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"{self.attempt} → {self.question}"


class ExamAnswerFile(models.Model):
    answer = models.ForeignKey(
        "exams.ExamAnswer",
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


class ProctoringLog(models.Model):
    EVENT_TYPE_CHOICES = (
        ("tab_switch", pgettext_lazy("exams.model.proctoring.choice.event_type", "tab_switch")),
        ("copy_paste", pgettext_lazy("exams.model.proctoring.choice.event_type", "copy_paste")),
        ("right_click", pgettext_lazy("exams.model.proctoring.choice.event_type", "right_click")),
        ("fullscreen_exit", pgettext_lazy("exams.model.proctoring.choice.event_type", "fullscreen_exit")),
        ("focus_loss", pgettext_lazy("exams.model.proctoring.choice.event_type", "focus_loss")),
        ("browser_console", pgettext_lazy("exams.model.proctoring.choice.event_type", "browser_console")),
        ("screenshot_attempt", pgettext_lazy("exams.model.proctoring.choice.event_type", "screenshot_attempt")),
        ("multiple_windows", pgettext_lazy("exams.model.proctoring.choice.event_type", "multiple_windows")),
        ("suspicious_activity", pgettext_lazy("exams.model.proctoring.choice.event_type", "suspicious_activity")),
        ("network_disconnect", pgettext_lazy("exams.model.proctoring.choice.event_type", "network_disconnect")),
        ("other", pgettext_lazy("exams.model.proctoring.choice.event_type", "other")),
    )

    exam_attempt = models.ForeignKey(
        "exams.ExamAttempt",
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


class ExamGradeEvent(models.Model):
    """Append-only manual-grading ledger (re-audit §5.6 / grade tamper-evidence).

    Hər manual bal dəyişikliyi (kim, nə vaxt, köhnə→yeni bal, hansı sual)
    burada qeydə alınır. Ledger yalnız INSERT üçündür — tarixçə redaktə
    olunmur (audit üçün). Tenant izolyasiyası ``organizations 0022`` RLS
    policy-si ilə (exam→organization dolayı).
    """

    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="grade_events",
        verbose_name=pgettext_lazy("exams.model.grade_event.field", "attempt"),
    )
    question = models.ForeignKey(
        "exams.ExamQuestion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_events",
        verbose_name=pgettext_lazy("exams.model.grade_event.field", "question"),
    )
    grader = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_grade_events",
        verbose_name=pgettext_lazy("exams.model.grade_event.field", "grader"),
    )
    old_score = models.IntegerField(null=True, blank=True)
    new_score = models.IntegerField(null=True, blank=True)
    max_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ExamGradeEventManager()

    class Meta:
        verbose_name = pgettext_lazy("exams.model.grade_event.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.grade_event.meta", "plural")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["attempt", "-created_at"]),
        ]

    def __str__(self):
        return f"grade {self.attempt_id}/{self.question_id}: {self.old_score}→{self.new_score}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise _immutable_error()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise _immutable_error()


__all__ = [
    "ExamAnswer",
    "ExamAnswerFile",
    "ExamAttempt",
    "ExamGradeEvent",
    "ProctoringLog",
]
