"""`transcript.issue` açarını MÖVCUD tenantların rollarına verir (sahib 2026-10-19).

Yeni təşkilatlar açarı ``default_roles_university`` → ``apply_transcript_grants`` ilə alır; bu miqrasiya
köhnə tenantları eyni vəziyyətə gətirir (``verification/0002`` naxışı — açar app-ın öz miqrasiyasındadır,
``organizations`` miqrasiya zəncirinə paralel işlərlə toqquşma riski yaratmır):

* ``*`` və ya ``transcript.*`` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* hər təşkilatın öz ``Role`` sətri ayrıca yenilənir (tenant izolyasiyası).

Dekan / dekan müavini UNIT roludur: açar onlara yalnız öz fakültəsinin alt-ağacında əhatə verir
(``Membership.scope_unit``) — miqrasiya əhatəni dəyişmir.

Rol siyahısı QƏSDƏN burada DONDURULUB (canlı şablon import edilmir).
Geri dönüş: açarı yalnız bu rollardan götürür.
"""

from django.db import migrations

_KEY = "transcript.issue"
_COVERING = ("*", "transcript.*")
_ROLES = ("teaching_office_head", "student_services", "ikt_rehber", "dean", "vice_dean")


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
        ("verification", "0003_doc_type_enrollment_certificate"),
        ("organizations", "0069_hr_contract_permissions"),
    ]

    operations = [migrations.RunPython(forward, backward)]
