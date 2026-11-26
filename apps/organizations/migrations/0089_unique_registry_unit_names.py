"""Guard registry names without guessing which existing academic unit to rename."""

from django.db import migrations, models
from django.db.models.functions import Collate

# Whitespace stripped by the registry forms (str.strip).
_TRIM_CHARS = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)
_ACTIVE_REGISTRY = models.Q(is_active=True, unit_type__in=("faculty", "chair", "department"))
_FACULTY = models.Case(models.When(unit_type="faculty", then=1), default=0)
_NAME = Collate(
    models.Func(
        models.Func(
            models.Func("name", models.Value(_TRIM_CHARS), function="BTRIM"),
            function="NORMALIZE",
            output_field=models.TextField(),
        ),
        template='LOWER(%(expressions)s COLLATE "az-x-icu")',
    ),
    "C",
)


def check_existing_names(apps, schema_editor):
    schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    schema_editor.execute("LOCK TABLE organizations_orgunit IN SHARE ROW EXCLUSIVE MODE")
    units = (
        apps.get_model("organizations", "OrgUnit")
        .objects.using(schema_editor.connection.alias)
        .filter(_ACTIVE_REGISTRY)
        .annotate(registry_kind=_FACULTY, registry_name=_NAME)
    )
    groups = (
        units.order_by()
        .values("organization_id", "registry_kind", "registry_name")
        .annotate(total=models.Count("pk"))
        .filter(total__gt=1)
    )
    count = groups.count()
    if not count:
        return
    samples = []
    for group in groups.order_by("organization_id", "registry_kind", "registry_name")[:5]:
        rows = units.filter(
            organization_id=group["organization_id"],
            registry_kind=group["registry_kind"],
            registry_name=group["registry_name"],
        )
        ids = ", ".join(str(pk) for pk in rows.order_by("pk").values_list("pk", flat=True)[:5])
        samples.append(f"organization={group['organization_id']} total={group['total']} unit_ids=[{ids}]")
    raise RuntimeError(
        f"{count} active registry name collision group(s). Up to five groups and five unit IDs per group: "
        + " | ".join(samples)
        + ". Review these units, resolve their names or archive obsolete units, then retry. No unit was changed."
    )


class Migration(migrations.Migration):
    dependencies = [("organizations", "0088_credit_recognition_rim_staff")]
    operations = [
        migrations.RunPython(check_existing_names, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="orgunit",
            constraint=models.UniqueConstraint(
                "organization", _FACULTY, _NAME, condition=_ACTIVE_REGISTRY, name="orgunit_active_registry_name_uniq"
            ),
        ),
    ]
