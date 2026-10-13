"""2026-10-13 (gecə) — vaxtla məhdud zal nəzarətçisi növbəsi (``InvigilatorDuty``).

Additiv: yeni cədvəl, mövcud sətirlərə toxunulmur. Cədvəldə birbaşa NOT NULL
``organization_id`` var — tenant siyasəti 0073 (``exams_finalattemptdevice``) ilə eyni
formadadır: ``ENABLE`` + ``FORCE`` + ``USING``/``WITH CHECK``; qeyri-PostgreSQL → no-op;
geri qaytarıla bilir.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "exams_invigilatorduty"
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
        ("exams", "0074_questionsubmission_registry_groups"),
        ("organizations", "0060_board_chair_rector_primary"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InvigilatorDuty",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("starts_at", models.DateTimeField(verbose_name="starts_at")),
                ("ends_at", models.DateTimeField(verbose_name="ends_at")),
                ("note", models.CharField(blank=True, max_length=200, verbose_name="note")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_by",
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
                        verbose_name="organization",
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duties",
                        to="exams.examroom",
                        verbose_name="room",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invigilator_duties",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "singular",
                "verbose_name_plural": "plural",
                "ordering": ["starts_at", "id"],
                "indexes": [
                    models.Index(fields=["user", "starts_at"], name="invduty_user_start_idx"),
                    models.Index(fields=["room", "starts_at"], name="invduty_room_start_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("ends_at__gt", models.F("starts_at"))),
                        name="invigilator_duty_end_after_start",
                    )
                ],
            },
        ),
        migrations.RunPython(_apply_rls, _revert_rls),
    ]
