"""accounts auth forms paketi — login."""

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import pgettext_lazy

from core.utils import build_absolute_url, get_auth_otp_expiry_minutes

from ...identity import canonical_identity_queryset, email_is_placeholder, user_access_is_login_blocked
from ...models import EmailOTP
from ...services import issue_email_otp


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
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": pgettext_lazy("accounts.form.login.placeholder", "password"),
                "autocomplete": "current-password",
                "autocapitalize": "none",
                "autocorrect": "off",
                "spellcheck": "false",
            }
        ),
    )

    def confirm_login_allowed(self, user):
        """
        Extend default active-user check with organization suspension guard.
        Pending organizations allow login so users can see their approval status.
        """
        # ``archived`` hesabda ``is_active`` QƏSDƏN True-dur (registrar
        # trigger-ləri üçün) — girişi bağlayan yeganə şərt access_state-dir.
        if not user.is_active or user_access_is_login_blocked(user):
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


class CustomPasswordResetForm(PasswordResetForm):
    """Password reset request form that sends both a short-lived OTP and link."""

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

    #: Yer-tutucu e-poçtla gələn istifadəçiyə göstərilən YEGANƏ yol.
    placeholder_email_message = pgettext_lazy(
        "accounts.form.password_reset.error",
        "Hesabınızda real e-poçt ünvanı qeydə alınmayıb — e-poçt qeydiyyatı üçün RİM-ə müraciət edin.",
    )

    def clean_email(self):
        """Yer-tutucu domen → poçt yox, RİM göstərişi.

        ``@placeholder.invalid``-ə poçt marşrutlanmır (RFC 2606), ona görə
        «göndərdik» demək yalan olardı.  Yoxlama YALNIZ yazılan dəyərə baxır —
        bazaya sorğu yoxdur, deməli hesabın mövcudluğu sızmır.
        """

        email = self.cleaned_data["email"]
        if email_is_placeholder(email):
            raise forms.ValidationError(self.placeholder_email_message, code="placeholder_email")
        return email

    def get_users(self, email):
        """Köçürülmüş (parolsuz) hesab da bərpa edə bilər — R-8.

        Django-nun `PasswordResetForm.get_users()` `has_usable_password()`
        olmayan hesabı süzür.  Bu, LDAP/sistem hesabları üçün doğru defolt,
        AMMA köçürülmüş 8 500+ istifadəçi məhz belədir: kredensiallar QƏSDƏN
        köçürülməyib (`services/rim/credentials.py`).  Süzgəc onları həm
        girişdən, həm bərpadan kəsirdi — «done» səhifəsi görünür, poçt getmir.

        Ona görə burada parolun mövcudluğu YOX, **girişin açıq olması** meyardır:

        * ``is_active`` — ``staged`` hesab onsuz da False-dur;
        * ``access_state`` ``staged``/``archived`` deyil (tək mənbə:
          ``login_blocked_access_states``) — arxiv hesabın ``is_active``-i
          registrar trigger-ləri üçün True qalır, bərpa isə bağlıdır;
        * e-poçt yer-tutucu deyil — belə ünvana poçt getmir (üstdəki
          ``clean_email`` onsuz da bloklayır, bu isə hədəf tərəfli qoruma:
          başqa istifadəçinin real e-poçtu ilə yer-tutuculu hesab açılmasın).

        Uyğunluq DB-nin kanonik (NFKC + trim + lower) ifadə indeksləri ilə eyni
        formadadır — Django-nun ``iexact``-ı NFKC normallaşdırmır.
        """

        User = get_user_model()
        email_field = User.get_email_field_name()
        if email_is_placeholder(email):
            return
        candidates = canonical_identity_queryset(
            User._default_manager.filter(is_active=True),
            email_field,
            email,
        )
        for user in candidates.order_by("pk"):
            if email_is_placeholder(getattr(user, email_field, "")):
                continue
            if user_access_is_login_blocked(user):
                continue
            yield user

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
        self.password_reset_users = []
        for user in self.get_users(email):
            code, expires_at, _otp = issue_email_otp(user, purpose=EmailOTP.Purpose.PASSWORD_RESET)
            self.password_reset_users.append(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            reset_url = build_absolute_url(
                reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token}),
                request=request,
            )
            context = {
                "brand": getattr(settings, "SITE_BRAND_NAME", "") or "EMSArena",
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
