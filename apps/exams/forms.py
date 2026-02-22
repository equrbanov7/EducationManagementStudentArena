from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption, QuestionBlock, StudentGroup


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
                    "placeholder": "Məs: Şərt operatorları – Test 1",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "İmtahan haqqında qısa izah...",
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
                    "placeholder": "Başlama tarixi və vaxtı",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                    "placeholder": "Bitmə tarixi və vaxtı",
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
                    "placeholder": "Məs: 123456 (6 rəqəm)",
                    "maxlength": "6",
                }
            ),
            "total_duration_minutes": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Məs: 30 (dəqiqə)",
                }
            ),
            "default_question_time_seconds": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Məs: 60 (saniyə)",
                }
            ),
            "max_attempts_per_user": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Məs: 1, 2, 3...",
                }
            ),
        }
        labels = {
            "title": "İmtahan adı",
            "description": "Qısa izah",
            "exam_type": "İmtahan tipi",
            "is_active": "Aktiv olsun?",
            "start_datetime": "Başlama tarixi və vaxtı",  # ✅ YENİ
            "end_datetime": "Bitmə tarixi və vaxtı",  # ✅ YENİ
            "is_public": "Hamı üçün açıqdır?",
            "allowed_users": "Fərdi icazəli istifadəçilər",
            "allowed_groups": "İcazəli qruplar",
            "access_code": "İmtahan kodu (6 rəqəm)",
            "total_duration_minutes": "Ümumi müddət (dəqiqə)",
            "default_question_time_seconds": "Hər sual üçün default vaxt (saniyə)",
            "max_attempts_per_user": "Bir istifadəçi üçün maksimum cəhd sayı",
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
            raise forms.ValidationError("Kod 6 rəqəmli və yalnız rəqəmlərdən ibarət olmalıdır (məs: 123456).")

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
            raise ValidationError("Paint cavabı yalnız Yazılı / praktiki imtahanlarda aktiv edilə bilər.")

        # Əgər hər ikisi doldurulubsa, bitmə başlamadan sonra olmalıdır
        if start_dt and end_dt:
            if start_dt >= end_dt:
                raise forms.ValidationError("Bitmə tarixi başlama tarixindən sonra olmalıdır.")

        return cleaned_data


class ExamQuestionCreateForm(forms.ModelForm):
    """
    Bu forma 1 sualı + 3-4 variantı eyni formda yaratmaq/edit edə bilmək üçündür.
    """

    # ---- Variant field-ləri ----
    option1_text = forms.CharField(
        label="1-ci variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option1_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option2_text = forms.CharField(
        label="2-ci variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option2_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option3_text = forms.CharField(
        label="3-cü variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option3_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    option4_text = forms.CharField(
        label="4-cü variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    option4_is_correct = forms.BooleanField(
        label="Düzgün?",
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
                    "placeholder": "Sual mətni...",
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
                    "placeholder": "Məs: 60 (saniyə). Boş qalsa default istifadə olunur.",
                }
            ),
            "correct_answer": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Yazılı/praktiki üçün ideal cavab (istəyə görə)...",
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
            "text": "Sual",
            "block": "Mövzu Bloku",
            "answer_mode": "Cavab rejimi",
            "time_limit_seconds": "Bu sual üçün vaxt limiti",
            "correct_answer": "Yazılı/praktiki üçün ideal cavab",
            "image": "Sual şəkli (optional)",
            "video": "Sual videosu (optional)",
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
            self.fields["block"].empty_label = "Ümumi (Heç bir bloka aid deyil)"
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
            raise forms.ValidationError("Heç bir variant daxil edilməyib.")

        if answer_mode == "single":
            correct_count = sum(1 for (_, is_corr) in opts if is_corr)
            if correct_count == 0:
                raise forms.ValidationError("Tək cavab rejimində ən azı 1 düzgün variant seçilməlidir.")
            if correct_count > 1:
                raise forms.ValidationError("Tək cavab rejimində yalnız 1 düzgün variant ola bilər.")

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
        label="Primary müəllim",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )
    assigned_teachers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Təyin olunmuş müəllimlər",
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-select",
            }
        ),
        help_text="Bu qrupu idarə edə bilən əlavə müəllimlər.",
    )

    class Meta:
        model = StudentGroup
        fields = ["name", "students"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Məs: 875i, 842A1 və s.",
                }
            ),
            "students": forms.SelectMultiple(
                attrs={
                    "class": "form-select",
                }
            ),
        }
        labels = {
            "name": "Qrup adı / nömrəsi",
            "students": "Qrupdakı tələbələr",
        }
        help_texts = {
            "students": "Yalnız aktiv tenant-a aid tələbələr görünür.",
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

        actor_is_teacher = (
            self.actor is not None
            and (
                (
                    hasattr(self.actor, "has_role")
                    and (
                        self.actor.has_role(ProfileRole.TEACHER)
                        or self.actor.has_role(ProfileRole.ASSISTANT_TEACHER)
                    )
                )
                or self.actor_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
            )
        )
        if self.actor is not None and actor_is_teacher and not self.can_multi_assign_teachers:
            self.fields["primary_teacher"].queryset = teachers_qs.filter(id=self.actor.id)
            self.fields["assigned_teachers"].queryset = teachers_qs.filter(id=self.actor.id)
            self.fields["primary_teacher"].initial = self.actor.id
            self.fields["assigned_teachers"].initial = [self.actor.id]
            self.fields["assigned_teachers"].help_text = "Müəllim rolunda yalnız özünü təyin edə bilərsən."
        elif self.actor is not None and not self.can_multi_assign_teachers:
            self.fields["assigned_teachers"].help_text = "Bu rol üçün yalnız bir müəllim təyin edilə bilər."

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
            raise ValidationError("Aktiv təşkilat olmadan qrup yaratmaq/yeniləmək olmaz.")

        if students is not None:
            invalid_students = students.exclude(profile__organization=self.organization)
            if invalid_students.exists():
                raise ValidationError("Qrupa yalnız eyni tenant-dakı tələbələr əlavə edilə bilər.")

        if primary_teacher is None:
            raise ValidationError("Qrup üçün primary müəllim seçilməlidir.")

        if not self._is_teacher_profile(primary_teacher):
            raise ValidationError("Primary müəllim mütləq teacher rolunda olmalıdır.")

        try:
            primary_teacher_profile = primary_teacher.profile
        except Exception:
            primary_teacher_profile = None

        primary_teacher_org = getattr(primary_teacher_profile, "organization", None)
        if primary_teacher_org != self.organization:
            raise ValidationError("Primary müəllim qrupla eyni tenant-da olmalıdır.")

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
            raise ValidationError("Təyin olunan müəllimlərin hamısı eyni tenant-da teacher olmalıdır.")

        assigned_ids = {teacher.id for teacher in assigned_list}
        assigned_ids.add(primary_teacher.id)

        actor_is_teacher = (
            self.actor is not None
            and (
                (
                    hasattr(self.actor, "has_role")
                    and (
                        self.actor.has_role(ProfileRole.TEACHER)
                        or self.actor.has_role(ProfileRole.ASSISTANT_TEACHER)
                    )
                )
                or self.actor_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
            )
        )

        if self.can_multi_assign_teachers:
            if len(assigned_ids) > self.MAX_MULTI_TEACHERS:
                raise ValidationError(
                    f"Müəllimdən yuxarı rollar bir qrupa maksimum {self.MAX_MULTI_TEACHERS} müəllim təyin edə bilər."
                )
        elif actor_is_teacher and self.actor is not None:
            if primary_teacher.id != self.actor.id:
                raise ValidationError("Müəllim rolunda yalnız özünü primary müəllim kimi təyin edə bilərsən.")

            non_actor_ids = {teacher_id for teacher_id in assigned_ids if teacher_id != self.actor.id}
            if non_actor_ids:
                raise ValidationError("Müəllim rolunda əlavə müəllim təyin etmək qadağandır.")

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
