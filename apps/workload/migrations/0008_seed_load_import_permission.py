"""`workload.load_import` açarını MÖVCUD tenantların rollarına verir (sahib 2026-10-23).

Yeni təşkilatlar açarı ``default_roles_university`` → ``apply_workload_load_grants`` ilə alır; bu miqrasiya köhnə
tenantları eyni vəziyyətə gətirir (``verification/0002`` naxışı):

* ``*`` və ya ``workload.*`` daşıyan rola TOXUNULMUR (onsuz da əhatəlidir);
* açar artıq varsa heç nə dəyişmir → İDEMPOTENTDİR;
* hər təşkilatın öz ``Role`` sətri ayrıca yenilənir (tenant izolyasiyası).

Rol siyahısı QƏSDƏN burada DONDURULUB. Geri dönüş: açarı yalnız bu rollardan götürür.
"""

from django.db import migrations

_KEY = "workload.load_import"
_COVERING = ("*", "workload.*")
_ROLES = ("ikt_rehber", "teaching_office_head", "teaching_office_staff")


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
        ("workload", "0007_amendment_document_max_length"),
        ("organizations", "0071_grade_event_trial_purge_exception"),
    ]

    operations = [migrations.RunPython(forward, backward)]
