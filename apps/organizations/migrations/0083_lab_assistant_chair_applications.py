"""Laborant kafedra müraciətlərini görür və cavablandırır (sahib 2026-11-17: «müraciəti laborant da görsün, əsas
laborantlar cavab verir»).

* ``lab_assistant`` roluna ``application.handle`` açarı (səthi açır; açar, ``application.*`` və ya ``*`` artıq
  varsa toxunulmur → idempotent).
* «Kafedra müdirliyi» şöbəsinin (``ApplicationUnit.code = "kafedra"``) emalçı rollarına ``lab_assistant`` əlavə
  olunur. Rol UNIT əhatəlidir — laborant yalnız ÖZ kafedrasına (üzvlüyün ``scope_unit`` alt-ağacı) yönləndirilən
  müraciəti görür (``apps/applications/services/access.py``). Tenant siyahıdan ``chair_head``-i çıxarıbsa
  toxunulmur.

Geri dönüş: açar və rol adı geri götürülür.
"""

from django.db import migrations

_ROLE = "lab_assistant"
_PERMISSION = "application.handle"
_UNIT_CODE = "kafedra"
_CHAIR_HEAD = "chair_head"


def _covered(permissions, key):
    return key in permissions or f"{key.split('.', 1)[0]}.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        if not _covered(permissions, _PERMISSION):
            role.permissions = [*permissions, _PERMISSION]
            role.save(update_fields=["permissions"])

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _CHAIR_HEAD in names and _ROLE not in names:
            unit.handler_role_names = [*names, _ROLE]
            unit.save(update_fields=["handler_role_names"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name=_ROLE).iterator():
        permissions = list(role.permissions or [])
        if _PERMISSION in permissions:
            role.permissions = [key for key in permissions if key != _PERMISSION]
            role.save(update_fields=["permissions"])

    ApplicationUnit = apps.get_model("applications", "ApplicationUnit")
    for unit in ApplicationUnit.objects.filter(code=_UNIT_CODE).iterator():
        names = [str(name) for name in (unit.handler_role_names or []) if name]
        if _ROLE in names:
            unit.handler_role_names = [name for name in names if name != _ROLE]
            unit.save(update_fields=["handler_role_names"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0082_rim_staff_daily_access"),
        ("applications", "0013_attachments_50mb"),
    ]

    operations = [migrations.RunPython(forward, backward)]
