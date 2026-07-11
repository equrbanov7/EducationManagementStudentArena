from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext, pgettext_lazy

from apps.organizations.public import organization_user_queryset, user_has_org_role
from core.roles import ProfileRole

User = get_user_model()


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
    # Bu qrupun tədris etdiyi fənlər (registrar master-data). String-referans →
    # exams→registrar import kənarı yaranmır. Müəllim sual göndərəndə fənn
    # dropdown-u qrupun bu fənlərindən gəlir (bənd 4-5).
    subjects = models.ManyToManyField(
        "registrar.Subject",
        related_name="student_groups",
        blank=True,
        verbose_name=pgettext_lazy("exams.model.student_group.field", "subjects"),
    )
    # Qrupun akademik vahidi (OrgUnit: ixtisas/qrup). Rol-skoplu görünüşün əsası
    # (bənd 3): kafedra öz alt-ağacını, dekan fakültəni görür. String-referans →
    # exams→organizations onsuz da mövcud kənardır, yeni asılılıq yaranmır.
    org_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="student_groups",
        verbose_name=pgettext_lazy("exams.model.student_group.field", "org_unit"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.student_group.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.student_group.meta", "plural")
        unique_together = ("organization", "teacher", "name")
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
            teacher_is_allowed = self.teacher.is_superuser or getattr(self.teacher, "is_superadmin", False)
            if not teacher_is_allowed and self.organization_id:
                teacher_is_allowed = user_has_org_role(
                    self.teacher,
                    self.organization,
                    {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
                )

            if not teacher_is_allowed:
                errors["teacher"] = pgettext("exams.model.error", "group_primary_teacher_role_required")

            if (
                self.organization_id
                and not organization_user_queryset(
                    self.organization,
                    queryset=User.objects.filter(id=self.teacher_id),
                ).exists()
            ):
                errors["teacher"] = pgettext("exams.model.error", "group_primary_teacher_tenant_mismatch")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def has_student(self, user: User) -> bool:
        return self.students.filter(id=user.id).exists()

    def has_teacher(self, user: User) -> bool:
        if user is None:
            return False
        return self.teacher_id == user.id or self.teachers.filter(id=user.id).exists()


class ExamAccessPolicyMixin:
    def _expire_stale_attempts_for(self, user: User) -> bool:
        changed = False
        # Use Python-side expiry logic because the effective deadline depends on
        # each attempt's started_at plus the exam duration, which is easier to
        # keep consistent in one place on the model.
        for attempt in self.attempts.filter(user=user, status__in=["draft", "in_progress"]).order_by("-started_at"):
            if attempt.expire_if_time_limit_reached():
                changed = True
        return changed

    def _user_has_active_attempt(self, user: User) -> bool:
        self._expire_stale_attempts_for(user)
        return self.attempts.filter(user=user, status__in=["draft", "in_progress"]).exists()

    def _user_in_allowed_groups(self, user: User) -> bool:
        return self.allowed_groups.filter(students=user).exists()

    def _user_is_excluded(self, user: User) -> bool:
        return self.excluded_users.filter(id=user.id).exists()

    def _user_in_assigned_course(self, user: User) -> bool:
        if not self.course_id:
            return False
        return self.course.memberships.filter(user=user, role="student").exists()

    def can_user_see(self, user: User) -> bool:
        if user == self.author:
            return True

        # EXAM-P1-02: arxivlənmiş/soft-silinmiş imtahan tələbəyə görünmür.
        if not self.is_active or self.is_archived or getattr(self, "is_deleted", False):
            return False

        # EXAM-P1-03: exclusion siyahısı public imtahanlara da şamildir —
        # açıq imtahan bloklanmış istifadəçini görünürlükdən keçirməməlidir.
        if self._user_is_excluded(user):
            return False

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
        if not self.is_active:
            return False, pgettext("exams.model.access", "exam_not_active")

        # EXAM-P1-02: UI düymələrinin gizlənməsi sərhəd deyil — birbaşa URL ilə
        # arxivlənmiş və ya soft-silinmiş imtahan başladıla bilməz.
        if self.is_archived or getattr(self, "is_deleted", False):
            return False, pgettext("exams.model.access", "exam_not_active")

        if self.is_before_start():
            start_str = self.start_datetime.strftime("%d.%m.%Y %H:%M")
            return False, pgettext("exams.model.access", "exam_not_started").format(start_str=start_str)

        if self.is_after_end():
            return False, pgettext("exams.model.access", "exam_ended")

        # EXAM-P1-03: exclusion public imtahanlara da şamildir və aktiv cəhdin
        # davam etdirilməsindən əvvəl yoxlanır — istisna edilən tələbə davam
        # edə bilməz.
        if user != self.author and self._user_is_excluded(user):
            return False, pgettext("exams.model.access", "no_exam_access")

        if self._user_has_active_attempt(user):
            return True, None

        left = self.attempts_left_for(user)
        if left is not None and left <= 0:
            return False, pgettext("exams.model.access", "attempt_limit_reached")

        if user == self.author:
            return True, None

        in_allowed_any = (
            self.allowed_users.filter(id=user.id).exists()
            or self._user_in_allowed_groups(user)
            or self._user_in_assigned_course(user)
        )

        # Final/midterm imtahanlarında ümumi imtahan kodu yox, hər tələbənin
        # fərdi PIN-i tələb olunur (imtahan yaradılanda avtomatik verilir).
        if getattr(self, "exam_type_extended", None) in {"final", "midterm"}:
            if not self.is_public and not in_allowed_any:
                return False, pgettext("exams.model.access", "no_exam_access")
            if not code:
                return False, pgettext("exams.model.access", "access_code_required")
            from apps.exams.services.student_pins import verify_student_pin

            if not verify_student_pin(self, user, code):
                return False, pgettext("exams.model.access", "access_code_invalid")
            return True, None

        if not self.access_code:
            if self.is_public:
                return True, None
            if in_allowed_any:
                return True, None
            return False, pgettext("exams.model.access", "no_exam_access")

        if not self.is_public and not in_allowed_any:
            return False, pgettext("exams.model.access", "no_exam_access")

        if not code:
            return False, pgettext("exams.model.access", "access_code_required")
        if code != self.access_code:
            return False, pgettext("exams.model.access", "access_code_invalid")

        return True, None

    def requires_code_for(self, user: User) -> bool:
        if user == self.author or getattr(user, "is_teacher", False):
            return False

        if not self.is_active:
            return False

        # Final/midterm imtahanları hər zaman fərdi PIN tələb edir.
        if getattr(self, "exam_type_extended", None) in {"final", "midterm"}:
            return True

        if not self.access_code:
            return False

        return True


__all__ = [
    "ExamAccessPolicyMixin",
    "StudentGroup",
]
