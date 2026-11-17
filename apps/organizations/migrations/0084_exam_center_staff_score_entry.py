"""İmtahan Mərkəzinin işçisi (``exam_center_staff``) «İmtahan balının daxil edilməsi»ndə işləyir — sahib 2026-11-18.

Sahib: «RİM rəhbəri, İmtahan Mərkəzinin rəhbəri və İmtahan Mərkəzinin işçisi burada işləyə bilməlidir və əlavə olaraq
apellyasiya xanasını da yaza bilməlidir». Mövcud tenantlarda ``exam_center_staff`` rollarına ``final_score.entry``
açarı əlavə olunur (açar, ``final_score.*`` və ya ``*`` artıq varsa toxunulmur). Apellyasiya icazəsi rol adından
gəlir (``registrar.exam_score_period_lock.change_permissions``). Geri alma yalnız bu açarı çıxarır.
"""

from django.db import migrations

_ROLE = "exam_center_staff"
_KEY = "final_score.entry"


def _roles(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    return apps.get_model("organizations", "Role").objects.filter(name=_ROLE)


def _covered(permissions) -> bool:
    return _KEY in permissions or "final_score.*" in permissions or "*" in permissions


def forward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        if not _covered(permissions):
            role.permissions = permissions + [_KEY]
            role.save(update_fields=["permissions"])


def backward(apps, schema_editor):
    for role in _roles(apps, schema_editor).iterator():
        permissions = list(role.permissions or [])
        if _KEY in permissions:
            role.permissions = [key for key in permissions if key != _KEY]
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("organizations", "0083_lab_assistant_chair_applications")]
    operations = [migrations.RunPython(forward, backward)]
