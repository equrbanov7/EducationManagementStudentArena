"""Tələbə idxalı — PLANLARIN TƏTBİQİ (hesab + üzvlük + akademik qeyd).

Atomiklik NAXIŞI: hər sətir ÖZ savepoint-indədir (``transaction.atomic()`` iç-içə
blok). Bir sətir çökürsə YALNIZ o sətir geri qayıdır — fayl bütövlükdə itmir və
operator nəticə cədvəlində konkret sətri görüb düzəldir. Bu, sahibin tələbidir:
«500 nəfərlik siyahıda bir səhv sətrə görə hamısı ləğv olmasın».

Hər yaradılan hesab:

* ``User``  — ``username`` plan tərəfindən qurulur (``st.<kod>``), parol
  TƏSADÜFİ generasiya olunur və YALNIZ cavabda qayıdır (audit-ə YAZILMIR);
* ``UserProfile`` — FİN, ata adı, cins, doğum tarixi, telefon, tələbə kodu;
  ``access_state=ACTIVE``, ``password_change_required=True``,
  ``email_verified=False`` → ilk girişdə e-poçt + OTP + yeni parol tələb olunur
  (``FirstLoginPasswordMiddleware``);
* ``Membership`` — ``student`` rolu, aktiv, primary;
* ``StudentAcademicRecord`` — qrup + proqram + kurikulum + qəbul ili.

Audit: hər hesab üçün bir ``CREATE`` sətri, faylın sonunda isə bir YEKUN sətri.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
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

STUDENT_ROLE_NAME = "student"


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


def student_role(organization):
    role = organization.roles.filter(name=STUDENT_ROLE_NAME, is_active=True).first()
    if role is None:
        raise IntakeApplyError(
            "student_role_missing",
            pgettext(_CTX, "Bu təşkilatda aktiv «student» rolu yoxdur — əvvəlcə rol kataloqu qurulmalıdır."),
        )
    return role


def _ensure_curriculum(organization, program, admission_year):
    from apps.registrar.models import Curriculum

    curriculum, _created = Curriculum.objects.get_or_create(
        organization=organization,
        program=program,
        admission_year=admission_year,
        defaults={"name": "", "is_active": True},
    )
    return curriculum


def _create_user(plan, *, organization, role, actor, request):
    values = plan.values
    password = generate_initial_password()

    user = User.objects.create_user(
        username=values["username"],
        email=values["email"],
        password=password,
    )
    user.first_name = values["first_name"]
    user.last_name = values["last_name"]
    user.is_active = True
    user.save(update_fields=["first_name", "last_name", "is_active"])

    profile, _created = UserProfile.objects.get_or_create(user=user)
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = ProfileRole.STUDENT
    profile.access_state = UserProfile.AccessState.ACTIVE
    profile.fin = values["fin"]
    profile.patronymic = values["patronymic"]
    profile.gender = values["gender"]
    profile.birth_date = values["birth_date"]
    profile.phone = values["phone"]
    profile.institutional_identifier = values["student_code"] or None
    profile.student_group_number = plan.group_name
    profile.student_specialization = getattr(plan.targets["program"], "name", "") or ""
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
    user.profile = profile

    from apps.organizations.models import Membership

    Membership.objects.create(
        user=user,
        organization=organization,
        role=role,
        assigned_by=actor,
        is_primary=True,
        is_active=True,
    )

    program = plan.targets["program"]
    admission_year = plan.targets["admission_year"]
    curriculum = plan.targets.get("curriculum") or _ensure_curriculum(organization, program, admission_year)

    from apps.registrar.models import StudentAcademicRecord

    StudentAcademicRecord.objects.get_or_create(
        organization=organization,
        student=user,
        program=program,
        defaults={
            "curriculum": curriculum,
            "group": plan.targets["group"],
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

    log_action(
        action=AuditAction.CREATE,
        user=actor,
        organization=organization,
        obj=user,
        reason="student_intake_created",
        changes={
            # Parol QƏSDƏN yoxdur — audit jurnalı sirr saxlamır.
            "username": user.username,
            "fin": values["fin"],
            "group": plan.group_name,
            "program": str(program.pk),
            "admission_year": admission_year,
            "funding": values.get("funding_type", ""),
            "education_form": values.get("education_form", ""),
            "email_placeholder": values["email"].endswith(".invalid"),
        },
        request=request,
    )
    return user, password


def apply_plans(*, organization, plans, actor, request=None) -> dict:
    """Planları icra edir və nəticə sətirlərini qaytarır (parol yalnız burada)."""

    role = student_role(organization)
    results: list = []
    credentials: list = []
    created_count = 0
    failed_count = 0
    skipped_count = 0

    for plan in plans:
        if plan.status != "create":
            if plan.status == "skip":
                skipped_count += 1
            else:
                failed_count += 1
            results.append(plan.as_dict())
            continue
        try:
            with transaction.atomic():
                user, password = _create_user(
                    plan,
                    organization=organization,
                    role=role,
                    actor=actor,
                    request=request,
                )
        except Exception as exc:  # noqa: BLE001 — sətir izolyasiyası qəsdəndir
            failed_count += 1
            plan.fail(
                "apply_failed",
                pgettext(_CTX, "Sətir yazılmadı: %s") % (str(exc)[:180] or exc.__class__.__name__),
            )
            results.append(plan.as_dict())
            continue

        created_count += 1
        plan.status = "created"
        plan.code = "created"
        plan.message = pgettext(_CTX, "Hesab yaradıldı.")
        row = plan.as_dict()
        row["status"] = "created"
        results.append(row)
        credentials.append(
            {
                "username": user.username,
                "password": password,
                "full_name": plan.full_name,
                "fin": plan.fin,
                "group": plan.group_name,
            }
        )

    log_action(
        action=AuditAction.CREATE,
        user=actor,
        organization=organization,
        reason="student_intake_batch",
        resource_type="student_intake",
        resource_repr="student_intake_batch",
        changes={
            "created": created_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "total": len(plans),
        },
        request=request,
    )

    return {
        "rows": results,
        "credentials": credentials,
        "summary": {
            "total": len(plans),
            "created": created_count,
            "skip": skipped_count,
            "error": failed_count,
        },
    }


__all__ = [
    "STUDENT_ROLE_NAME",
    "IntakeApplyError",
    "apply_plans",
    "generate_initial_password",
    "student_role",
]
