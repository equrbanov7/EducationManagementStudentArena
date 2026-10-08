"""Təhlükəsizlik dizaynı 2026-10-08 — final cəhdinin cihaz bağlantısı (``FinalAttemptDevice``).

Cədvəldə birbaşa NOT NULL ``organization_id`` var — tenant siyasəti organizations 0016
(``exams_examroomcomputer``) ilə eyni formadadır: ``ENABLE`` + ``FORCE`` + ``USING``/``WITH
CHECK``; qeyri-PostgreSQL → no-op; geri qaytarıla bilir.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

_TABLE = "exams_finalattemptdevice"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_ORG_EXPR = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING ({_BYPASS_EXPR} OR {_ORG_EXPR})
    WITH CHECK ({_BYPASS_EXPR} OR {_ORG_EXPR});
"""

_REVERSE_SQL = f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


def _apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0072_answer_drop_prefix_redundant_indexes"),
        ("organizations", "0057_capacity_drop_unused_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinalAttemptDevice",
            fields=[
                (
                    "attempt",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="device_binding",
                        serialize=False,
                        to="exams.examattempt",
                    ),
                ),
                ("token_hash", models.CharField(max_length=64)),
                ("bound_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("change_approved_at", models.DateTimeField(blank=True, null=True)),
                ("rebind_count", models.PositiveSmallIntegerField(default=0)),
                (
                    "change_approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
            },
        ),
        migrations.RunPython(_apply_rls, _revert_rls),
    ]
