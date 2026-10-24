"""Mövcud tenantlar: RİM əməkdaşı (`rim_staff`) + qəyyum (`trustee`) → `application.view_all` — 2026-10-24.

«Müraciətlərim → Bütün müraciətlər» tabı: RİM sistemə gələn BÜTÜN müraciətləri görür
(YALNIZ OXU — əməl və daxili qeyd vermir, bax ``services.access.can_oversee``). Yeni
təşkilatlar açarı rol şablonundan alır (``default_roles_rim`` / ``default_roles_oversight`` —
qəyyum «hər oxu açarını» daşıyır, sahib 2026-10-17); burada mövcud rol sətirlərinə yazılır.
`ikt_rehber` (`*`) və `application.manage` daşıyanlar onsuz da əhatəlidir — toxunulmur.

İdempotent: açar, `application.*` və ya `*` varsa sətir dəyişmir. Geri dönüş açarı götürür.
"""

from django.db import migrations

_KEY = "application.view_all"
_ROLE_NAMES = ("rim_staff", "trustee")


def _covered(permissions):
    return _KEY in permissions or "application.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLE_NAMES).iterator():
        permissions = list(role.permissions or [])
        if _covered(permissions):
            continue
        permissions.append(_KEY)
        role.permissions = permissions
        role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    for role in Role.objects.filter(name__in=_ROLE_NAMES).iterator():
        permissions = [entry for entry in (role.permissions or []) if entry != _KEY]
        if permissions != list(role.permissions or []):
            role.permissions = permissions
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0005_reopened_event_kind"),
        # Rol sətirlərini yazan son miqrasiyalardan SONRA (rol auditi 0061/0063 daxil).
        ("organizations", "0071_grade_event_trial_purge_exception"),
    ]

    operations = [migrations.RunPython(forward, backward)]
