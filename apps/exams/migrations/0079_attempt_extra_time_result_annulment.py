"""Sahib 2026-11-17 — fərdi əlavə vaxt + ləğv edilən nəticənin bərpası.

* ``ExamAttempt.extra_time_seconds`` — sabit defoltlu sütun (PostgreSQL 11+: cədvəl yenidən yazılmır).
* ``ExamResultAnnulment`` — ləğv/bərpa qeydi. Cədvəldə birbaşa NOT NULL ``organization_id`` var — tenant
  siyasəti 0075 (``exams_invigilatorduty``) ilə eyni formadadır (``ENABLE`` + ``FORCE`` + ``USING``/``WITH CHECK``).
* PR #366-dan bəri ``SupervisionIncident(teacher_action="result_annulled")`` kimi yazılmış ləğvlər yeni
  cədvələ köçürülür (cəhd başına ən sonuncu; hadisə sətri tarixçə üçün qalır). Geri qaytarıla bilir.
"""

import apps.exams.domain.result_annulment
import apps.exams.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


_TABLE = "exams_examresultannulment"
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

_REASON_KEYS = {"removed", "cheating", "other"}


def _apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


def _copy_incident_annulments(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    incident_model = apps.get_model("exams", "SupervisionIncident")
    annulment_model = apps.get_model("exams", "ExamResultAnnulment")
    latest = {}
    for incident in incident_model.objects.filter(teacher_action="result_annulled").order_by("timestamp", "id"):
        latest[incident.attempt_id] = incident
    for attempt_id, incident in latest.items():
        meta = incident.metadata if isinstance(incident.metadata, dict) else {}
        reason_key = meta.get("reason_key") if meta.get("reason_key") in _REASON_KEYS else "other"
        row = annulment_model.objects.create(
            organization_id=incident.organization_id,
            attempt_id=attempt_id,
            reason_key=reason_key,
            note=str(meta.get("note") or "")[:1000],
            incident_date=timezone.localtime(incident.timestamp).date() if incident.timestamp else None,
            previous_supervision_status=str(meta.get("previous_status") or "")[:20],
            annulled_by_id=meta.get("teacher_id") if isinstance(meta.get("teacher_id"), int) else None,
        )
        annulment_model.objects.filter(pk=row.pk).update(annulled_at=incident.timestamp)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0078_examquestion_replaces"),
        ("organizations", "0082_rim_staff_daily_access"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="examattempt",
            name="extra_time_seconds",
            field=models.PositiveIntegerField(db_default=0, default=0),
        ),
        migrations.CreateModel(
            name="ExamResultAnnulment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason_key", models.CharField(max_length=20)),
                ("note", models.TextField(max_length=1000)),
                ("incident_date", models.DateField(blank=True, null=True)),
                (
                    "document",
                    models.FileField(
                        blank=True,
                        max_length=255,
                        upload_to=apps.exams.domain.result_annulment.annul_document_path,
                        validators=[apps.exams.validators.validate_file_size],
                    ),
                ),
                ("previous_supervision_status", models.CharField(blank=True, default="", max_length=20)),
                ("annulled_at", models.DateTimeField(auto_now_add=True)),
                ("restored_at", models.DateTimeField(blank=True, null=True)),
                ("restore_note", models.TextField(blank=True, default="", max_length=1000)),
                (
                    "annulled_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="result_annulments",
                        to="exams.examattempt",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="organizations.organization",
                    ),
                ),
                (
                    "restored_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "İmtahan nəticəsinin ləğvi",
                "verbose_name_plural": "İmtahan nəticələrinin ləğvi",
                "ordering": ["-annulled_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("restored_at__isnull", True)),
                        fields=("attempt",),
                        name="uniq_active_result_annulment_per_attempt",
                    )
                ],
            },
        ),
        migrations.RunPython(_apply_rls, _revert_rls),
        migrations.RunPython(_copy_incident_annulments, migrations.RunPython.noop),
    ]
