"""Preserve pre-existing grants when removing this migration."""

from django.db import migrations

KEY = "faq.video.manage"
MARK = "_migration_0092_faq_editors"


def apply_grants(apps, schema_editor, reverse=False):
    alias = schema_editor.connection.alias
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    organizations = apps.get_model("organizations", "Organization").objects.using(alias)
    roles = apps.get_model("organizations", "Role").objects.using(alias)
    for org in organizations.filter(org_type="university").iterator():
        settings = dict(org.settings or {})
        if reverse:
            ids = set(settings.pop(MARK, []))
            for role in roles.filter(organization_id=org.pk, pk__in=ids):
                role.permissions = [key for key in (role.permissions or []) if key != KEY]
                role.save(using=alias, update_fields=["permissions"])
            if not ids:
                continue
        else:
            ids = set(settings.get(MARK, []))
            for role in roles.filter(organization_id=org.pk, name__in=["ikt_rehber", "rim_staff"], is_system=True):
                if KEY not in (role.permissions or []):
                    role.permissions = [*(role.permissions or []), KEY]
                    role.save(using=alias, update_fields=["permissions"])
                    ids.add(str(role.pk))
            if not ids:
                continue
            settings[MARK] = sorted(ids)
        organizations.filter(pk=org.pk).update(settings=settings)


def reverse_grants(apps, schema_editor):
    apply_grants(apps, schema_editor, reverse=True)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0091_dean_office_student_movement")]
    operations = [migrations.RunPython(apply_grants, reverse_grants)]
