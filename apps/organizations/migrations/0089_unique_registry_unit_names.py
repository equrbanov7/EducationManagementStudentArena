"""Guard registry names without guessing which existing academic unit to rename."""

from django.db import migrations, models
from django.db.models.functions import Collate

from apps.organizations import registry_name_ddl_v1

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


_CONSTRAINT = models.UniqueConstraint(
    "organization", _FACULTY, _NAME, condition=_ACTIVE_REGISTRY, name="orgunit_active_registry_name_uniq"
)


def install(apps, schema_editor):
    model = apps.get_model("organizations", "OrgUnit")
    native = _CONSTRAINT.create_sql(model, schema_editor)
    schema_editor.execute(registry_name_ddl_v1.create_sql(native, _TRIM_CHARS), params=None)


def uninstall(apps, schema_editor):
    model = apps.get_model("organizations", "OrgUnit")
    native = _CONSTRAINT.remove_sql(model, schema_editor)
    schema_editor.execute(registry_name_ddl_v1.remove_sql(native), params=None)


class Migration(migrations.Migration):
    dependencies = [("organizations", "0088_credit_recognition_rim_staff")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(install, uninstall)],
            state_operations=[migrations.AddConstraint(model_name="orgunit", constraint=_CONSTRAINT)],
        ),
    ]
