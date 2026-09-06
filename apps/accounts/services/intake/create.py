"""Hesab yaradılmasının TƏK NÜVƏSİ — tələbə (toplu idxal) və müəllim (RİM).

NİYƏ AYRICA MODUL? 2026-09-06-ya qədər hesab yaratmağın yeganə kod yolu
``apply.py::_create_user`` idi və o, TƏLƏBƏYƏ bağlı idi (qrup + proqram +
kurikulum + ``StudentAcademicRecord``). RİM mərkəzinə «tək-tək hesab yarat»
(tələbə VƏ müəllim) səthi əlavə ediləndə iki seçim vardı: məntiqi kopyalamaq,
və ya nüvəni ayırıb hər iki səthin ONU çağırması. İkincisi seçilib — parol
siyasəti, ``password_change_required`` müqaviləsi və audit sətri BİR yerdədir.

MÜQAVİLƏ

* ``create_account`` HESABIN ÖZÜNÜ qurur: ``User`` + ``UserProfile`` +
  ``Membership``. Tələbəyə xas addımlar (qrup adı, ixtisas etiketi, kurikulum,
  ``StudentAcademicRecord``) YALNIZ ``kind == "student"`` və ``student_targets``
  verildikdə icra olunur — müəllim heç vaxt akademik qeyd almır.
* Parol TƏSADÜFİ generasiya olunur, YALNIZ qaytarılır; nə audit-ə, nə log-a
  yazılır (bax `apply.py` və `rim/credentials.py` başlıqları).
* ``password_change_required=True`` + ``email_verified=False`` → ilk girişdə
  e-poçt təsdiqi (OTP) + öz parolu məcburidir (`FirstLoginPasswordMiddleware`).
* Tranzaksiya İDARƏSİ ÇAĞIRANDADIR: toplu idxal hər sətri öz savepoint-ində
  icra edir, RİM-in tək-tək səthi isə bir ``atomic()`` blokunda. Bu modul öz
  başına ``atomic()`` açmır ki, iç-içə savepoint semantikası pozulmasın.
"""

from __future__ import annotations

import unicodedata

from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction
from core.roles import ProfileRole

from ...models import UserProfile

_CTX = "student_intake"

User = get_user_model()

#: Oxunaqlı, oxşar simvolsuz (0/O, 1/l/I yox) — `provision_student_credentials`
#: komandası ilə EYNİ əlifba (çap-parol axını dəyişmir).
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
_PASSWORD_LENGTH = 10

#: Hesab növləri — kataloqdakı rol adı ilə eyni olmalıdır.
KIND_STUDENT = "student"
KIND_TEACHER = "teacher"
ACCOUNT_KINDS = (KIND_STUDENT, KIND_TEACHER)

STUDENT_ROLE_NAME = KIND_STUDENT
TEACHER_ROLE_NAME = KIND_TEACHER

#: Növ → təşkilat rolunun adı. `teacher` seçimi `services/people/constants.py`
#: `DEFAULT_TEACHER_ROLE_NAME` ilə üst-üstə düşür (müəllim statusu verməyin
#: kanonik yolu) — kataloq eyni rolu görsün deyə.
_ROLE_NAME_BY_KIND = {
    KIND_STUDENT: STUDENT_ROLE_NAME,
    KIND_TEACHER: TEACHER_ROLE_NAME,
}

_PROFILE_ROLE_BY_KIND = {
    KIND_STUDENT: ProfileRole.STUDENT,
    KIND_TEACHER: ProfileRole.TEACHER,
}

#: İstifadəçi adı prefiksi (köçürülmüş `myedu.student.<id>` / `myedu.worker.<id>`
#: ilə eyni məntiq: mənbəni adından görmək olur, saf rəqəmli username yaranmır).
USERNAME_PREFIXES = {
    KIND_STUDENT: "st",
    KIND_TEACHER: "mu",
}

#: `username` sahəsinin təhlükəsiz uzunluq həddi (əlavə `.2` şəkilçisi üçün pay).
_USERNAME_BASE_MAX = 140


def _casefold(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def username_base(kind: str, *, code: str, fin: str) -> str:
    """Kod (tələbə/işçi nömrəsi) varsa ondan, yoxsa FİN-dən ad qurur.

    TƏK MƏNBƏ: toplu idxal (`validate.py`) və RİM-in tək-tək səthi eyni funksiyanı
    çağırır — ad şablonu iki yerdə saxlanılmır.
    """

    prefix = USERNAME_PREFIXES.get(kind, USERNAME_PREFIXES[KIND_STUDENT])
    fallback = "%s.fin.%s" % (prefix, str(fin or "").lower())
    base = "%s.%s" % (prefix, _casefold(code).replace(" ", "")) if code else fallback
    return "".join(ch for ch in base if ch.isalnum() or ch in "._-")[:_USERNAME_BASE_MAX] or fallback


def claim_username(base: str, *, taken=()) -> str:
    """Boş istifadəçi adı seçir: tutulubsa ``.2``, ``.3`` … şəkilçisi əlavə edir.

    ``taken`` — hələ DB-yə YAZILMAMIŞ, cari partiyada rezerv olunmuş adlar
    (toplu idxalda eyni faylın iki sətri eyni adı iddia edə bilər).

    E-poçt sahəsi də yoxlanılır, çünki giriş formu «istifadəçi adı VƏ YA e-poçt»
    qəbul edir — birinin adı digərinin e-poçtu ola bilməz.
    """

    candidate = base
    suffix = 1
    while (
        candidate in taken
        or User.objects.filter(username__iexact=candidate).exists()
        or User.objects.filter(email__iexact=candidate).exists()
    ):
        suffix += 1
        candidate = "%s.%d" % (base, suffix)
    return candidate


def generate_initial_password() -> str:
    """Birdəfəlik ilkin parol — TƏK MƏNBƏ.

    `import_users_from_excel` management komandası da bunu çağırır ki, UI səthi
    ilə server aləti eyni parol siyasətini (əlifba + uzunluq) daşısın; siyasət
    dəyişəndə iki yerdə düzəliş etmək lazım gəlməsin.
    """

    return get_random_string(_PASSWORD_LENGTH, _PASSWORD_ALPHABET)


class IntakeApplyError(Exception):
    """Bütün faylı dayandıran şərt (məsələn təşkilatda `student` rolu yoxdur)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self):
        return self.code


def account_role(organization, kind: str = KIND_STUDENT):
    """Təşkilatın ``student`` / ``teacher`` rolu; yoxdursa ``IntakeApplyError``."""

    name = _ROLE_NAME_BY_KIND.get(kind)
    if name is None:
        raise IntakeApplyError("account_kind_unknown", pgettext(_CTX, "Naməlum hesab növü."))
    # Eyni adlı bir neçə rol olsa ƏN YÜKSƏK səviyyəli götürülür (`people.actions`
    # ilə eyni qayda) — kataloq və RİM eyni rolu seçsin deyə.
    role = organization.roles.filter(name=name, is_active=True).order_by("-level").first()
    if role is None:
        if kind == KIND_TEACHER:
            raise IntakeApplyError(
                "teacher_role_missing",
                pgettext(_CTX, "Bu təşkilatda aktiv «müəllim» rolu yoxdur — əvvəlcə rol kataloqu qurulmalıdır."),
            )
        raise IntakeApplyError(
            "student_role_missing",
            pgettext(_CTX, "Bu təşkilatda aktiv «student» rolu yoxdur — əvvəlcə rol kataloqu qurulmalıdır."),
        )
    return role


def student_role(organization):
    """Geriyə-uyğun ad — `apply.py` və management komandası bunu çağırır."""

    return account_role(organization, KIND_STUDENT)


def teacher_role(organization):
    return account_role(organization, KIND_TEACHER)


def ensure_curriculum(organization, program, admission_year):
    from apps.registrar.models import Curriculum

    curriculum, _created = Curriculum.objects.get_or_create(
        organization=organization,
        program=program,
        admission_year=admission_year,
        defaults={"name": "", "is_active": True},
    )
    return curriculum


def _build_user(values, *, password):
    user = User.objects.create_user(
        username=values["username"],
        email=values["email"],
        password=password,
    )
    user.first_name = values["first_name"]
    user.last_name = values["last_name"]
    user.is_active = True
    user.save(update_fields=["first_name", "last_name", "is_active"])
    return user


def _write_profile(user, *, organization, kind, values, group_name, specialization):
    profile, _created = UserProfile.objects.get_or_create(user=user)
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = _PROFILE_ROLE_BY_KIND[kind]
    profile.access_state = UserProfile.AccessState.ACTIVE
    profile.fin = values["fin"]
    profile.patronymic = values["patronymic"]
    profile.gender = values["gender"]
    profile.birth_date = values["birth_date"]
    profile.phone = values["phone"]
    profile.institutional_identifier = values["student_code"] or None
    profile.student_group_number = group_name
    profile.student_specialization = specialization
    profile.password_change_required = True
    profile.email_verified = False
    profile.save(
        update_fields=[
            "organization",
            "organization_type",
            "role",
            "access_state",
            "fin",
            "patronymic",
            "gender",
            "birth_date",
            "phone",
            "institutional_identifier",
            "student_group_number",
            "student_specialization",
            "password_change_required",
            "email_verified",
            "updated_at",
        ]
    )
    return profile


def _write_academic_record(user, *, organization, values, targets):
    """Tələbəyə xas addım — müəllim yolunda HEÇ VAXT çağırılmır."""

    program = targets["program"]
    admission_year = targets["admission_year"]
    curriculum = targets.get("curriculum") or ensure_curriculum(organization, program, admission_year)

    from apps.registrar.models import StudentAcademicRecord

    StudentAcademicRecord.objects.get_or_create(
        organization=organization,
        student=user,
        program=program,
        defaults={
            "curriculum": curriculum,
            "group": targets["group"],
            "admission_year": admission_year,
            "status": "enrolled",
            "is_active": True,
            # ATİS qəbul atributları (ekran 08). Sütun faylda yoxdursa
            # `validate.admission.enrich` default qoyur — sahə heç vaxt NULL
            # qalmır, ona görə reyestrin (ekran 09) sütunları həmişə doludur.
            "atis_id": values.get("atis_id", ""),
            "admission_score": values.get("admission_score"),
            "admission_exam_type": values.get("admission_exam_type", ""),
            "education_form": values.get("education_form", "full_time"),
            "funding_type": values.get("funding_type", "paid"),
        },
    )


def _audit_changes(user, *, kind, values, targets, group_name, scope_unit):
    # Parol QƏSDƏN yoxdur — audit jurnalı sirr saxlamır.
    changes = {
        "username": user.username,
        "fin": values["fin"],
    }
    if kind == KIND_STUDENT:
        changes.update(
            {
                "group": group_name,
                "program": str(targets["program"].pk),
                "admission_year": targets["admission_year"],
                "funding": values.get("funding_type", ""),
                "education_form": values.get("education_form", ""),
            }
        )
    else:
        changes["kind"] = KIND_TEACHER
        changes["scope_unit"] = str(getattr(scope_unit, "pk", "") or "")
    changes["email_placeholder"] = values["email"].endswith(".invalid")
    return changes


def create_account(
    *,
    organization,
    kind,
    values,
    role,
    actor,
    request=None,
    student_targets=None,
    group_name="",
    specialization="",
    scope_unit=None,
    audit_reason="student_intake_created",
):
    """Bir hesab yaradır və ``(user, birdəfəlik parol)`` qaytarır.

    Args:
        kind: ``"student"`` və ya ``"teacher"``.
        values: ``username`` / ``email`` / ad-soyad / FİN / şəxsi sahələr.
        student_targets: YALNIZ tələbə üçün — ``group`` / ``program`` /
            ``curriculum`` / ``admission_year``. Müəllim yolunda ``None``.
        scope_unit: müəllim üzvlüyünün kafedrası (opsional).
    """

    if kind not in ACCOUNT_KINDS:
        raise IntakeApplyError("account_kind_unknown", pgettext(_CTX, "Naməlum hesab növü."))

    password = generate_initial_password()
    user = _build_user(values, password=password)
    profile = _write_profile(
        user,
        organization=organization,
        kind=kind,
        values=values,
        group_name=group_name,
        specialization=specialization,
    )
    user.profile = profile

    from apps.organizations.models import Membership

    Membership.objects.create(
        user=user,
        organization=organization,
        role=role,
        scope_unit=scope_unit if kind == KIND_TEACHER else None,
        assigned_by=actor,
        is_primary=True,
        is_active=True,
    )

    if kind == KIND_STUDENT:
        _write_academic_record(user, organization=organization, values=values, targets=student_targets or {})

    log_action(
        action=AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=user,
        reason=audit_reason,
        changes=_audit_changes(
            user,
            kind=kind,
            values=values,
            targets=student_targets or {},
            group_name=group_name,
            scope_unit=scope_unit,
        ),
        request=request,
        # Qonşu RİM əməlləri ilə eyni sütun dəsti — audit siyahısı hansı hesabın
        # yaradıldığını sətrin özündən göstərsin (`obj` yalnız content_type verir).
        resource_type="User",
        resource_id=str(user.pk),
        resource_repr=user.username,
    )
    return user, password


__all__ = [
    "ACCOUNT_KINDS",
    "KIND_STUDENT",
    "KIND_TEACHER",
    "STUDENT_ROLE_NAME",
    "TEACHER_ROLE_NAME",
    "IntakeApplyError",
    "USERNAME_PREFIXES",
    "account_role",
    "claim_username",
    "create_account",
    "ensure_curriculum",
    "generate_initial_password",
    "student_role",
    "teacher_role",
    "username_base",
]
