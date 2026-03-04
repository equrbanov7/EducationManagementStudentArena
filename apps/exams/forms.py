from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import pgettext, pgettext_lazy

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup
from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "exam_type",
            "is_active",
            "start_datetime",
            "end_datetime",
            "is_public",
            "allowed_users",
            "allowed_groups",
            "access_code",
            "total_duration_minutes",
            "default_question_time_seconds",
            "max_attempts_per_user",
            "enable_paint",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "title_example"),
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "description_short"),
                }
            ),
            "exam_type": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            # ✅ YENİ: DateTime widget-ləri
            "start_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "start_datetime"),
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "end_datetime"),
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "is_public": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
            "allowed_users": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),
            "allowed_groups": forms.SelectMultiple(
                attrs={
                    "class": "form-control",
                }
            ),
            "access_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "access_code"),
                    "maxlength": "6",
                }
            ),
            "total_duration_minutes": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "total_duration_minutes"),
                }
            ),
            "default_question_time_seconds": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "default_question_time_seconds"),
                }
            ),
            "max_attempts_per_user": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy("exams.form.exam.placeholder", "max_attempts_per_user"),
                }
            ),
        }
        labels = {
            "title": pgettext_lazy("exams.form.exam.label", "title"),
            "description": pgettext_lazy("exams.form.exam.label", "description"),
            "exam_type": pgettext_lazy("exams.form.exam.label", "exam_type"),
            "is_active": pgettext_lazy("exams.form.exam.label", "is_active"),
            "start_datetime": pgettext_lazy("exams.form.exam.label", "start_datetime"),
            "end_datetime": pgettext_lazy("exams.form.exam.label", "end_datetime"),
            "is_public": pgettext_lazy("exams.form.exam.label", "is_public"),
            "allowed_users": pgettext_lazy("exams.form.exam.label", "allowed_users"),
            "allowed_groups": pgettext_lazy("exams.form.exam.label", "allowed_groups"),
            "access_code": pgettext_lazy("exams.form.exam.label", "access_code"),
            "total_duration_minutes": pgettext_lazy("exams.form.exam.label", "total_duration_minutes"),
            "default_question_time_seconds": pgettext_lazy("exams.form.exam.label", "default_question_time_seconds"),
            "max_attempts_per_user": pgettext_lazy("exams.form.exam.label", "max_attempts_per_user"),
        }

    def __init__(self, *args, **kwargs):
        """
        Teacher-ə uyğun olaraq seçimləri filtr eləmək üçün
        view-dən ExamForm(user=request.user, ...) şəklində çağırmaq məqsədi ilə.
        """
        user = kwargs.pop("user", None)
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)

        # ✅ YENİ: DateTime field-lərini input_formats ilə düzəlt
        self.fields["start_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]

        # Default querysets
        self.fields["allowed_users"].queryset = User.objects.filter(is_active=True).order_by("username")
        self.fields["allowed_groups"].queryset = StudentGroup.objects.none()

        # Əgər teacher məlumatı gəlirsə, onu nəzərə alaq
        if user is not None:
            user_qs = User.objects.filter(is_active=True).exclude(id=user.id)
            if organization is not None:
                user_qs = user_qs.filter(profile__organization=organization)
                group_qs = StudentGroup.objects.filter(organization=organization)
            else:
                group_qs = StudentGroup.objects.filter(teacher=user)

            self.fields["allowed_users"].queryset = user_qs.distinct().order_by("username")
            self.fields["allowed_groups"].queryset = group_qs.order_by("name")

    def clean_access_code(self):
        code = (self.cleaned_data.get("access_code") or "").strip()
        if not code:
            return ""  # boş buraxmaq olar

        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "access_code_invalid"))

        return code

    def clean(self):
        """
        ✅ YENİ: Tarix validasiyası
        """
        cleaned_data = super().clean()
        start_dt = cleaned_data.get("start_datetime")
        end_dt = cleaned_data.get("end_datetime")
        enable_paint = cleaned_data.get("enable_paint")
        exam_type = cleaned_data.get("exam_type")

        if exam_type == "test" and enable_paint:
            raise ValidationError(pgettext_lazy("exams.form.exam.error", "enable_paint_written_only"))

        # Əgər hər ikisi doldurulubsa, bitmə başlamadan sonra olmalıdır
        if start_dt and end_dt:
            if start_dt >= end_dt:
                raise forms.ValidationError(pgettext_lazy("exams.form.exam.error", "end_after_start"))

        return cleaned_data


class ExamQuestionCreateForm(forms.ModelForm):
    """
    Bu forma 1 sualı + 3-4 variantı eyni formda yaratmaq/edit edə bilmək üçündür.
    """

    # ---- Variant field-ləri ----
    option1_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_1"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option1_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option2_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_2"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option2_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option3_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_3"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option3_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option4_text = forms.CharField(
        label=pgettext_lazy("exams.form.question.label", "option_4"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option4_is_correct = forms.BooleanField(
        label=pgettext_lazy("exams.form.question.label", "option_correct"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = ExamQuestion
        fields = [
            "text",
            "block",
            "answer_mode",
            "time_limit_seconds",
            "correct_answer",
            "image",
            "video",
            "enable_paint",
        ]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "text"),
                }
            ),
            "block": forms.Select(attrs={"class": "form-control"}),
            "answer_mode": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "time_limit_seconds": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": pgettext_lazy(
                        "exams.form.question.placeholder",
                        "time_limit_seconds",
                    ),
                }
            ),
            "correct_answer": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": pgettext_lazy("exams.form.question.placeholder", "correct_answer"),
                }
            ),
            # ✅ DƏYİŞİKLİK: ClearableFileInput ilə clear funksionallığı
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "video": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": "video/mp4,video/webm,video/quicktime",
                }
            ),
        }
        labels = {
            "text": pgettext_lazy("exams.form.question.label", "text"),
            "block": pgettext_lazy("exams.form.question.label", "block"),
            "answer_mode": pgettext_lazy("exams.form.question.label", "answer_mode"),
            "time_limit_seconds": pgettext_lazy("exams.form.question.label", "time_limit_seconds"),
            "correct_answer": pgettext_lazy("exams.form.question.label", "correct_answer"),
            "image": pgettext_lazy("exams.form.question.label", "image"),
            "video": pgettext_lazy("exams.form.question.label", "video"),
        }

    def __init__(self, *args, exam_type=None, subject_blocks=None, **kwargs):
        """
        exam_type (test / written) view-dən ötürülür.
        """
        self.exam_type = exam_type
        super().__init__(*args, **kwargs)

        # Yazılı imtahanlarda enable_paint field-ini silmə
        if self.exam_type != "written":
            self.fields.pop("enable_paint", None)

        # Blokları dropdown-a doldururuq
        if subject_blocks is not None:
            self.fields["block"].queryset = subject_blocks
            self.fields["block"].empty_label = pgettext_lazy("exams.form.question.select", "block_empty")
        else:
            self.fields["block"].queryset = QuestionBlock.objects.none()

        # Yazılı imtahanlarda answer_mode-u məcburi etməyək
        if self.exam_type == "written":
            self.fields["answer_mode"].required = False

        # Edit zamanı mövcud variantları inputlara doldur
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            options = list(instance.options.all().order_by("id"))
            for idx, opt in enumerate(options[:4], start=1):
                self.fields[f"option{idx}_text"].initial = opt.text
                self.fields[f"option{idx}_is_correct"].initial = opt.is_correct

    def clean(self):
        cleaned_data = super().clean()
        answer_mode = cleaned_data.get("answer_mode")
        image = cleaned_data.get("image")
        video = cleaned_data.get("video")

        if image and not getattr(image, "_committed", False):
            validate_uploaded_file(
                image,
                allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
                max_size_mb=10,
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )
            randomize_uploaded_filename(image)

        if video and not getattr(video, "_committed", False):
            validate_uploaded_file(
                video,
                allowed_extensions={".mp4", ".webm", ".mov"},
                max_size_mb=30,
                allowed_mime_types={"video/mp4", "video/webm", "video/quicktime", "application/octet-stream"},
                allowed_mime_prefixes=("video/",),
            )
            randomize_uploaded_filename(video)

        # Yazılı imtahanda options validasiyasını skip edirik
        if self.exam_type == "written":
            return cleaned_data

        # TEST üçün variant validasiyası
        opts = []
        for i in range(1, 5):
            text = cleaned_data.get(f"option{i}_text")
            is_correct = cleaned_data.get(f"option{i}_is_correct")
            if text:
                opts.append((text, is_correct))

        if answer_mode in ("single", "multiple") and not opts:
            raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "options_required"))

        if answer_mode == "single":
            correct_count = sum(1 for (_, is_corr) in opts if is_corr)
            if correct_count == 0:
                raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "single_requires_one_correct"))
            if correct_count > 1:
                raise forms.ValidationError(pgettext_lazy("exams.form.question.error", "single_only_one_correct"))

        return cleaned_data

    def create_options(self, question_instance: ExamQuestion):
        """
        Yeni sual yaradılanda variantları yarat
        """
        for i in range(1, 5):
            text = self.cleaned_data.get(f"option{i}_text")
            is_correct = self.cleaned_data.get(f"option{i}_is_correct")
            if text:
                ExamQuestionOption.objects.create(
                    question=question_instance,
                    text=text,
                    is_correct=bool(is_correct),
                )

    def save_options(self, question_instance: ExamQuestion):
        """
        Edit zamanı köhnə variantları sil və yenilərini yarat
        """
        question_instance.options.all().delete()
        self.create_options(question_instance)


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
