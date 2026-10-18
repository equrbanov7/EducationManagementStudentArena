"""`document_seal.manage` açarını MÖVCUD tenantların rollarına verir (sahib 2026-10-18).

Yeni təşkilatlar açarı ``default_roles_university`` → ``apply_document_seal_grants`` ilə alır; bu miqrasiya
köhnə tenantları eyni vəziyyətə gətirir (``announcements/0003`` naxışı — açar app-ın öz miqrasiyasındadır,
``organizations`` miqrasiya zəncirinə paralel işlərlə toqquşma riski yaratmır):

* ``*`` və ya ``document_seal.*`` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* hər təşkilatın öz ``Role`` sətri ayrıca yenilənir (tenant izolyasiyası).

Rol siyahısı QƏSDƏN burada DONDURULUB (canlı şablon import edilmir).
Geri dönüş: açarı yalnız bu rollardan götürür.
"""

from django.db import migrations

_KEY = "document_seal.manage"
_COVERING = ("*", "document_seal.*")
_ROLES = ("ikt_rehber", "teaching_office_head", "teaching_office_staff", "student_services")


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
        ("verification", "0001_document_seal"),
        ("organizations", "0067_accounting_retake_permissions"),
    ]

    operations = [migrations.RunPython(forward, backward)]
