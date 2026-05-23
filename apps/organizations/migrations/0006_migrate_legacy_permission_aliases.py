"""Migrate legacy permission-prefix aliases to the canonical names (FAZA 10).

Historically the codebase used two spellings for several permission prefixes
(``grading.*`` vs ``grade.*``, ``courses.*`` vs ``course.*``,
``exams.*`` vs ``exam.*``, ``members.*`` vs ``member.*``) plus an unmapped
``structure.*`` that never matched the real ``unit.*`` permissions.

``default_roles.py`` now emits only the canonical names. This data migration
rewrites any existing ``Role.permissions`` JSON arrays in the database so the
legacy spellings disappear, allowing ``PERMISSION_PREFIX_ALIASES`` to be removed
in a later release.

Idempotent: re-running it changes nothing once data is already canonical.
Reverse is a no-op (canonical names are a strict superset semantically).
"""

from django.db import migrations

# Legacy prefix -> canonical prefix. Applied to the dotted permission strings
# stored in Role.permissions (e.g. "grading.view" -> "grade.view",
# "courses.*" -> "course.*").
_PREFIX_REWRITES = {
    "grading.": "grade.",
    "courses.": "course.",
    "exams.": "exam.",
    "members.": "member.",
    "structure.": "unit.",
}


def _canonicalize(permission: str) -> str:
    for legacy, canonical in _PREFIX_REWRITES.items():
        if permission.startswith(legacy):
            return canonical + permission[len(legacy):]
    return permission


def _forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    # Roles are RLS-protected; bypass so every tenant's roles are rewritten.
    from core.rls import bypass_rls

    with bypass_rls():
        for role in Role.objects.all().iterator():
            perms = role.permissions or []
            if not isinstance(perms, list):
                continue
            new_perms = []
            seen = set()
            for perm in perms:
                if not isinstance(perm, str):
                    new_perms.append(perm)
                    continue
                canonical = _canonicalize(perm)
                if canonical not in seen:
                    new_perms.append(canonical)
                    seen.add(canonical)
            if new_perms != perms:
                role.permissions = new_perms
                role.save(update_fields=["permissions"])


def _reverse(apps, schema_editor):
    # No-op: we do not reintroduce legacy spellings.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0005_notification_org_fk_rls"),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
