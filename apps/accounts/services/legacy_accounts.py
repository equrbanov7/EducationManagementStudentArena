"""Köhnə sistem DELTA köçürməsi üçün hesab qatı (``apps.legacy_import.services.delta`` çağırır).

Yeni hesab YALNIZ mövcud rəsmi yollarla yaranır — burada yeni qayda yoxdur:

* müəllim — «Dərs yükü faylı»nın ad tutuşdurması (``teacher_roster.chair_teachers.ChairTeacherResolver``):
  tapılmasa FİN-siz hesab (sahib 2026-10-11), parolsuz, ``roster.<ad>@placeholder.invalid``;
* tələbə — RİM-in ``intake.create.create_account`` yolu (``User`` + ``UserProfile`` + ``Membership`` +
  ``StudentAcademicRecord`` + audit), ``legacy.<ad>@placeholder.invalid``; parol QOYULMUR
  (``set_unusable_password``) — birdəfəlik parolu RİM «Parol təyin et» ilə verir, ilk girişdə öz parolu
  və real e-poçtu məcburidir. ``institutional_identifier`` = legacy ``students.id`` (cutover qaydası).

Heç bir e-poçt / bildiriş göndərilmir.
"""

from __future__ import annotations

LEGACY_STUDENT_EMAIL_PREFIX = "legacy"


def chair_teacher_resolver(organization, chair, *, actor_user, apply: bool, tag: str = ""):
    from .teacher_roster.chair_teachers import ChairTeacherResolver

    return ChairTeacherResolver(organization, chair, actor_user=actor_user, apply=apply, tag=tag)


def teacher_resolution_statuses() -> tuple[frozenset, frozenset]:
    """``(tapılmış statuslar, yaradılmış statuslar)``."""

    from .teacher_roster.chair_teachers import RESOLVED, TEACHER_CREATED, TEACHER_CREATED_NAMESAKE

    return frozenset(RESOLVED), frozenset({TEACHER_CREATED, TEACHER_CREATED_NAMESAKE})


def create_legacy_student(
    *,
    organization,
    actor,
    first_name: str,
    last_name: str,
    patronymic: str,
    fin,
    gender: str,
    birth_date,
    legacy_code: str,
    group,
    program,
    admission_year: int,
    education_form: str = "full_time",
    funding_type: str = "paid",
    tag: str = "",
):
    """Tələbə hesabı (parolsuz). Qaytarır: ``User``."""

    from ..identity import PLACEHOLDER_EMAIL_DOMAIN
    from .intake.create import create_account, student_role
    from .staff_roster import username_seed
    from .teacher_roster.create import claim_name_username

    username = claim_name_username(username_seed(f"{last_name} {first_name}"))
    user, _password = create_account(
        organization=organization,
        kind="student",
        values={
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": f"{LEGACY_STUDENT_EMAIL_PREFIX}.{username}@{PLACEHOLDER_EMAIL_DOMAIN}",
            "fin": fin or None,
            "patronymic": patronymic,
            "gender": gender,
            "birth_date": birth_date,
            "phone": "",
            "student_code": legacy_code,
            "education_form": education_form,
            "funding_type": funding_type,
        },
        role=student_role(organization),
        actor=actor,
        student_targets={"group": group, "program": program, "admission_year": admission_year},
        group_name=group.name,
        audit_reason=f"legacy_delta_student_created {tag}".strip(),
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])
    return user


__all__ = [
    "LEGACY_STUDENT_EMAIL_PREFIX",
    "chair_teacher_resolver",
    "create_legacy_student",
    "teacher_resolution_statuses",
]
