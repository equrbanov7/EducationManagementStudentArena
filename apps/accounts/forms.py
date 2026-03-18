"""
Forms for accounts app (authentication and user management).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import pgettext_lazy

from apps.accounts.models import EmailOTP
from apps.organizations.models import Country, Institution, Organization
from core.constants import OrganizationType
from core.utils import build_absolute_url, get_auth_otp_expiry_minutes

from .models import ProfileRole
from .services import issue_email_otp, verify_otp_code

User = get_user_model()


STUDENT_JOIN_ORG_TYPE_MAP = {
    "school_student": OrganizationType.SCHOOL,
    "university_student": OrganizationType.UNIVERSITY,
    "course_student": OrganizationType.COURSE_CENTER,
}
ORGANIZATION_CREATOR_TYPES = {
    OrganizationType.SCHOOL,
    OrganizationType.UNIVERSITY,
    OrganizationType.COURSE_CENTER,
}


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
            (
                "school_student",
                pgettext_lazy("accounts.form.register.choice", "org_type_school_student"),
            ),
            (
                "university_student",
                pgettext_lazy("accounts.form.register.choice", "org_type_university_student"),
            ),
            (
                "course_student",
                pgettext_lazy("accounts.form.register.choice", "org_type_course_student"),
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
        error_messages={
            "invalid_choice": "Düzgün seçim edin. Bu seçim mövcud seçimlərdən biri deyil.",
        },
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
        required=False,
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
        country_code = (cleaned_data.get("country") or "").upper()
        selected_registration_type = cleaned_data.get("organization_type")
        join_organization = cleaned_data.get("join_organization")
        institution_not_listed_name = (cleaned_data.get("institution_not_listed_name") or "").strip()
        organization_identifier = (cleaned_data.get("organization_identifier") or "").strip()
        organization_license_identifier = (cleaned_data.get("organization_license_identifier") or "").strip()
        initial_role = cleaned_data.get("initial_role")
        signup_mode = "individual"
        organization_type = selected_registration_type

        if p1 and p2 and p1 != p2:
            self.add_error("password2", pgettext_lazy("accounts.form.register.error", "password_mismatch"))

        if not country_code:
            self.add_error("country", pgettext_lazy("accounts.form.register.error", "country_required"))
        elif not Country.objects.filter(code=country_code, is_active=True).exists():
            self.add_error("country", pgettext_lazy("accounts.form.register.error", "country_invalid"))

        if selected_registration_type in STUDENT_JOIN_ORG_TYPE_MAP:
            signup_mode = "student_join"
            organization_type = STUDENT_JOIN_ORG_TYPE_MAP[selected_registration_type]
        elif selected_registration_type in ORGANIZATION_CREATOR_TYPES:
            signup_mode = "organization_create"
            organization_type = selected_registration_type
        elif selected_registration_type == OrganizationType.INDIVIDUAL:
            signup_mode = "individual"
            organization_type = OrganizationType.INDIVIDUAL

        if signup_mode == "organization_create":
            if not institution_not_listed_name:
                self.add_error(
                    "institution_not_listed_name",
                    pgettext_lazy("accounts.form.register.error", "institution_name_required"),
                )

            if organization_type == OrganizationType.UNIVERSITY and not organization_identifier:
                self.add_error(
                    "organization_identifier",
                    pgettext_lazy("accounts.form.register.error", "university_identifier_required"),
                )

            cleaned_data["institution"] = None
            cleaned_data["join_organization"] = None
            cleaned_data["initial_role"] = ProfileRole.ORG_ADMIN
        elif signup_mode == "student_join":
            if join_organization:
                if not join_organization.is_active or join_organization.status != "active":
                    self.add_error(
                        "join_organization",
                        pgettext_lazy("accounts.form.register.error", "join_organization_inactive"),
                    )
                if join_organization.org_type != organization_type:
                    self.add_error(
                        "join_organization",
                        pgettext_lazy("accounts.form.register.error", "join_organization_type_mismatch"),
                    )
                if not self._organization_matches_country(join_organization, country_code):
                    self.add_error(
                        "join_organization",
                        pgettext_lazy("accounts.form.register.error", "join_organization_country_mismatch"),
                    )

            cleaned_data["institution"] = None
            cleaned_data["institution_not_listed_name"] = ""
            cleaned_data["organization_identifier"] = ""
            cleaned_data["organization_license_identifier"] = ""
            cleaned_data["initial_role"] = ProfileRole.STUDENT
        else:
            cleaned_data["institution"] = None
            cleaned_data["institution_not_listed_name"] = ""
            cleaned_data["organization_identifier"] = ""
            cleaned_data["organization_license_identifier"] = ""
            cleaned_data["join_organization"] = None
            cleaned_data["initial_role"] = ProfileRole.ORG_ADMIN

        cleaned_data["country"] = country_code
        cleaned_data["organization_type"] = organization_type
        cleaned_data["signup_mode"] = signup_mode
        cleaned_data["initial_role"] = cleaned_data.get("initial_role", initial_role)
        cleaned_data["institution_not_listed_name"] = cleaned_data.get(
            "institution_not_listed_name", institution_not_listed_name
        )
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
        self.fields["country"].choices = [("", pgettext_lazy("accounts.form.register.choice", "country_select"))] + [
            (country.code, country.name) for country in countries
        ]

        selected_country = (self.data.get("country") or self.initial.get("country") or "").upper()
        selected_registration_type = self.data.get("organization_type") or self.initial.get("organization_type")
        selected_org_type = STUDENT_JOIN_ORG_TYPE_MAP.get(selected_registration_type, selected_registration_type)

        institutions = Institution.objects.filter(is_active=True)
        if selected_country:
            institutions = institutions.filter(country__code=selected_country)
        if selected_org_type in ORGANIZATION_CREATOR_TYPES:
            institutions = institutions.filter(institution_type=selected_org_type)
        else:
            institutions = institutions.none()

        self.fields["institution"].queryset = institutions.order_by("name")
        join_orgs = Organization.objects.filter(is_active=True, status="active").exclude(
            org_type=OrganizationType.INDIVIDUAL
        )
        if selected_org_type in ORGANIZATION_CREATOR_TYPES:
            join_orgs = join_orgs.filter(org_type=selected_org_type)
        submitted_join_organization = (self.data.get("join_organization") or "").strip()
        if submitted_join_organization:
            join_orgs = (join_orgs | Organization.objects.filter(pk=submitted_join_organization)).distinct()
        self.fields["join_organization"].queryset = join_orgs.order_by("name")

        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["first_name"].widget.attrs["required"] = "required"
        self.fields["last_name"].widget.attrs["required"] = "required"

    @staticmethod
    def _organization_matches_country(organization, country_code):
        if not organization or not country_code:
            return True

        org_country = (organization.country or "").strip()
        if not org_country:
            return True
        if org_country.upper() == country_code:
            return True

        country = Country.objects.filter(code=country_code, is_active=True).first()
        if not country:
            return False
        return org_country.lower() == country.name.lower()


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


class CustomPasswordChangeForm(PasswordChangeForm):
    """Styled password change form for the profile cabinet."""

    old_password = forms.CharField(
        label="Mövcud şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Mövcud şifrə",
                "autocomplete": "current-password",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="Yeni şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrə",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Yeni şifrəni təkrarla",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrəni təkrarla",
                "autocomplete": "new-password",
            }
        ),
    )


class CustomPasswordResetForm(PasswordResetForm):
    """Password reset request form that sends both a link and an OTP code."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "Email ünvanınızı daxil edin",
                "autocomplete": "email",
            }
        ),
    )

    def save(
        self,
        domain_override=None,
        subject_template_name="accounts/password_reset_subject.txt",
        email_template_name="accounts/password_reset_email.txt",
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name="accounts/password_reset_email.html",
        extra_email_context=None,
    ):
        email = self.cleaned_data["email"]
        for user in self.get_users(email):
            code, expires_at = issue_email_otp(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            reset_url = build_absolute_url(
                reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token}),
                request=request,
            )
            context = {
                "email": user.email,
                "user": user,
                "uid": uid,
                "token": token,
                "reset_url": reset_url,
                "otp_code": code,
                "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
                "otp_expires_at": expires_at,
                **(extra_email_context or {}),
            }
            self.send_mail(
                subject_template_name,
                email_template_name,
                context,
                from_email,
                user.email,
                html_email_template_name=html_email_template_name,
            )


class OTPPasswordResetConfirmForm(SetPasswordForm):
    """Set-password form that requires the emailed OTP code as well."""

    otp_code = forms.CharField(
        label="OTP kodu",
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Emailə gələn 6 rəqəmli kod",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
            }
        ),
    )
    new_password1 = forms.CharField(
        label="Yeni şifrə",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrə",
                "autocomplete": "new-password",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="Yeni şifrəni təkrarla",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Yeni şifrəni təkrarla",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_otp_code(self):
        candidate = (self.cleaned_data.get("otp_code") or "").strip()
        success, otp = verify_otp_code(self.user, candidate)
        if not success or otp is None:
            raise forms.ValidationError("OTP kodu yanlışdır və ya vaxtı bitib.")
        self.matched_otp = otp
        return candidate

    def save(self, commit=True):
        user = super().save(commit=commit)
        matched_otp = getattr(self, "matched_otp", None)
        if matched_otp is not None and not matched_otp.is_used:
            matched_otp.is_used = True
            matched_otp.save(update_fields=["is_used"])
        EmailOTP.objects.filter(user=user, is_used=False).exclude(
            pk=getattr(matched_otp, "pk", None)
        ).update(is_used=True)
        return user
