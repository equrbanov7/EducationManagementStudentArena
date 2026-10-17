"""Məcburi profil məlumatları — siyasət (sahib 2026-10-17).

Sahib: «Daxil olan hər kəsə ilk dəfə — kimdəsə FİN kod xanası ya da hansı xana məlumatı vacibdir, yoxdursa —
məcburi doldurma et. Və izahda yaz ki nəyə görə lazımdır.»

Bu modul YEGANƏ mənbədir: hansı rola hansı sahə lazımdır, sahə «doludur» nə deməkdir, kim azaddır, dəyər necə
normallaşdırılır. Qapı (``middleware_profile_completion``), səhifə (``views/auth/profile_completion``), RİM
filtri («Məlumat natamam») və hesabat əmri hamısı buradan oxuyur.

QAYDALAR

* Rol → sahə xəritəsi ``ROLE_REQUIREMENTS``-dədir (tələbə / heyət). Rolu olmayan, yalnız məzun / valideyn /
  «member» hesabı heç nə doldurmur.
* «Dolu» sahə HEÇ VAXT yenidən soruşulmur — ATİS-dən (rəsmi mənbə) və ya RİM-dən gələn FİN, telefon, e-poçt
  olduğu kimi qalır; səhifə yalnız BOŞ sahələri göstərir və yalnız onları yazır.
* E-poçt «dolu» deyil: boşdursa və ya yer-tutucudursa (``…@placeholder.invalid``) — belə ünvana parol bərpası
  kodu getmir (bax ``forms/auth/login.CustomPasswordResetForm``).
* Azad: superuser, ``qa.*`` QA hesabları, aktiv olmayan / arxiv (məzun, xaric) / mərhələlənmiş hesablar,
  ilk-giriş axınındakı hesab (o axın üstündür) və başqasının adından baxış (view-as).
* Söndürmə: «Sistem tənzimləmələri» → ``profile.required_fields_enabled`` (qəza açarı) və hər sahə üçün ayrıca
  ``profile.require_<sahə>``. Testlərdə defolt ``PROFILE_COMPLETION_ENABLED=False`` (bax ``config/settings/test``).
* FİN və telefon DƏYƏRLƏRİ heç vaxt loga / audit-ə yazılmır — yalnız sahə adları.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.utils.translation import pgettext, pgettext_lazy

from core import runtime_settings
from core.roles import ProfileRole
from core.validators import FIN_PATTERN, normalize_fin

_CTX = "accounts.profile_completion"

FIELD_FIN = "fin"
FIELD_PHONE = "phone"
FIELD_EMAIL = "email"

ROLE_STUDENT = "student"
ROLE_STAFF = "staff"

#: Tələbə ailəsi — eyni dəst sorğu qapısında da işlənir (``apps/surveys/services/gate``).
STUDENT_ROLE_NAMES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
#: Heyət sayılmayan rollar — məzun, valideyn, «member» heç nə doldurmur.
NON_STAFF_ROLE_NAMES = frozenset({ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT, "alumni", "parent", "member"})

#: QA hesabları (``qa.teacher``, ``qa.student`` …) — bələdçi / avtomatik yoxlama hesablarıdır, qapıda dayanmır.
QA_USERNAME_PREFIX = "qa."

ENABLED_KEY = "profile.required_fields_enabled"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    setting_key: str
    label: object
    why: object
    placeholder: object
    input_type: str
    autocomplete: str
    inputmode: str
    max_length: int


FIELDS: dict[str, FieldSpec] = {
    spec.key: spec
    for spec in (
        FieldSpec(
            FIELD_FIN,
            "profile.require_fin",
            pgettext_lazy(_CTX, "FİN kod"),
            pgettext_lazy(
                _CTX,
                "Rəsmi sənədlər (arayış, diplom əlavəsi), dövlət sistemləri (ATİS/DİM) ilə uyğunlaşdırma və hesabınızın "
                "bərpasında kimliyinizi təsdiqləmək üçün. Şəxsiyyət vəsiqəsinin arxa üzündəki 7 simvoldur.",
            ),
            pgettext_lazy(_CTX, "məs: 5ABC12D"),
            "text",
            "off",
            "text",
            7,
        ),
        FieldSpec(
            FIELD_PHONE,
            "profile.require_phone",
            pgettext_lazy(_CTX, "Mobil telefon"),
            pgettext_lazy(_CTX, "Təcili xəbərdarlıqlar və hesabın bərpası üçün."),
            # Operator (050, 055 …) ayrıca seçilir — xanaya yalnız qalan 7 rəqəm yazılır (sahib 2026-10-17).
            pgettext_lazy(_CTX, "məs: 123 45 67"),
            "tel",
            "tel",
            "tel",
            20,
        ),
        FieldSpec(
            FIELD_EMAIL,
            "profile.require_email",
            pgettext_lazy(_CTX, "Şəxsi e-poçt"),
            pgettext_lazy(
                _CTX,
                "Parol bərpası kodu bu ünvana göndərilir. Hər gün istifadə etdiyiniz ünvanı yazın (məs. Gmail).",
            ),
            pgettext_lazy(_CTX, "məs: adiniz@gmail.com"),
            "email",
            "email",
            "email",
            254,
        ),
    )
}

#: Rol → məcburi sahələr (sıra = səhifədəki sıra). Yeni rol / sahə yalnız burada əlavə olunur.
ROLE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    ROLE_STUDENT: (FIELD_FIN, FIELD_PHONE, FIELD_EMAIL),
    ROLE_STAFF: (FIELD_FIN, FIELD_PHONE, FIELD_EMAIL),
}

#: Azərbaycan mobil operator kodları — telefon xanasının yanında seçilir (sahib 2026-10-17: «050, 055 kimi
#: ordan seçib yazsın»). ``OPERATOR_OTHER`` → xarici nömrə, tam ``+`` formatında yazılır.
AZ_MOBILE_OPERATORS = ("050", "051", "055", "099", "070", "077", "010", "060")
OPERATOR_OTHER = "other"
PHONE_OPERATOR_FIELD = "phone_operator"
_LOCAL_DIGITS = 7

#: Mobil nömrədə ən az / ən çox rəqəm (ölkə kodu daxil).
_PHONE_MIN_DIGITS = 9
_PHONE_MAX_DIGITS = 15
_PHONE_ALLOWED = re.compile(r"^\+?[0-9()\-\s.]+$")


# ── Açarlar ─────────────────────────────────────────────────────────────────────────────────────────────


def gate_enabled() -> bool:
    return runtime_settings.get_bool(ENABLED_KEY)


def field_enabled(key: str) -> bool:
    return runtime_settings.get_bool(FIELDS[key].setting_key)


# ── Kim / nə ────────────────────────────────────────────────────────────────────────────────────────────


def role_family(memberships) -> str:
    """Aktiv üzvlüklərdən ``staff`` / ``student`` / ``""`` (heyət rolu varsa — heyət)."""
    names = set()
    for membership in memberships or ():
        role = getattr(membership, "role", None)
        if role is None or not getattr(membership, "is_active", True) or not getattr(role, "is_active", True):
            continue
        names.add(ProfileRole.normalize_membership_role_name(getattr(role, "name", "")))
    if names - NON_STAFF_ROLE_NAMES:
        return ROLE_STAFF
    if names & STUDENT_ROLE_NAMES:
        return ROLE_STUDENT
    return ""


def is_exempt_user(user) -> bool:
    """Qapının HEÇ VAXT dayandırmadığı hesab (request-dən asılı olmayan hissə)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return True
    if getattr(user, "is_superuser", False) or not getattr(user, "is_active", False):
        return True
    if str(getattr(user, "username", "") or "").lower().startswith(QA_USERNAME_PREFIX):
        return True
    profile = getattr(user, "profile", None)
    if profile is None:
        return True
    if getattr(profile, "access_state", "active") != "active" or getattr(profile, "is_deleted", False):
        return True
    # İlk-giriş axını (e-poçt OTP + öz parolu) üstündür — o bitənə qədər bu qapı gözləyir.
    return bool(getattr(profile, "password_change_required", False))


def has_value(user, key: str) -> bool:
    profile = getattr(user, "profile", None)
    if key == FIELD_FIN:
        return bool(str(getattr(profile, "fin", "") or "").strip())
    if key == FIELD_PHONE:
        return len(re.sub(r"\D", "", str(getattr(profile, "phone", "") or ""))) >= 7
    if key == FIELD_EMAIL:
        from .identity import email_is_placeholder

        email = str(getattr(user, "email", "") or "").strip()
        return bool(email) and not email_is_placeholder(email)
    return True


def required_fields(user, memberships) -> list[FieldSpec]:
    family = role_family(memberships)
    return [FIELDS[key] for key in ROLE_REQUIREMENTS.get(family, ()) if field_enabled(key)]


def missing_fields(user, memberships) -> list[FieldSpec]:
    """Doldurulmalı sahələr — qapı söndürülüdürsə və ya hesab azaddırsa ``[]``."""
    if not gate_enabled() or is_exempt_user(user):
        return []
    return [spec for spec in required_fields(user, memberships) if not has_value(user, spec.key)]


def request_memberships(request):
    """Cari təşkilatın üzvlükləri (middleware artıq yükləyib); yoxdursa bütün aktiv üzvlüklər."""
    memberships = getattr(request, "org_memberships", None)
    if memberships or getattr(request, "organization", None) is not None:
        # Təşkilat həll olunub — üzvlük siyahısı (boş olsa belə, məs. sahib) həqiqətdir; əlavə sorğu yoxdur.
        return memberships or []
    from apps.organizations.models import Membership

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    return list(Membership.objects.filter(user=user, is_active=True).select_related("role"))


def missing_for_request(request) -> list[FieldSpec]:
    if getattr(request, "is_view_as", False):
        return []
    user = getattr(request, "user", None)
    if not gate_enabled() or is_exempt_user(user):
        return []
    return missing_fields(user, request_memberships(request))


def missing_users_q(prefix: str = "") -> Q:
    """``User`` sorğusu üçün «məlumat natamam» şərti (RİM filtri, hesabat). Rol süzgəci çağırandadır."""
    from .identity import PLACEHOLDER_EMAIL_DOMAIN

    clauses = Q(pk__in=[])
    if field_enabled(FIELD_FIN):
        clauses |= Q(**{f"{prefix}profile__fin__isnull": True}) | Q(**{f"{prefix}profile__fin": ""})
    if field_enabled(FIELD_PHONE):
        clauses |= Q(**{f"{prefix}profile__phone": ""})
    if field_enabled(FIELD_EMAIL):
        clauses |= Q(**{f"{prefix}email": ""}) | Q(**{f"{prefix}email__iendswith": "@" + PLACEHOLDER_EMAIL_DOMAIN})
    exempt = Q(**{f"{prefix}is_superuser": True}) | Q(**{f"{prefix}username__istartswith": QA_USERNAME_PREFIX})
    return clauses & ~exempt


# ── Dəyərin yoxlanması ──────────────────────────────────────────────────────────────────────────────────


def clean_fin(raw) -> str:
    value = normalize_fin(raw)
    if not value:
        raise ValidationError(pgettext(_CTX, "FİN kodunu yazın."), code="required")
    if not FIN_PATTERN.fullmatch(value):
        raise ValidationError(
            pgettext(_CTX, "FİN kod 7 simvoldur: yalnız latın hərfləri və rəqəmlər (məs. 5ABC12D)."), code="invalid"
        )
    return value


def clean_phone(raw) -> str:
    """Azərbaycan nömrəsi ``+994XXXXXXXXX`` şəklinə gətirilir; xarici nömrə ``+`` ilə qəbul olunur."""
    text = " ".join(str(raw or "").split())
    if not text:
        raise ValidationError(pgettext(_CTX, "Mobil telefon nömrəsini yazın."), code="required")
    digits = re.sub(r"\D", "", text)
    if not _PHONE_ALLOWED.match(text) or not (_PHONE_MIN_DIGITS <= len(digits) <= _PHONE_MAX_DIGITS):
        raise ValidationError(pgettext(_CTX, "Telefon nömrəsi düzgün deyil (məs. 050 123 45 67)."), code="invalid")
    if text.startswith("+"):
        return "+" + digits
    if digits.startswith("994") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+994" + digits[1:]
    if len(digits) == 9:
        return "+994" + digits
    raise ValidationError(pgettext(_CTX, "Telefon nömrəsi düzgün deyil (məs. 050 123 45 67)."), code="invalid")


def combine_phone(data) -> str:
    """Operator seçimi + qalan rəqəmlər → ``clean_phone``-un qəbul etdiyi tam nömrə.

    Operator seçilibsə xanada düz 7 rəqəm olmalıdır (``050`` + ``1234567``). Operator gəlməyibsə (köhnə forma,
    API) və ya «Xarici nömrə» seçilibsə xananın özü tam nömrə kimi yoxlanılır.
    """
    operator = str(data.get(PHONE_OPERATOR_FIELD) or "").strip()
    raw = str(data.get(FIELD_PHONE) or "")
    if operator not in AZ_MOBILE_OPERATORS:
        return raw
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) == 9 and digits[:2] == operator[1:]:
        digits = digits[2:]  # «50 123 45 67» yazılıbsa operator təkrarı atılır
    elif len(digits) == 10 and digits[:3] == operator:
        digits = digits[3:]
    if len(digits) != _LOCAL_DIGITS or not _PHONE_ALLOWED.match(raw.strip()):
        raise ValidationError(pgettext(_CTX, "Operator kodundan sonra 7 rəqəm yazın (məs. 123 45 67)."), code="invalid")
    return operator + digits


def clean_email(raw) -> str:
    from .identity import email_is_placeholder
    from .models import EmailOTP

    value = EmailOTP.normalize_email(raw)
    if not value:
        raise ValidationError(pgettext(_CTX, "E-poçt ünvanını yazın."), code="required")
    try:
        validate_email(value)
    except ValidationError as exc:
        raise ValidationError(pgettext(_CTX, "Etibarlı e-poçt ünvanı yazın."), code="invalid") from exc
    if email_is_placeholder(value):
        raise ValidationError(pgettext(_CTX, "Etibarlı e-poçt ünvanı yazın."), code="invalid")
    return value


CLEANERS = {FIELD_FIN: clean_fin, FIELD_PHONE: clean_phone, FIELD_EMAIL: clean_email}


__all__ = [
    "AZ_MOBILE_OPERATORS",
    "CLEANERS",
    "ENABLED_KEY",
    "FIELDS",
    "FIELD_EMAIL",
    "FIELD_FIN",
    "FIELD_PHONE",
    "FieldSpec",
    "OPERATOR_OTHER",
    "PHONE_OPERATOR_FIELD",
    "ROLE_REQUIREMENTS",
    "ROLE_STAFF",
    "ROLE_STUDENT",
    "combine_phone",
    "field_enabled",
    "gate_enabled",
    "has_value",
    "is_exempt_user",
    "missing_fields",
    "missing_for_request",
    "missing_users_q",
    "request_memberships",
    "required_fields",
    "role_family",
]
