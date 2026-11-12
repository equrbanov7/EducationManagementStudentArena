"""RİM əməkdaşının (``rim_staff``) gündəlik iş açarları — sahib 2026-11-12.

Sahib: «yük bölgüsü, fənn təhvili, qruplar, RİM mərkəzi … parol sıfırlanması. Gündəlik olaraq ən çox lazım olan nə
varsa hamısına access-i olsun. Gün əlavə etmək, çıxarmaq, silmək və s., alt qrup əlavə etmək». Şablon:
``permissions_rim_staff.RIM_STAFF_DAILY_PERMISSIONS`` (siyahı burada SƏTİR-SƏTİR köçürülüb — miqrasiya tətbiq
kodundan asılı qalmasın). İdempotent: açar, ``<prefiks>.*`` və ya ``*`` artıq varsa toxunulmur. Geri alma yalnız
bu miqrasiyanın əlavə etdiyi açarları silir (prod-da redaktordan əvvəlcədən verilmiş olsa belə — şablon vəziyyəti).
"""

from django.db import migrations

_ROLE = "rim_staff"
_KEYS = (
    "user.search",
    "user.credentials",
    "user.edit",
    "user.block",
    "account.password_reset",
    "workload.distribute",
    "workload.manage",
    "workload.load_import",
    "journal.reassign",
    "journal.view",
    "journal.roster",
    "journal.direct_edit",
    "unit.group_manage",
    "student.registry_view",
    "student.movement",
    "student.assign_group",
    "retake.manage",
    "schedule.manage",
)


def _roles(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    return apps.get_model("organizations", "Role").objects.filter(name=_ROLE)


def _covered(permissions, key) -> bool:
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        missing = [key for key in _KEYS if not _covered(permissions, key)]
        if missing:
            role.permissions = permissions + missing
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        kept = [key for key in permissions if key not in _KEYS]
        if kept != permissions:
            role.permissions = kept
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0081_chair_head_journal_view")]
    operations = [migrations.RunPython(forward, backward)]
