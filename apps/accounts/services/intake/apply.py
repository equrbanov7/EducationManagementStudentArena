"""Tələbə idxalı — PLANLARIN TƏTBİQİ (hesab + üzvlük + akademik qeyd).

Atomiklik NAXIŞI: hər sətir ÖZ savepoint-indədir (``transaction.atomic()`` iç-içə
blok). Bir sətir çökürsə YALNIZ o sətir geri qayıdır — fayl bütövlükdə itmir və
operator nəticə cədvəlində konkret sətri görüb düzəldir. Bu, sahibin tələbidir:
«500 nəfərlik siyahıda bir səhv sətrə görə hamısı ləğv olmasın».

Hesabın ÖZÜ ``create.py::create_account``-da qurulur (ORTAQ nüvə — RİM mərkəzinin
«tək-tək hesab yarat» səthi də onu çağırır). Bu modul yalnız PLAN → NÜVƏ
tərcüməsini, sətir izolyasiyasını və faylın YEKUN audit sətrini saxlayır.

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

from django.db import transaction
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction

from .create import (
    KIND_STUDENT,
    STUDENT_ROLE_NAME,
    IntakeApplyError,
    create_account,
    generate_initial_password,
    student_role,
)

_CTX = "student_intake"


def _create_user(plan, *, organization, role, actor, request):
    """Bir planı ORTAQ nüvəyə tərcümə edir (tələbə yolu)."""

    return create_account(
        organization=organization,
        kind=KIND_STUDENT,
        values=plan.values,
        role=role,
        actor=actor,
        request=request,
        student_targets=plan.targets,
        group_name=plan.group_name,
        specialization=getattr(plan.targets["program"], "name", "") or "",
        audit_reason="student_intake_created",
    )


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
            from django.db import DataError

            detail = (
                pgettext(_CTX, "sahə uzunluğu həddi keçildi")
                if isinstance(exc, DataError)  # xam DB mesajı istifadəçiyə sızmasın (STUDENT-MGMT-02)
                else (str(exc)[:180] or exc.__class__.__name__)
            )
            plan.fail(
                "apply_failed",
                pgettext(_CTX, "Sətir yazılmadı: %s") % detail,
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
