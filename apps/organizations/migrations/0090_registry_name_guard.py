"""Teach model validation and future schema changes about the 0089 compatibility guard."""

from importlib import import_module

from django.db import migrations

from apps.organizations.name_matching import RegistryNameConstraint

# A previously applied 0089 already has the native unique index. Keep its DDL
# intact and retain the exact frozen expression from that migration.
_previous = import_module("apps.organizations.migrations.0089_unique_registry_unit_names")._CONSTRAINT


class Migration(migrations.Migration):
    dependencies = [("organizations", "0089_unique_registry_unit_names")]
    operations = [
        migrations.AlterConstraint(
            model_name="orgunit",
            name=_previous.name,
            constraint=RegistryNameConstraint(
                *_previous.expressions, name=_previous.name, condition=_previous.condition
            ),
        ),
    ]
