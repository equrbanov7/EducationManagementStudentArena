"""Tyutor = proqram koordinatoru — YEKUN açar dəsti eyni (sahib 2026-10-14: «tyutor və proqram koordinatoru
eyni roldur demək olar, hər 2-si eyni şeyləri edə bilsin»).

``0050_tutor_coordinator_parity`` yalnız BAZA dəstini bərabərləşdirmişdi; sonrakı qrant modulları (stage2,
stage4, TXM, tədris şöbəsi, müraciət) açarları yalnız koordinatora əkirdi. Şablon tərəfi:
``default_roles_role_audit.ROLE_PARITY_GROUPS`` / ``apply_role_parity``. Bu miqrasiya mövcud tenantları eyni
vəziyyətə gətirir:

* hər iki rola ``_UNION`` açarları (şablonun yekun birləşməsi, bura KÖÇÜRÜLÜB — sonradan dəyişən modula
  söykənmir). Açar, onun ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa TOXUNULMUR → idempotent;
  ``level`` / ``name`` / ``display_name`` / ``scope_type`` dəyişmir.
* «Proqram koordinatoru» müraciət şöbəsinin (``ApplicationUnit.code = "koordinator"``) emalçı rollarına
  ``tutor`` əlavə olunur — ``application.handle`` açarı səthi açır, konkret müraciət isə şöbənin
  ``handler_role_names``-indən asılıdır (``apps/applications/services/access.py``). Tenant siyahını
  dəyişibsə (koordinator yoxdursa) toxunulmur.

Geri dönüş: tyutordan yalnız bu miqrasiyanın ona verdiyi koordinator açarları (``_TUTOR_ADDED``) götürülür,
şöbə siyahısından ``tutor`` çıxarılır. Koordinatora heç nə əlavə edilmədiyi üçün (birləşmə onda artıq var idi)
geri dönüş ona toxunmur.
"""

from django.db import migrations

_ROLES = ("tutor", "program_coordinator")

#: Şablonun 2026-10-14 yekun birləşməsi (22 açar).
_UNION = (
    "analytics.view_unit",
    "appeal.create",
    "application.create",
    "application.handle",
    "catalog.view",
    "course.view",
    "exam.view",
    "group.manage",
    "journal.roster",
    "member.view",
    "people.manage_academic",
    "people.view_students",
    "plan.view",
    "schedule.manage",
    "schedule.view",
    "semester.view",
    "student.assign_group",
    "student.registry_view",
    "unit.group_manage",
    "unit.view",
    "workload.review",
    "workload.view",
)

#: Əvvəl YALNIZ koordinatorda olan açarlar — geri dönüşdə tyutordan götürülür.
_TUTOR_ADDED = (
    "application.handle",
    "catalog.view",
    "plan.view",
    "semester.view",
    "student.assign_group",
    "student.registry_view",
    "unit.group_manage",
    "workload.review",
    "workload.view",
)

_APPLICATION_UNIT_CODE = "koordinator"
_COORDINATOR = "program_coordinator"
_TUTOR = "tutor"


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        before = list(role.permissions or [])
        if "*" in before:
            continue
        permissions = list(before)
        for key in _UNION:
            if not _covered(permissions, key):
                permissions.append(key)
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_APPLICATION_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _COORDINATOR in names and _TUTOR not in names:
            unit.handler_role_names = [*names, _TUTOR]
            unit.save(update_fields=["handler_role_names"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_TUTOR).iterator():
        before = list(role.permissions or [])
        permissions = [key for key in before if key not in _TUTOR_ADDED]
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_APPLICATION_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _TUTOR in names:
            unit.handler_role_names = [name for name in names if name != _TUTOR]
            unit.save(update_fields=["handler_role_names"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0063_role_audit_followup"),
        ("applications", "0005_reopened_event_kind"),
    ]

    operations = [migrations.RunPython(forward, backward)]
