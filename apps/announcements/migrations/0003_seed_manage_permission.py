"""`announcement.manage` açarını MÖVCUD tenantların rollarına verir (sahib, 2026-10-06).

Yeni təşkilatlar açarı ``default_roles_university`` → ``apply_announcement_grants`` ilə
alır; bu miqrasiya köhnə tenantları eyni vəziyyətə gətirir. ``organizations/0056`` ilə
EYNİ naxış:

* ``*`` və ya ``announcement.*`` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* hər təşkilatın öz ``Role`` sətri ayrıca yenilənir (tenant izolyasiyası).

Rol siyahısı QƏSDƏN burada DONDURULUB (canlı şablon import edilmir).
Geri dönüş: açarı yalnız bu rollardan götürür.
"""

from django.db import migrations

_KEY = "announcement.manage"
_COVERING = ("*", "announcement.*")
_ROLES = ("vice_rector", "dean", "vice_dean", "chair_head", "teaching_office_head", "student_services")


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        if _KEY in permissions or any(entry in permissions for entry in _COVERING):
            continue
        role.permissions = permissions + [_KEY]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    for role in Role.objects.filter(name__in=_ROLES).iterator():
        permissions = list(role.permissions or [])
        if _KEY not in permissions:
            continue
        role.permissions = [entry for entry in permissions if entry != _KEY]
        role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("announcements", "0002_rls_announcements"),
        ("organizations", "0057_capacity_drop_unused_indexes"),
    ]

    operations = [migrations.RunPython(forward, backward)]
