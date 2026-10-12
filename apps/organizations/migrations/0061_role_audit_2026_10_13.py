"""Rol auditi 2026-10-13 — mövcud tenantların rol sətirlərini şablonla eyni vəziyyətə gətirir.

Mənbə: ``apps/organizations/default_roles_role_audit.py`` (xəritələr bura KÖÇÜRÜLÜB — miqrasiya sonradan
dəyişən modula söykənməsin). Hesabat: ``docs/audits/2026-10-13-claude/ROL_AUDITI.md``.

* Verilən açar: açar, onun ``<prefiks>.*`` wildcard-ı və ya ``*`` artıq varsa TOXUNULMUR → idempotent.
* Alınan açar (``hr``: ``user.import``, ``people.view_students``) — Tələbə xidmətlərinə keçib.
* Ölü açarlar (``grade.publish``, ``assignment.edit``) bütün rollardan silinir (heç nəyi qapılamırdı).
* ``member`` → ``application.create`` (artıq «onboarding» sayılmır — vəzifəsi xəritələnməmiş ofis işçisi).

Geri dönüş: verilən açarları həmin rol adlarından götürür (əvvəldən olub-olmadığı bilinmir — 0058 ilə eyni
qəbul), HR-a alınanları qaytarır; ölü açarlar geri yazılmır. Tenant izolyasiyası: hər ``Role`` ayrıca.
"""

from django.db import migrations

_GRANTS = {
    "exam_center_head": ("exam_center.decide", "student.records_view"),
    "exam_center": ("exam_center.decide", "student.records_view"),
    "exam_center_staff": ("people.view_students", "people.view_teachers", "student.records_view"),
    "hr": ("user.import_staff",),
    "assistant": (
        "grade.input",
        "syllabus.view",
        "syllabus.edit",
        "syllabus.submit",
        "exam.create",
        "exam.edit",
        "exam.host",
    ),
    "teaching_office_head": (
        "student.records_view",
        "journal.view",
        "journal.lessons_unit",
        "schedule.view",
        "student.registry_view",
    ),
    "teaching_office_staff": ("student.records_view", "journal.view", "journal.lessons_unit", "schedule.view"),
    "vice_rector": ("schedule.view", "student.records_view"),
    "dean": ("student.records_view",),
    "vice_dean": ("student.records_view",),
    "chair_head": ("student.records_view",),
    "rim_staff": ("student.records_view",),
    "member": ("application.create",),
}
_REVOKES = {"hr": ("user.import", "people.view_students")}
_DEAD = ("grade.publish", "assignment.edit")


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.all().iterator():
        before = list(role.permissions or [])
        permissions = [key for key in before if key not in _DEAD]
        for key in _REVOKES.get(role.name, ()):
            permissions = [entry for entry in permissions if entry != key]
        for key in _GRANTS.get(role.name, ()):
            if not _covered(permissions, key):
                permissions.append(key)
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    names = set(_GRANTS) | set(_REVOKES)
    for role in Role.objects.filter(name__in=names).iterator():
        before = list(role.permissions or [])
        granted = set(_GRANTS.get(role.name, ()))
        permissions = [key for key in before if key not in granted]
        for key in _REVOKES.get(role.name, ()):
            if key not in permissions:
                permissions.append(key)
        if permissions != before:
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [("organizations", "0060_board_chair_rector_primary")]

    operations = [migrations.RunPython(forward, backward)]
