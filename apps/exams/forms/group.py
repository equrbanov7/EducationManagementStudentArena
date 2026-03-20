"""
Student group forms (teacher/admin-facing).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import pgettext, pgettext_lazy

from apps.accounts.models import ProfileRole
from apps.exams.models import StudentGroup

User = get_user_model()


class StudentGroupForm(forms.ModelForm):
    MAX_MULTI_TEACHERS = 3

    primary_teacher = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        label=pgettext_lazy("exams.form.group.label", "primary_teacher"),
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )
    assigned_teachers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label=pgettext_lazy("exams.form.group.label", "assigned_teachers"),
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select",
            }
        ),
        help_text=pgettext_lazy("exams.form.group.help", "assigned_teachers"),
    )

    class Meta:
        model = StudentGroup
        fields = ["name", "students"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.group.placeholder", "name"),
                }
            ),
            "students": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                }
            ),
        }
        labels = {
            "name": pgettext_lazy("exams.form.group.label", "name"),
            "students": pgettext_lazy("exams.form.group.label", "students"),
        }
        help_texts = {
            "students": pgettext_lazy("exams.form.group.help", "students"),
        }

    def __init__(self, *args, **kwargs):
        actor = kwargs.pop("actor", None)
        teacher = kwargs.pop("teacher", None)  # backward compatibility
        organization = kwargs.pop("organization", None)
        can_multi_assign_teachers = kwargs.pop("can_multi_assign_teachers", False)
        is_superadmin = kwargs.pop("is_superadmin", False)
        super().__init__(*args, **kwargs)

        self.actor = actor or teacher
        if self.actor:
            try:
                actor_profile = self.actor.profile
            except Exception:
                actor_profile = None
        else:
            actor_profile = None
        self.actor_role = getattr(actor_profile, "role", None)
        self.organization = organization
        self.is_superadmin = bool(is_superadmin)
        self.can_multi_assign_teachers = bool(can_multi_assign_teachers)

        users_qs = User.objects.filter(is_active=True).select_related("profile").order_by("username")
        if self.organization is not None:
            users_qs = users_qs.filter(profile__organization=self.organization)
        elif not self.is_superadmin:
            users_qs = users_qs.none()

        students_qs = users_qs.filter(
            Q(profile__role__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT])
            | Q(groups__name__in=[ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT])
        ).distinct()
        teachers_qs = users_qs.filter(
            Q(profile__role__in=[ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER])
            | Q(groups__name__in=[ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER])
        ).distinct()

        self.fields["students"].queryset = students_qs
        self.fields["primary_teacher"].queryset = teachers_qs
        self.fields["assigned_teachers"].queryset = teachers_qs

        if self.instance and self.instance.pk:
            self.fields["primary_teacher"].initial = self.instance.teacher_id
            initial_assigned = list(self.instance.teachers.values_list("id", flat=True))
            if self.instance.teacher_id not in initial_assigned:
                initial_assigned.append(self.instance.teacher_id)
            self.fields["assigned_teachers"].initial = initial_assigned

        actor_is_teacher = self.actor is not None and (
            (
                hasattr(self.actor, "has_role")
                and (self.actor.has_role(ProfileRole.TEACHER) or self.actor.has_role(ProfileRole.ASSISTANT_TEACHER))
            )
            or self.actor_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
        )
        if self.actor is not None and actor_is_teacher and not self.can_multi_assign_teachers:
            self.fields["primary_teacher"].queryset = teachers_qs.filter(id=self.actor.id)
            self.fields["assigned_teachers"].queryset = teachers_qs.filter(id=self.actor.id)
            self.fields["primary_teacher"].initial = self.actor.id
            self.fields["assigned_teachers"].initial = [self.actor.id]
            self.fields["assigned_teachers"].help_text = pgettext_lazy(
                "exams.form.group.help",
                "teacher_self_only",
            )
        elif self.actor is not None and not self.can_multi_assign_teachers:
            self.fields["assigned_teachers"].help_text = pgettext_lazy(
                "exams.form.group.help",
                "role_single_teacher",
            )

        self.fields["students"].label_from_instance = self._user_option_label
        self.fields["primary_teacher"].label_from_instance = self._user_option_label
        self.fields["assigned_teachers"].label_from_instance = self._user_option_label

    def _user_option_label(self, user):
        full_name = (user.get_full_name() or "").strip()
        if full_name:
            return f"{user.username} - {full_name}"
        return user.username

    def _is_teacher_profile(self, user):
        if user is None:
            return False
        if hasattr(user, "has_role"):
            return user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER)
        try:
            profile = user.profile
        except Exception:
            profile = None
        return getattr(profile, "role", None) in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}

    def clean(self):
        cleaned_data = super().clean()
        students = cleaned_data.get("students")
        primary_teacher = cleaned_data.get("primary_teacher")
        assigned_teachers = cleaned_data.get("assigned_teachers")

        if self.organization is None:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "org_required"))

        if students is not None:
            invalid_students = students.exclude(profile__organization=self.organization)
            if invalid_students.exists():
                raise ValidationError(pgettext_lazy("exams.form.group.error", "tenant_students_only"))

        if primary_teacher is None:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_required"))

        if not self._is_teacher_profile(primary_teacher):
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_role_required"))

        try:
            primary_teacher_profile = primary_teacher.profile
        except Exception:
            primary_teacher_profile = None

        primary_teacher_org = getattr(primary_teacher_profile, "organization", None)
        if primary_teacher_org != self.organization:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_tenant_mismatch"))

        assigned_list = list(assigned_teachers) if assigned_teachers is not None else []

        invalid_assigned = []
        for teacher in assigned_list:
            try:
                teacher_profile = teacher.profile
            except Exception:
                teacher_profile = None
            teacher_org = getattr(teacher_profile, "organization", None)

            if not self._is_teacher_profile(teacher) or teacher_org != self.organization:
                invalid_assigned.append(teacher)
        if invalid_assigned:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "assigned_teachers_invalid"))

        assigned_ids = {teacher.id for teacher in assigned_list}
        assigned_ids.add(primary_teacher.id)

        actor_is_teacher = self.actor is not None and (
            (
                hasattr(self.actor, "has_role")
                and (self.actor.has_role(ProfileRole.TEACHER) or self.actor.has_role(ProfileRole.ASSISTANT_TEACHER))
            )
            or self.actor_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
        )

        if self.can_multi_assign_teachers:
            if len(assigned_ids) > self.MAX_MULTI_TEACHERS:
                raise ValidationError(
                    pgettext("exams.form.group.error", "max_multi_teachers").format(count=self.MAX_MULTI_TEACHERS)
                )
        elif actor_is_teacher and self.actor is not None:
            if primary_teacher.id != self.actor.id:
                raise ValidationError(pgettext_lazy("exams.form.group.error", "teacher_primary_self_only"))

            non_actor_ids = {teacher_id for teacher_id in assigned_ids if teacher_id != self.actor.id}
            if non_actor_ids:
                raise ValidationError(pgettext_lazy("exams.form.group.error", "teacher_assign_forbidden"))

            assigned_ids = {self.actor.id}
        else:
            # Teacher olmayan, amma multi icazəsi də olmayan rollar yalnız 1 müəllim seçə bilər.
            assigned_ids = {primary_teacher.id}

        self._validated_assigned_teacher_ids = assigned_ids
        return cleaned_data

    def _post_clean(self):
        # Ensure model-level validation receives tenant + primary teacher before full_clean().
        if self.organization is not None:
            self.instance.organization = self.organization

        primary_teacher = self.cleaned_data.get("primary_teacher")
        if primary_teacher is not None:
            self.instance.teacher = primary_teacher

        super()._post_clean()

    def save(self, commit=True):
        group = super().save(commit=False)
        group.organization = self.organization
        group.teacher = self.cleaned_data["primary_teacher"]

        if not commit:
            return group

        group.save()
        self.save_m2m()

        assigned_teacher_ids = getattr(self, "_validated_assigned_teacher_ids", {group.teacher_id})
        teachers_qs = User.objects.filter(id__in=assigned_teacher_ids)
        group.teachers.set(teachers_qs)

        return group
