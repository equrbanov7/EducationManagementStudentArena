from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed(apps, schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    Unit = apps.get_model("applications", "ApplicationUnit")
    Kind = apps.get_model("applications", "ApplicationKind")
    for unit in Unit.objects.filter(code="tedris"):
        Unit.objects.filter(pk=unit.pk).update(accepts_students=False, requires_recipient=True)
        Kind.objects.get_or_create(organization_id=unit.organization_id, code="prorektor", defaults={
            "label": "Prorektora müraciət", "note": "Konkret prorektoru seçərək müraciət göndərin",
            "allowed_sender_families": ["teacher"], "target_unit_id": unit.pk, "sla_days": 5,
            "badge_palette": "primary", "is_active": True,
        })


def unseed(apps, schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    Unit = apps.get_model("applications", "ApplicationUnit")
    Kind = apps.get_model("applications", "ApplicationKind")
    Unit.objects.filter(code="tedris").update(accepts_students=True, requires_recipient=False)
    for kind in Kind.objects.filter(code="prorektor"):
        if not kind.applications.exists():
            kind.delete()
        else:
            Kind.objects.filter(pk=kind.pk).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("applications", "0007_rim_staff_answers_every_application"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField("applicationunit", "accepts_students", models.BooleanField(default=True)),
        migrations.AddField("applicationunit", "requires_recipient", models.BooleanField(default=False)),
        migrations.AddField("applicationevent", "hidden_at", models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.AddField("applicationevent", "hidden_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hidden_application_events", to=settings.AUTH_USER_MODEL)),
        migrations.RunPython(seed, unseed),
    ]
