"""Backfill ``course.create`` onto legacy ``teacher`` roles.

``default_roles.py`` already grants ``course.create`` to the ``teacher`` role,
but older roles created before that change may be missing it. Until now
``OrganizationMiddleware`` patched this at request time by unconditionally
adding ``course.create`` to any membership whose role name was ``teacher``.

This data migration moves that fix into the data layer (the single source of
truth for permissions), so the middleware special-case can be removed and RBAC
stays fully centralised.

Idempotent: roles that already grant ``course.create`` (directly, via
``course.*`` or via ``*``) are left untouched. Reverse is a no-op.
"""

from django.db import migrations

# A teacher role already grants course.create if any of these appear in its
# permissions list.
_ALREADY_GRANTS = {"course.create", "course.*", "*"}


def _forward(apps, schema_editor):
    Role = apps.get_model("organizations", "Role")
    # Roles are RLS-protected; bypass so every tenant's roles are backfilled.
    from core.rls import bypass_rls

    with bypass_rls():
        for role in Role.objects.filter(name="teacher").iterator():
            perms = role.permissions or []
            if not isinstance(perms, list):
                continue
            if _ALREADY_GRANTS.intersection(perms):
                continue
            role.permissions = [*perms, "course.create"]
            role.save(update_fields=["permissions"])


def _reverse(apps, schema_editor):
    # No-op: we do not strip course.create back off teacher roles.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0010_seed_university_tutor_role"),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
