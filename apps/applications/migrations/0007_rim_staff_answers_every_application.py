"""Mövcud tenantlar: RİM əməkdaşı RİM şöbəsinin emalçısıdır + `application.handle` — 2026-10-26.

Sahib: «RİM hər müraciəti cavablandıra bilsin». Əvvəl RİM şöbəsini (`rim`) yalnız rəhbər
(`ikt_rehber`) emal edirdi; əməkdaş (`rim_staff`) «Bütün müraciətlər»i YALNIZ OXUYURDU — hətta
«Texniki problem» müraciətlərinə də cavab verə bilmirdi. Kod tərəfi:
``services.access.is_universal_responder`` (RİM şöbəsinin emalçısı hər açıq müraciətə cavab verir).

İki iş, hər ikisi İDEMPOTENT:

1. `rim` kodlu ``ApplicationUnit`` sətirlərinin ``handler_role_names``-inə `rim_staff` əlavə olunur
   (tenant siyahını redaktə edibsə digər adlara toxunulmur; şöbə yoxdursa heç nə edilmir).
2. `rim_staff` rol sətirlərinə `application.handle` (açar, `application.*` və ya `*` varsa toxunulmur).

Geri dönüş hər ikisini götürür.
"""

from django.db import migrations

_UNIT_CODE = "rim"
_ROLE_NAME = "rim_staff"
_KEY = "application.handle"


def _covered(permissions):
    return _KEY in permissions or "application.*" in permissions or "*" in permissions


def _bypass_rls(schema_editor):
    # Müraciət cədvəllərində FORCE RLS var (0002) — tenant konteksti olmayan miqrasiya bütün
    # təşkilatların şöbə sətirlərini görsün deyə (organizations 0003 naxışı).
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")


def forward(apps, schema_editor):
    _bypass_rls(schema_editor)
    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _ROLE_NAME not in names:
            unit.handler_role_names = [*names, _ROLE_NAME]
            unit.save(update_fields=["handler_role_names"])

    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = list(role.permissions or [])
        if _covered(permissions):
            continue
        role.permissions = [*permissions, _KEY]
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    _bypass_rls(schema_editor)
    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [name for name in (unit.handler_role_names or []) if name != _ROLE_NAME]
        if names != list(unit.handler_role_names or []):
            unit.handler_role_names = names
            unit.save(update_fields=["handler_role_names"])

    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE_NAME).iterator():
        permissions = [entry for entry in (role.permissions or []) if entry != _KEY]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0006_grant_view_all_to_rim_staff"),
        ("organizations", "0073_grade_event_attempt_purge_exception"),
    ]

    operations = [migrations.RunPython(forward, backward)]
