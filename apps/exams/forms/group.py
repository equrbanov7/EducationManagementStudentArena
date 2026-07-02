"""
Student group forms (teacher/admin-facing).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.models import StudentGroup
from apps.organizations.services import organization_role_user_queryset, organization_user_queryset, user_has_org_role
from core.roles import ProfileRole

User = get_user_model()


class UserMetadataSelectMultiple(forms.SelectMultiple):
    """Expose lightweight user metadata to custom checklist renderers."""

    group_membership_attrs = (
        "_student_group_memberships_for_form",
        "_teacher_primary_group_memberships_for_form",
        "_teacher_assigned_group_memberships_for_form",
    )

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if str(name).split("-")[-1] != "students":
            return option

        user = getattr(value, "instance", None)
        profile = getattr(user, "profile", None)
        student_group_number = (getattr(profile, "student_group_number", "") or "").strip()
        membership_labels = []

        search_labels = []
        if student_group_number:
            option["attrs"]["data-student-group-number"] = student_group_number
            search_labels.append(student_group_number)

        for group in self._iter_prefetched_group_memberships(user):
            group_name = (getattr(group, "name", "") or "").strip()
            if group_name and group_name not in membership_labels:
                membership_labels.append(group_name)

        search_labels.extend(membership_labels)
        if membership_labels:
            option["attrs"]["data-user-group-labels"] = ", ".join(membership_labels)
        if search_labels:
            option["attrs"]["data-search-text"] = f"{label} {', '.join(search_labels)}"

        return option

    def _iter_prefetched_group_memberships(self, user):
        if user is None:
            return []

        memberships = []
        for attr in self.group_membership_attrs:
            memberships.extend(getattr(user, attr, []) or [])

        return memberships


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
        widget=UserMetadataSelectMultiple(
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
            "students": UserMetadataSelectMultiple(
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
        self.organization = organization
        self.is_superadmin = bool(is_superadmin)
        self.can_multi_assign_teachers = bool(can_multi_assign_teachers)

        users_qs = User.objects.filter(is_active=True).select_related("profile").order_by("username")
        if self.organization is not None:
            users_qs = organization_user_queryset(self.organization, queryset=users_qs)
        elif not self.is_superadmin:
            users_qs = users_qs.none()

        students_qs = organization_role_user_queryset(
            self.organization,
            {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT},
            queryset=users_qs,
        )
        teachers_qs = organization_role_user_queryset(
            self.organization,
            {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
            queryset=users_qs,
        )

        group_memberships_qs = StudentGroup.objects.none()
        if self.organization is not None:
            group_memberships_qs = (
                StudentGroup.objects.filter(organization=self.organization)
                .only("id", "name", "organization_id")
                .order_by("name")
            )

        students_qs = students_qs.prefetch_related(
            Prefetch(
                "student_groups_as_student",
                queryset=group_memberships_qs,
                to_attr="_student_group_memberships_for_form",
            )
        )
        teachers_qs = teachers_qs.prefetch_related(
            Prefetch(
                "student_groups",
                queryset=group_memberships_qs,
                to_attr="_teacher_primary_group_memberships_for_form",
            ),
            Prefetch(
                "student_groups_as_teacher",
                queryset=group_memberships_qs,
                to_attr="_teacher_assigned_group_memberships_for_form",
            ),
        )

        self.fields["students"].queryset = students_qs
        self.fields["primary_teacher"].queryset = teachers_qs
        self.fields["assigned_teachers"].queryset = teachers_qs

        if self.instance and self.instance.pk:
            self.fields["primary_teacher"].initial = self.instance.teacher_id
            initial_assigned = list(self.instance.teachers.values_list("id", flat=True))
            if self.instance.teacher_id not in initial_assigned:
                initial_assigned.append(self.instance.teacher_id)
            self.fields["assigned_teachers"].initial = initial_assigned

        actor_is_teacher = self.actor is not None and user_has_org_role(
            self.actor,
            self.organization,
            {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
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
        return user_has_org_role(
            user,
            self.organization,
            {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
        )

    def clean(self):
        cleaned_data = super().clean()
        students = cleaned_data.get("students")
        primary_teacher = cleaned_data.get("primary_teacher")
        assigned_teachers = cleaned_data.get("assigned_teachers")

        if self.organization is None:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "org_required"))

        if students is not None:
            allowed_student_ids = set(self.fields["students"].queryset.values_list("id", flat=True))
            invalid_students = students.exclude(id__in=allowed_student_ids)
            if invalid_students.exists():
                raise ValidationError(pgettext_lazy("exams.form.group.error", "tenant_students_only"))

        if primary_teacher is None:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_required"))

        if not self._is_teacher_profile(primary_teacher):
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_role_required"))

        if primary_teacher.id not in self.fields["primary_teacher"].queryset.values_list("id", flat=True):
            raise ValidationError(pgettext_lazy("exams.form.group.error", "primary_teacher_tenant_mismatch"))

        assigned_list = list(assigned_teachers) if assigned_teachers is not None else []

        invalid_assigned = []
        allowed_teacher_ids = set(self.fields["assigned_teachers"].queryset.values_list("id", flat=True))
        for teacher in assigned_list:
            if teacher.id not in allowed_teacher_ids or not self._is_teacher_profile(teacher):
                invalid_assigned.append(teacher)
        if invalid_assigned:
            raise ValidationError(pgettext_lazy("exams.form.group.error", "assigned_teachers_invalid"))

        assigned_ids = {teacher.id for teacher in assigned_list}
        assigned_ids.add(primary_teacher.id)

        actor_is_teacher = self.actor is not None and user_has_org_role(
            self.actor,
            self.organization,
            {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER},
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
