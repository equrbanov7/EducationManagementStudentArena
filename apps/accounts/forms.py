"""
Forms for accounts app (authentication and user management).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from core.constants import OrganizationType

from apps.organizations.models import Country, Institution

from .models import ProfileRole

User = get_user_model()


class RegisterForm(forms.ModelForm):
    """User registration form with multi-step wizard support."""

    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Şifrənizi daxil edin...",
                "class": "form-control",
            }
        ),
    )
    password2 = forms.CharField(
        label="Şifrə təkrar",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Şifrəni təkrar daxil edin...",
                "class": "form-control",
            }
        ),
    )

    country = forms.ChoiceField(
        label="Ölkə",
        required=True,
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    organization_type = forms.ChoiceField(
        label="Qeydiyyat tipi",
        choices=[
            (OrganizationType.INDIVIDUAL, "Individual"),
            (OrganizationType.SCHOOL, "School"),
            (OrganizationType.UNIVERSITY, "University"),
            (OrganizationType.COURSE_CENTER, "Course Center"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        initial=OrganizationType.INDIVIDUAL,
    )

    institution = forms.ModelChoiceField(
        label="Müəssisə",
        queryset=Institution.objects.none(),
        required=False,
        empty_label="Müəssisə seçin",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    institution_not_listed_name = forms.CharField(
        label="Müəssisə adı (Not listed)",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Müəssisə siyahıda yoxdursa adını daxil edin...",
                "class": "form-control",
            }
        ),
    )

    organization_identifier = forms.CharField(
        label="Rəsmi identifikator / kod",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Məs: School No. 132 və ya UNI-2026",
                "class": "form-control",
            }
        ),
    )

    organization_license_identifier = forms.CharField(
        label="Lisenziya / VÖEN (opsional)",
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Opsional lisenziya və ya vergi kodu",
                "class": "form-control",
            }
        ),
    )

    initial_role = forms.ChoiceField(
        label="İlkin rol",
        choices=[
            (ProfileRole.MEMBER, "Member / Pending"),
            (ProfileRole.TEACHER, "Teacher"),
            (ProfileRole.HR, "HR"),
            (ProfileRole.ORG_ADMIN, "Organization Admin"),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        initial=ProfileRole.MEMBER,
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "placeholder": "İstifadəçi adınız...",
                    "class": "form-control",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "Email ünvanınız...",
                    "class": "form-control",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "placeholder": "Adınız...",
                    "class": "form-control",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": "Soyadınız...",
                    "class": "form-control",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password2")
        country_code = cleaned_data.get("country")
        organization_type = cleaned_data.get("organization_type")
        institution = cleaned_data.get("institution")
        institution_not_listed_name = (cleaned_data.get("institution_not_listed_name") or "").strip()
        organization_identifier = (cleaned_data.get("organization_identifier") or "").strip()
        organization_license_identifier = (cleaned_data.get("organization_license_identifier") or "").strip()
        initial_role = cleaned_data.get("initial_role")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Şifrələr uyğun gəlmir.")

        if not country_code:
            self.add_error("country", "Ölkə seçimi tələb olunur.")
        elif not Country.objects.filter(code=country_code, is_active=True).exists():
            self.add_error("country", "Seçilən ölkə etibarlı deyil.")

        if initial_role == ProfileRole.STUDENT:
            self.add_error("initial_role", "Signup zamanı Student rolu seçilə bilməz.")

        if organization_type in {OrganizationType.SCHOOL, OrganizationType.UNIVERSITY, OrganizationType.COURSE_CENTER}:
            if not institution and not institution_not_listed_name:
                self.add_error("institution", "Müəssisə seçin və ya Not listed sahəsini doldurun.")
                self.add_error("institution_not_listed_name", "Müəssisə adı tələb olunur.")
            if institution:
                if institution.country.code != country_code:
                    self.add_error("institution", "Müəssisə seçilən ölkəyə aid deyil.")
                if institution.institution_type != organization_type:
                    self.add_error("institution", "Müəssisə tipi qeydiyyat tipi ilə uyğun deyil.")
            if organization_type in {OrganizationType.SCHOOL, OrganizationType.UNIVERSITY} and not (
                organization_identifier or (institution and institution.code)
            ):
                self.add_error(
                    "organization_identifier",
                    "School/University üçün rəsmi identifikator və ya kod tələb olunur.",
                )
        else:
            cleaned_data["institution"] = None
            cleaned_data["institution_not_listed_name"] = ""

        cleaned_data["country"] = (country_code or "").upper()
        cleaned_data["organization_type"] = organization_type
        cleaned_data["initial_role"] = initial_role
        cleaned_data["institution_not_listed_name"] = institution_not_listed_name
        cleaned_data["organization_identifier"] = organization_identifier
        cleaned_data["organization_license_identifier"] = organization_license_identifier

        return cleaned_data

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu istifadəçi adı artıq istifadə olunur.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu email artıq istifadə olunur.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        countries = Country.objects.filter(is_active=True).order_by("name")
        self.fields["country"].choices = [("", "Ölkə seçin")] + [(country.code, country.name) for country in countries]

        selected_country = (self.data.get("country") or self.initial.get("country") or "").upper()
        selected_org_type = self.data.get("organization_type") or self.initial.get("organization_type")

        institutions = Institution.objects.filter(is_active=True)
        if selected_country:
            institutions = institutions.filter(country__code=selected_country)
        if selected_org_type in {OrganizationType.SCHOOL, OrganizationType.UNIVERSITY, OrganizationType.COURSE_CENTER}:
            institutions = institutions.filter(institution_type=selected_org_type)
        else:
            institutions = institutions.none()

        self.fields["institution"].queryset = institutions.order_by("name")


class CustomLoginForm(AuthenticationForm):
    """Custom login form with styled fields."""

    username = forms.CharField(
        label="İstifadəçi adı və ya email",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "İstifadəçi adı və ya email",
            }
        ),
    )
    password = forms.CharField(
        label="Şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Şifrəniz",
            }
        ),
    )

    def confirm_login_allowed(self, user):
        """
        Extend default active-user check with organization suspension guard.
        """
        if not user.is_active:
            raise forms.ValidationError("Hesab aktiv deyil. Dəstək xidməti ilə əlaqə saxlayın.", code="inactive")

        if user.is_superuser or getattr(user, "is_superadmin", False):
            return

        profile = getattr(user, "profile", None)
        organization = getattr(profile, "organization", None) if profile else None
        if organization and (organization.status == "suspended" or not organization.is_active):
            raise forms.ValidationError(
                "Təşkilatınız dayandırılıb. Giriş bloklanıb, administrator ilə əlaqə saxlayın.",
                code="org_suspended",
            )
