"""
Forms for accounts app (authentication and user management).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import pgettext_lazy

from apps.organizations.models import Country, Institution, Organization
from core.constants import OrganizationType

from .models import ProfileRole

User = get_user_model()


class RegisterForm(forms.ModelForm):
    """User registration form with multi-step wizard support."""

    password = forms.CharField(
        label=pgettext_lazy("accounts.form.register.label", "password"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": pgettext_lazy("accounts.form.register.placeholder", "password"),
                "class": "form-control",
            }
        ),
    )
    password2 = forms.CharField(
        label=pgettext_lazy("accounts.form.register.label", "password_confirm"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": pgettext_lazy("accounts.form.register.placeholder", "password_confirm"),
                "class": "form-control",
            }
        ),
    )

    country = forms.ChoiceField(
        label=pgettext_lazy("accounts.form.register.label", "country"),
        required=True,
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    organization_type = forms.ChoiceField(
        label=pgettext_lazy("accounts.form.register.label", "registration_type"),
        choices=[
            (
                OrganizationType.INDIVIDUAL,
                pgettext_lazy("accounts.form.register.choice", "org_type_individual"),
            ),
            (
                OrganizationType.SCHOOL,
                pgettext_lazy("accounts.form.register.choice", "org_type_school"),
            ),
            (
                OrganizationType.UNIVERSITY,
                pgettext_lazy("accounts.form.register.choice", "org_type_university"),
            ),
            (
                OrganizationType.COURSE_CENTER,
                pgettext_lazy("accounts.form.register.choice", "org_type_course_center"),
            ),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
        initial=OrganizationType.INDIVIDUAL,
    )

    institution = forms.ModelChoiceField(
        label=pgettext_lazy("accounts.form.register.label", "institution"),
        queryset=Institution.objects.none(),
        required=False,
        empty_label=pgettext_lazy("accounts.form.register.choice", "institution_empty"),
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    join_organization = forms.ModelChoiceField(
        label=pgettext_lazy("accounts.form.register.label", "join_organization"),
        queryset=Organization.objects.none(),
        required=False,
        empty_label=pgettext_lazy("accounts.form.register.choice", "organization_empty"),
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    institution_not_listed_name = forms.CharField(
        label=pgettext_lazy("accounts.form.register.label", "institution_not_listed"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": pgettext_lazy("accounts.form.register.placeholder", "institution_not_listed"),
                "class": "form-control",
            }
        ),
    )

    organization_identifier = forms.CharField(
        label=pgettext_lazy("accounts.form.register.label", "official_identifier"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": pgettext_lazy("accounts.form.register.placeholder", "official_identifier"),
                "class": "form-control",
            }
        ),
    )

    organization_license_identifier = forms.CharField(
        label=pgettext_lazy("accounts.form.register.label", "license_identifier_optional"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": pgettext_lazy("accounts.form.register.placeholder", "license_identifier_optional"),
                "class": "form-control",
            }
        ),
    )

    initial_role = forms.ChoiceField(
        label=pgettext_lazy("accounts.form.register.label", "initial_role"),
        choices=[
            (
                ProfileRole.MEMBER,
                pgettext_lazy("accounts.form.register.choice", "role_member_pending"),
            ),
            (
                ProfileRole.TEACHER,
                pgettext_lazy("accounts.form.register.choice", "role_teacher"),
            ),
            (
                ProfileRole.HR,
                pgettext_lazy("accounts.form.register.choice", "role_hr"),
            ),
            (
                ProfileRole.ORG_ADMIN,
                pgettext_lazy("accounts.form.register.choice", "role_org_admin"),
            ),
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
                    "placeholder": pgettext_lazy("accounts.form.register.placeholder", "username"),
                    "class": "form-control",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": pgettext_lazy("accounts.form.register.placeholder", "email"),
                    "class": "form-control",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "placeholder": pgettext_lazy("accounts.form.register.placeholder", "first_name"),
                    "class": "form-control",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": pgettext_lazy("accounts.form.register.placeholder", "last_name"),
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
        join_organization = cleaned_data.get("join_organization")
        institution_not_listed_name = (cleaned_data.get("institution_not_listed_name") or "").strip()
        organization_identifier = (cleaned_data.get("organization_identifier") or "").strip()
        organization_license_identifier = (cleaned_data.get("organization_license_identifier") or "").strip()
        initial_role = cleaned_data.get("initial_role")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", pgettext_lazy("accounts.form.register.error", "password_mismatch"))

        if not country_code:
            self.add_error("country", pgettext_lazy("accounts.form.register.error", "country_required"))
        elif not Country.objects.filter(code=country_code, is_active=True).exists():
            self.add_error("country", pgettext_lazy("accounts.form.register.error", "country_invalid"))

        if initial_role == ProfileRole.STUDENT and organization_type != OrganizationType.INDIVIDUAL:
            self.add_error(
                "initial_role",
                pgettext_lazy("accounts.form.register.error", "signup_student_role_not_allowed"),
            )

        if organization_type in {OrganizationType.SCHOOL, OrganizationType.UNIVERSITY, OrganizationType.COURSE_CENTER}:
            if not institution and not institution_not_listed_name:
                self.add_error("institution", pgettext_lazy("accounts.form.register.error", "institution_required"))
                self.add_error(
                    "institution_not_listed_name",
                    pgettext_lazy("accounts.form.register.error", "institution_name_required"),
                )
            if institution:
                if institution.country.code != country_code:
                    self.add_error(
                        "institution",
                        pgettext_lazy("accounts.form.register.error", "institution_country_mismatch"),
                    )
                if institution.institution_type != organization_type:
                    self.add_error(
                        "institution",
                        pgettext_lazy("accounts.form.register.error", "institution_type_mismatch"),
                    )
            if organization_type == OrganizationType.UNIVERSITY and not (
                organization_identifier or (institution and institution.code)
            ):
                self.add_error(
                    "organization_identifier",
                    pgettext_lazy("accounts.form.register.error", "university_identifier_required"),
                )
            cleaned_data["join_organization"] = None
        else:
            cleaned_data["institution"] = None
            cleaned_data["institution_not_listed_name"] = ""
            cleaned_data["organization_identifier"] = ""
            cleaned_data["organization_license_identifier"] = ""
            if not join_organization:
                self.add_error(
                    "join_organization",
                    pgettext_lazy("accounts.form.register.error", "individual_organization_required"),
                )
            else:
                # Individual + selected organization should always onboard as student.
                cleaned_data["initial_role"] = ProfileRole.STUDENT

        cleaned_data["country"] = (country_code or "").upper()
        cleaned_data["organization_type"] = organization_type
        cleaned_data["initial_role"] = cleaned_data.get("initial_role", initial_role)
        cleaned_data["institution_not_listed_name"] = institution_not_listed_name
        cleaned_data["organization_identifier"] = cleaned_data.get("organization_identifier", organization_identifier)
        cleaned_data["organization_license_identifier"] = cleaned_data.get(
            "organization_license_identifier", organization_license_identifier
        )

        return cleaned_data

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if username and User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(pgettext_lazy("accounts.form.register.error", "username_taken"))
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(pgettext_lazy("accounts.form.register.error", "email_taken"))
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        countries = Country.objects.filter(is_active=True).order_by("name")
        self.fields["country"].choices = [
            ("", pgettext_lazy("accounts.form.register.choice", "country_select"))
        ] + [(country.code, country.name) for country in countries]

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
        self.fields["join_organization"].queryset = (
            Organization.objects.filter(is_active=True, status="active")
            .exclude(org_type=OrganizationType.INDIVIDUAL)
            .order_by("name")
        )


class CustomLoginForm(AuthenticationForm):
    """Custom login form with styled fields."""

    username = forms.CharField(
        label=pgettext_lazy("accounts.form.login.label", "username_or_email"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": pgettext_lazy("accounts.form.login.placeholder", "username_or_email"),
            }
        ),
    )
    password = forms.CharField(
        label=pgettext_lazy("accounts.form.login.label", "password"),
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": pgettext_lazy("accounts.form.login.placeholder", "password"),
            }
        ),
    )

    def confirm_login_allowed(self, user):
        """
        Extend default active-user check with organization suspension guard.
        """
        if not user.is_active:
            raise forms.ValidationError(
                pgettext_lazy("accounts.form.login.error", "account_inactive"),
                code="inactive",
            )

        if user.is_superuser or getattr(user, "is_superadmin", False):
            return

        profile = getattr(user, "profile", None)
        organization = getattr(profile, "organization", None) if profile else None
        if organization and (organization.status == "suspended" or not organization.is_active):
            raise forms.ValidationError(
                pgettext_lazy("accounts.form.login.error", "organization_suspended"),
                code="org_suspended",
            )
