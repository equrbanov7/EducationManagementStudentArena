"""
User profile models for EMS Arena.
Extends Django's User model with additional profile information.
"""

import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.hashers import check_password, identify_hasher
from django.db import models
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.translation import pgettext, pgettext_lazy

from core.constants import OrganizationType

# M2 (2026-07-02): ProfileRole core.roles-a köçürülüb (dövri asılılıq kökü idi).
# Köhnə `from apps.accounts.models import ProfileRole` import səthi qorunur (AGENTS §1).
from core.roles import ProfileRole  # noqa: F401
from core.utils import get_auth_otp_expiry_seconds, get_auth_otp_max_attempts
from core.validators import validate_fin


class EmailOTP(models.Model):
    """Secure one-time password record for signup, login, and recovery flows."""

    _HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup verification"
        LOGIN = "login", "Login verification"
        PASSWORD_RESET = "password_reset", "Password reset"
        ADMIN_LOGIN = "admin_login", "Admin login"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otps",
        null=True,
        blank=True,
    )
    email = models.EmailField(db_index=True, blank=True, default="")
    # Legacy storage kept temporarily so pre-migration OTP rows remain verifiable.
    code = models.CharField(max_length=128, blank=True, default="")
    otp_hash = models.CharField(max_length=64, blank=True, default="")
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.SIGNUP,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False)
    attempts_count = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"
        indexes = [
            models.Index(fields=["email", "purpose", "created_at"]),
            models.Index(fields=["user", "purpose", "created_at"]),
        ]

    @staticmethod
    def normalize_email(email):
        return BaseUserManager.normalize_email(str(email or "").strip()).lower()

    @classmethod
    def build_otp_hash(cls, *, email, otp, purpose):
        normalized_email = cls.normalize_email(email)
        payload = f"{purpose}:{normalized_email}:{str(otp or '').strip()}"
        return salted_hmac(
            "apps.accounts.email_otp",
            payload,
            secret=settings.SECRET_KEY,
            algorithm="sha256",
        ).hexdigest()

    @staticmethod
    def _code_is_hashed(value):
        try:
            identify_hasher(value)
            return True
        except Exception:
            return False

    @classmethod
    def _is_sha256_digest(cls, value):
        return bool(value and cls._HEX_DIGEST_RE.fullmatch(str(value).strip().lower()))

    def save(self, *args, **kwargs):
        if self.user_id and not self.email:
            self.email = self.normalize_email(getattr(self.user, "email", ""))
        else:
            self.email = self.normalize_email(self.email)

        if self.code and not self.otp_hash and not self._code_is_hashed(self.code):
            self.otp_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=self.code,
                purpose=self.purpose,
            )
            self.code = ""
        elif self.otp_hash and not self._is_sha256_digest(self.otp_hash):
            self.otp_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=self.otp_hash,
                purpose=self.purpose,
            )

        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(seconds=get_auth_otp_expiry_seconds())
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def matches_code(self, raw_code):
        candidate = str(raw_code or "").strip()
        if not candidate:
            return False

        if self.otp_hash:
            candidate_hash = self.build_otp_hash(
                email=self.email or getattr(self.user, "email", ""),
                otp=candidate,
                purpose=self.purpose,
            )
            if constant_time_compare(candidate_hash, self.otp_hash):
                return True

        if self.code:
            if self._code_is_hashed(self.code):
                return check_password(candidate, self.code)
            return constant_time_compare(candidate, self.code)

        return False

    @property
    def remaining_attempts(self):
        return max(0, get_auth_otp_max_attempts() - int(self.attempts_count or 0))

    def mark_verified(self):
        self.is_verified = True
        self.is_used = True
        self.save(update_fields=["is_verified", "is_used"])

    def invalidate(self):
        if self.is_used:
            return
        self.is_used = True
        self.save(update_fields=["is_used"])

    def register_failed_attempt(self):
        self.attempts_count = int(self.attempts_count or 0) + 1
        if self.attempts_count >= get_auth_otp_max_attempts():
            self.is_used = True
            self.save(update_fields=["attempts_count", "is_used"])
            return
        self.save(update_fields=["attempts_count"])

    @classmethod
    def pending_queryset(cls, *, user=None, email=None, purpose=None):
        if not user and not email:
            return cls.objects.none()

        filters = {
            "is_used": False,
        }
        if user is not None:
            filters["user"] = user
        if email:
            filters["email"] = cls.normalize_email(email)
        if purpose:
            filters["purpose"] = purpose
        return cls.objects.filter(**filters).order_by("-created_at")

    @classmethod
    def get_matching_otp(cls, *, user=None, email=None, code="", purpose=None):
        candidate = str(code or "").strip()
        if not candidate:
            return None

        queryset = cls.pending_queryset(user=user, email=email, purpose=purpose).filter(
            expires_at__gte=timezone.now(),
        )

        for otp in queryset[:10]:
            if otp.matches_code(candidate):
                return otp

        return None


class UserProfile(models.Model):
    """
    Extended user profile with organization type and additional information.
    Links user to an organization for multi-tenant support.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")

    class AccessState(models.TextChoices):
        """Hesabın tətbiq səthlərinə buraxılma vəziyyəti.

        ``STAGED`` yalnız idarə olunan import üçün kilidli keçid vəziyyətidir;
        adi qeydiyyatların mövcud davranışı ``ACTIVE`` olaraq qalır.
        """

        ACTIVE = "active", "Aktiv giriş"
        STAGED = "staged", "Mərhələlənmiş (giriş bağlıdır)"

    access_state = models.CharField(
        max_length=16,
        choices=AccessState.choices,
        default=AccessState.ACTIVE,
        db_index=True,
        verbose_name="Giriş vəziyyəti",
        help_text="Legacy import hesabları ayrıca təsdiqlənənədək staged qalır.",
    )

    # Organization linkage for multi-tenant support
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
        verbose_name="Təşkilat",
        help_text="İstifadəçinin aid olduğu təşkilat",
    )

    requested_organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_members",
        verbose_name="Müraciət edilən təşkilat",
        help_text="Signup zamanı seçilən, amma hələ qoşulmadığı təşkilat",
    )

    requested_organization_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Müraciət edilən təşkilat adı",
        help_text="Təşkilat DB-də yoxdursa signup zamanı daxil edilən ad",
    )

    requested_organization_message = models.CharField(
        max_length=280,
        blank=True,
        default="",
        verbose_name="Təşkilata müraciət mesajı",
        help_text="Tələbənin təşkilata qoşulma üçün yazdığı qısa mesaj",
    )

    organization_type = models.CharField(
        max_length=20,
        choices=OrganizationType.CHOICES,
        default=OrganizationType.INDIVIDUAL,
        verbose_name="Təşkilat tipi",
        help_text="Hansı təşkilat tipində qeydiyyatdan keçdiniz",
    )

    country = models.CharField(max_length=100, blank=True, default="", verbose_name="Ölkə")

    student_university_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Universitet adı",
        help_text="Tələbə üçün universitet adı (əgər varsa)",
    )

    student_school_identifier = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="Məktəb nömrəsi/identifikatoru",
        help_text="Tələbə üçün məktəb nömrəsi və ya rəsmi identifikator",
    )

    # ``student_school_identifier`` tarixən məktəbin öz təşkilat kodunu daşıya
    # bilir və tələbələr arasında unikal deyil. Ona görə legacy cutover üçün
    # həmin biznes sahəsinin mənası dəyişdirilmir; təsdiqlənmiş, tələbəyə aid
    # institusional açar ayrıca və boş/null semantikasını qoruyaraq saxlanılır.
    institutional_identifier = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="İnstitusional tələbə identifikatoru",
        help_text="Yalnız təsdiqlənmiş import mapping-i ilə doldurulan tələbə açarı.",
    )

    fin = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        default=None,
        unique=True,
        validators=[validate_fin],
        verbose_name="FİN",
        help_text="Şəxsiyyət vəsiqəsi FİN kodu (7 simvol, A-Z0-9) — idxal/uzlaşdırma açarı.",
    )

    student_specialization = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="İxtisas / Fakültə",
        help_text="Tələbənin ixtisası və ya fakültəsi",
    )

    student_group_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Qrup / Sinif",
        help_text="Tələbənin qrup nömrəsi və ya sinif qrupu",
    )

    department = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Departament / Kafedra",
        help_text="Müəllim və ya işçinin departamenti/kafedrası",
    )

    class AcademicTitle(models.TextChoices):
        """Elmi ad / vəzifə — müəllim və akademik heyət üçün."""

        ASSISTANT = "assistant", pgettext_lazy("accounts.academic_title", "Assistent")
        TEACHER = "teacher", pgettext_lazy("accounts.academic_title", "Müəllim")
        SENIOR_TEACHER = "senior_teacher", pgettext_lazy("accounts.academic_title", "Baş müəllim")
        DOCENT = "docent", pgettext_lazy("accounts.academic_title", "Dosent")
        PROFESSOR = "professor", pgettext_lazy("accounts.academic_title", "Professor")

    class AcademicDegree(models.TextChoices):
        """Elmi dərəcə."""

        PHD = "phd", pgettext_lazy("accounts.academic_degree", "Fəlsəfə doktoru (PhD)")
        DSC = "dsc", pgettext_lazy("accounts.academic_degree", "Elmlər doktoru")

    academic_title = models.CharField(
        max_length=30,
        choices=AcademicTitle.choices,
        blank=True,
        default="",
        verbose_name="Elmi ad / vəzifə",
        help_text="Müəllim/akademik heyət üçün: assistent → professor",
    )

    academic_degree = models.CharField(
        max_length=30,
        choices=AcademicDegree.choices,
        blank=True,
        default="",
        verbose_name="Elmi dərəcə",
        help_text="Fəlsəfə doktoru (PhD) və ya elmlər doktoru",
    )

    staff_position = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Vəzifə",
        help_text="İşçinin vəzifəsi (yalnız staff üçün)",
    )

    # RBAC role field.
    #
    # DENORMALIZED CACHE — NOT the source of truth (FAZA 10 clarification).
    #
    # The authoritative role for a user inside an organization is the
    # tenant-scoped ``organizations.Membership.role`` row. This ``profile.role``
    # field is a convenience denormalization kept in sync by the role-assignment
    # views (see apps/accounts/views/roles.py, which writes both Membership.role
    # and profile.role together).
    #
    # When the two ever disagree, trust Membership.role — it is per-organization
    # and RLS-protected, whereas profile.role is a single global value that
    # cannot represent a user who belongs to multiple organizations with
    # different roles. New code MUST resolve roles via the membership /
    # ``request.org_memberships`` path, not via this field.
    role = models.CharField(
        max_length=30,
        choices=ProfileRole.CHOICES,
        default=ProfileRole.MEMBER,
        db_index=True,
        verbose_name="Rol",
        help_text="Denormalizə keş — əsl rol Membership.role-dadır",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Avatar",
        help_text="Profil şəkli",
    )

    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon", help_text="Əlaqə nömrəsi")

    phone_secondary = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="Əlavə telefon",
        help_text="İkinci əlaqə nömrəsi. Nömrələr yalnız əməkdaş səviyyəli baxanlara göstərilir.",
    )

    bio = models.TextField(blank=True, verbose_name="Haqqında", help_text="Qısa məlumat")

    supervisor_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Nəzarətçi kodu",
        help_text="Admin/supervisor tərəfindən təyin edilir. User dəyişə bilməz.",
    )

    location = models.CharField(max_length=100, blank=True, verbose_name="Yer", help_text="Şəhər və ya ünvan")

    # ── E-university provisioning: first-login flow ─────────────────────────
    # When the administration provisions an account (no public self-signup),
    # the user first logs in with a temporary password and is then forced to
    # verify their email (OTP) and set their own password before using the
    # system. See FirstLoginPasswordMiddleware + accounts:set_initial_password.
    password_change_required = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Parol dəyişməlidir",
        help_text="İlk girişdə istifadəçi öz parolunu qurana qədər True qalır.",
    )
    email_verified = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Email təsdiqlənib",
        help_text="İlk girişdə OTP ilə təsdiqləndikdən sonra True; parol bərpası üçün istifadə olunur.",
    )

    # Superadmin tərəfindən verilən "imtahan zalı idarəçisi" icazəsi: bu bayraq
    # açıq olan istifadəçi (superadmin olmasa da) imtahan zalı və zaldakı
    # kompüter/MAC qeydlərini yarada/redaktə edə bilir. Bax:
    # apps.exams.services.access_policy.can_manage_exam_rooms.
    can_manage_exam_rooms = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Zal idarəçisi",
        help_text="Superadmin verir: imtahan zalı və kompüter/MAC qeydlərini idarə etmək icazəsi.",
    )

    # Soft-delete fields for account deletion
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name="Silinib",
        help_text="Hesab silinibsə True",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Silinmə tarixi",
        help_text="Hesabın silinmə tarixi",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaradılma tarixi")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Yenilənmə tarixi")

    class Meta:
        verbose_name = "İstifadəçi profili"
        verbose_name_plural = "İstifadəçi profilləri"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["role"]),
            models.Index(fields=["requested_organization"]),
            models.Index(fields=["is_deleted", "deleted_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    @property
    def organization_name(self):
        """Təşkilat adı, təşkilatsız istifadəçi üçün «Fərdi».

        Etiket tərcümə olunur: profil başlığında göstərilir və sabit
        azərbaycanca sətir olanda EN/RU/TR interfeysdə də azərbaycanca çıxırdı
        (2026-07-31 auditi).
        """
        if self.organization:
            return self.organization.name
        return pgettext("accounts.profile", "individual_no_organization")

    @property
    def role_level(self):
        """Numeric level for the current role."""
        return ProfileRole.LEVELS.get(self.role, 0)

    @property
    def is_academics_locked(self):
        """Akademik sahələr (müəssisə/ixtisas/qrup) qurum tərəfindən idarə olunurmu?

        Yalnız həqiqi qurum üzvlüyündə (universitet/məktəb/kurs mərkəzi) True —
        şəxsi (INDIVIDUAL tipli) təşkilatda istifadəçi öz təhsil məlumatını
        sərbəst mətnlə redaktə edə bilər.
        """
        organization = self.organization
        return organization is not None and organization.org_type != OrganizationType.INDIVIDUAL

    @property
    def academic_title_display(self):
        """«Professor · Elmlər doktoru» kimi birləşmiş etiket (boş ola bilər)."""
        parts = []
        if self.academic_title:
            parts.append(self.get_academic_title_display())
        if self.academic_degree:
            parts.append(self.get_academic_degree_display())
        return " · ".join(parts)


class AcademicProfileItem(models.Model):
    """İstifadəçinin özü idarə etdiyi akademik fəaliyyət qeydi.

    Müəllim profilində məqalə/konfrans materialı/sertifikat/tədris etdiyi fənn
    kimi bəndlər; tələbə və digər rollar da öz nailiyyətlərini (sertifikat,
    məqalə və s.) əlavə edə bilir. Yalnız sahibinə redaktə icazəsi var —
    yoxlama servis qatındadır (apps.accounts.services.academic_profile).
    """

    class Kind(models.TextChoices):
        SUBJECT = "subject", pgettext_lazy("accounts.academic_item_kind", "Tədris etdiyi fənn")
        CERTIFICATE = "certificate", pgettext_lazy("accounts.academic_item_kind", "Sertifikat")
        PUBLICATION = "publication", pgettext_lazy("accounts.academic_item_kind", "Məqalə")
        CONFERENCE = "conference", pgettext_lazy("accounts.academic_item_kind", "Konfrans materialı")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="academic_items",
        verbose_name="İstifadəçi",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="Növ")
    title = models.CharField(max_length=200, verbose_name="Başlıq")
    detail = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Ətraflı",
        help_text="Jurnal/konfrans adı, verən qurum, kafedra və s.",
    )
    year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="İl",
    )
    link = models.URLField(
        max_length=300,
        blank=True,
        default="",
        verbose_name="Keçid",
        help_text="DOI / sertifikat / nəşr keçidi (http-https)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akademik fəaliyyət qeydi"
        verbose_name_plural = "Akademik fəaliyyət qeydləri"
        ordering = ["kind", "-year", "-id"]
        indexes = [models.Index(fields=["user", "kind"])]

    def __str__(self):
        return f"{self.user_id} · {self.get_kind_display()} · {self.title[:40]}"


# Separate module keeps this already-large model module below the size budget.
from .identity_models import AccountActivationEvidence  # noqa: E402,F401
