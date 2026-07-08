"""Tələbə-səviyyəli imtahan giriş modelləri.

* ``ExamStudentPin`` — final/midterm imtahanlarında hər tələbənin öz fərdi
  PIN-i. İmtahan yaradılanda avtomatik verilir və tələbə kabinetində DƏRHAL
  görünür (final imtahan mərkəzindəki bilet-PIN sistemindən fərqli olaraq
  vaxt-pəncərəsi yoxdur). PIN saxlanması final_center/pins.py ilə eyni
  primitivlərdən (salted hash + Fernet) istifadə edir.
* ``StudentExamAttemptGrant`` — müəllimin konkret bir tələbəyə verdiyi əlavə
  cəhd(lər). Qlobal ``max_attempts_per_user`` dəyişmir; yalnız bu tələbənin
  cəhd limiti artır.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import pgettext_lazy

User = get_user_model()


class ExamStudentPin(models.Model):
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="student_pins",
        verbose_name=pgettext_lazy("exams.model.student_pin.field", "exam"),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_student_pins",
        verbose_name=pgettext_lazy("exams.model.student_pin.field", "student"),
    )
    # Doğrulama üçün salted hash; icazəli göstərmə üçün Fernet şifrəli nüsxə.
    pin_hash = models.CharField(max_length=255)
    pin_cipher = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.student_pin.meta", "student exam PIN")
        verbose_name_plural = pgettext_lazy("exams.model.student_pin.meta", "student exam PINs")
        constraints = [
            models.UniqueConstraint(fields=["exam", "student"], name="uniq_exam_student_pin"),
        ]
        indexes = [
            models.Index(fields=["exam", "student"], name="exam_student_pin_idx"),
        ]

    def __str__(self):
        return f"PIN {self.student_id} → exam {self.exam_id}"


class StudentExamAttemptGrant(models.Model):
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="attempt_grants",
        verbose_name=pgettext_lazy("exams.model.attempt_grant.field", "exam"),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_attempt_grants",
        verbose_name=pgettext_lazy("exams.model.attempt_grant.field", "student"),
    )
    extra_attempts = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.attempt_grant.field", "extra_attempts"),
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_exam_attempts",
        verbose_name=pgettext_lazy("exams.model.attempt_grant.field", "granted_by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.attempt_grant.meta", "extra attempt grant")
        verbose_name_plural = pgettext_lazy("exams.model.attempt_grant.meta", "extra attempt grants")
        constraints = [
            models.UniqueConstraint(fields=["exam", "student"], name="uniq_exam_student_attempt_grant"),
        ]

    def __str__(self):
        return f"+{self.extra_attempts} attempt(s): {self.student_id} → exam {self.exam_id}"
