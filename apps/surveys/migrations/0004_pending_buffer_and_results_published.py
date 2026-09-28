# Audit 2026-09-28 SV-2/SV-3: dərc gözləyən anonim cavab buferi + nəticələrin ilk dərc anı.
# Geri çevrilə bilən və mövcud data üçün təhlükəsiz: yeni boş cədvəl, nullable sahə; bağlı
# kampaniyalar üçün ``results_published_at`` = ``closed_at`` (və ya ``updated_at``) — onların
# nəticəsi artıq göstərilib, sonrakı cavablar (yenidən açılış) buferdə gözləyəcək.

import uuid

import django.db.models.deletion
from django.db import migrations, models

_TABLE = "surveys_surveypendingresponse"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_ORG_EXPR = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"


def _rls_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING ({_BYPASS_EXPR} OR organization_id IS NULL OR {_ORG_EXPR})
    WITH CHECK ({_BYPASS_EXPR} OR organization_id IS NULL OR {_ORG_EXPR});
""")


def _rls_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
""")


def _mark_closed_published(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    SurveyCampaign = apps.get_model("surveys", "SurveyCampaign")
    for campaign in SurveyCampaign.objects.filter(status="closed", results_published_at__isnull=True):
        campaign.results_published_at = campaign.closed_at or campaign.updated_at
        campaign.save(update_fields=["results_published_at"])
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'off', true)")


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0054_seed_quality_control_roles"),
        ("surveys", "0003_receipt_once_per_teacher"),
    ]

    operations = [
        migrations.AddField(
            model_name="surveycampaign",
            name="results_published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="SurveyPendingResponse",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("scope", models.CharField(choices=[("teacher", "Müəllim"), ("general", "Ümumi")], max_length=16)),
                ("bucket", models.CharField(max_length=64)),
                ("payload", models.JSONField(default=dict)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_responses",
                        to="surveys.surveycampaign",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
            ],
            options={
                "verbose_name": "dərc gözləyən anonim cavab",
                "verbose_name_plural": "dərc gözləyən anonim cavablar",
                "indexes": [models.Index(fields=["campaign", "bucket"], name="surveys_pending_camp_bucket")],
            },
        ),
        migrations.RunPython(_rls_forward, _rls_reverse),
        migrations.RunPython(_mark_closed_published, migrations.RunPython.noop),
    ]
