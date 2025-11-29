# blog/forms.py
from django import forms
from django.contrib.auth.models import User

from .models import Post, Comment, Question,Exam, ExamQuestion, ExamQuestionOption,Category


class SubscriptionForm(forms.Form):
    email = forms.EmailField(
        required=True,
        label='',
        widget=forms.EmailInput(attrs={
            "placeholder": "Email ünvanınızı daxil edin...",
            "class": "form-control",
            "id": "emailInput",
        })
    )
    # Gələcəkdə ad/soyad sahələri də əlavə edə bilərsən.


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Şifrənizi daxil edin...",
            "class": "form-control",
        })
    )
    password2 = forms.CharField(
        label="Şifrə təkrar",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Şifrəni təkrar daxil edin...",
            "class": "form-control",
        })
    )

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(attrs={
                "placeholder": "İstifadəçi adınız...",
                "class": "form-control",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "Email ünvanınız...",
                "class": "form-control",
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")

        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Şifrələr uyğun gəlmir")

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError("Bu email artıq istifadə olunur.")
        return email


class PostForm(forms.ModelForm):
    # Modeldə olmayan, amma yeni kateqoriya yaratmaq üçün lazım olan sahə
    new_category = forms.CharField(
        label="Yeni Kateqoriya",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Siyahıda yoxdursa, yenisini bura yazın..."
        })
    )

    class Meta:
        model = Post
        fields = ["title", "category", "excerpt", "content", "image_url","image"] # new_category bura daxil edilmir!
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Məqalə başlığı",
            }),
            "category": forms.Select(attrs={
                "class": "form-control",
            }),
            "excerpt": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Qısa təsvir (excerpt)...",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 8,
                "placeholder": "Məqalə mətni...",
            }),
            "image_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "Şəklin URL-i (məs: https://...)",
            }),
            "image": forms.ClearableFileInput(attrs={
                "class": "form-control",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Kateqoriya seçimini məcburi etmirik (istifadəçi yenisini yaza bilsin deyə)
        self.fields['category'].required = False
        self.fields['category'].empty_label = "--- Kateqoriya Seçin ---"
        #Image və image_url sahələrindən yalnız biri doldurulmalıdır
        self.fields['image'].required = False
        self.fields['image_url'].required = False


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text", "rating"]
        widgets = {
            "text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Fikrini yaz...",
            }),
            "rating": forms.Select(attrs={
                "class": "form-control",
            }),
        }

class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["question_text", "answer_text", "visible_to_all", "visible_users"]
        widgets = {
            "question_text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Sual mətni...",
            }),
            "answer_text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Cavab mətni (istəyə görə)...",
            }),
            "visible_to_all": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "visible_users": forms.SelectMultiple(attrs={
                "class": "form-control",
            }),
        }
        labels = {
            "question_text": "Sual",
            "answer_text": "Cavab",
            "visible_to_all": "Hamı görə bilsin?",
            "visible_users": "Görə bilən istifadəçilər (əgər hamı deyilsə)",
        }


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "exam_type",
            "is_active",
            "total_duration_minutes",
            "default_question_time_seconds",
            "max_attempts_per_user",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Məs: Şərt operatorları – Test 1",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "İmtahan haqqında qısa izah...",
            }),
            "exam_type": forms.Select(attrs={
                "class": "form-control",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
            "total_duration_minutes": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Məs: 30 (dəqiqə)",
            }),
            "default_question_time_seconds": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Məs: 60 (saniyə)",
            }),
            "max_attempts_per_user": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Məs: 1, 2, 3...",
            }),
        }
        labels = {
            "title": "İmtahan adı",
            "description": "Qısa izah",
            "exam_type": "İmtahan tipi",
            "is_active": "Aktiv olsun?",
            "total_duration_minutes": "Ümumi müddət (dəqiqə)",
            "default_question_time_seconds": "Hər sual üçün default vaxt (saniyə)",
            "max_attempts_per_user": "Bir istifadəçi üçün maksimum cəhd sayı",
        }

class ExamQuestionCreateForm(forms.ModelForm):
    """
    Bu forma 1 sualı + 3-4 variantı eyni formda yaratmaq/edə bilmək üçündür (test tipində).
    Yazılı imtahan üçün options hissəsini istifadə etməyəcəyik.
    """

    # ---- Variant field-ləri ----
    option1_text = forms.CharField(
        label="1-ci variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    option1_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    option2_text = forms.CharField(
        label="2-ci variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    option2_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    option3_text = forms.CharField(
        label="3-cü variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    option3_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    option4_text = forms.CharField(
        label="4-cü variant",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"})
    )
    option4_is_correct = forms.BooleanField(
        label="Düzgün?",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    class Meta:
        model = ExamQuestion
        fields = ["text", "answer_mode", "time_limit_seconds", "correct_answer"]
        widgets = {
            "text": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Sual mətni..."
            }),
            "answer_mode": forms.Select(attrs={
                "class": "form-control",
            }),
            "time_limit_seconds": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "Məs: 60 (saniyə). Boş qalsa default istifadə olunur."
            }),
            "correct_answer": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Yazılı/praktiki üçün ideal cavab (istəyə görə)...",
            }),
        }
        labels = {
            "text": "Sual",
            "answer_mode": "Cavab rejimi",
            "time_limit_seconds": "Bu sual üçün vaxt limiti",
            "correct_answer": "Yazılı/praktiki üçün ideal cavab",
        }

    def __init__(self, *args, exam_type=None, **kwargs):
        """
        exam_type (test / written) view-dən ötürülür.
        - written üçün: answer_mode required olmasın.
        - edit zamanı mövcud variantlar inputlara dolsun.
        """
        self.exam_type = exam_type
        super().__init__(*args, **kwargs)

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

    # ---- Validasiya ----
    def clean(self):
        cleaned_data = super().clean()
        answer_mode = cleaned_data.get("answer_mode")

        # Yazılı imtahanda options validasiyasını tam skip edirik
        if self.exam_type == "written":
            # answer_mode boş olsa belə, sonradan view-də single kimi set edəcəyik
            return cleaned_data

        # Burdan aşağısı yalnız TEST üçündür
        opts = []
        for i in range(1, 5):
            text = cleaned_data.get(f"option{i}_text")
            is_correct = cleaned_data.get(f"option{i}_is_correct")
            if text:
                opts.append((text, is_correct))

        # Əgər cavab rejimi single/multiple-dirsə və heç bir variant verilməyibsə:
        if answer_mode in ("single", "multiple") and not opts:
            raise forms.ValidationError("Heç bir variant daxil edilməyib.")

        if answer_mode == "single":
            correct_count = sum(1 for (_, is_corr) in opts if is_corr)
            if correct_count == 0:
                raise forms.ValidationError(
                    "Tək cavab rejimində ən azı 1 düzgün variant seçilməlidir."
                )
            if correct_count > 1:
                raise forms.ValidationError(
                    "Tək cavab rejimində yalnız 1 düzgün variant ola bilər."
                )

        return cleaned_data

    # ---- Yeni sual yaradanda variantları yaratmaq üçün ----
    def create_options(self, question_instance: ExamQuestion):
        """
        Form valid olandan sonra ExamQuestion yarandıqdan sonra
        bu metod çağırılaraq ExamQuestionOption obyektləri yaradılır.
        Boş text olan variantlar ignore olunur.
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

    # ---- Edit zamanı köhnə variantları silib yenidən yaratmaq üçün ----
    def save_options(self, question_instance: ExamQuestion):
        """
        Edit zamanı:
        1. Köhnə variantların hamısını silir,
        2. Formdan gələn yeni dəyərlərə uyğun variantlar yaradır.
        """
        question_instance.options.all().delete()
        self.create_options(question_instance)
