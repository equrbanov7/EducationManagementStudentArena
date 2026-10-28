from django.db import migrations, models
from django.db.models import Q


def restrict_existing(apps, schema_editor):
    if schema_editor is not None and schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SET LOCAL app.bypass_rls = 'on'")
    Application = apps.get_model("applications", "Application")
    ids = Application.objects.filter(
        Q(current_unit__requires_recipient=True)
        | Q(events__from_unit__requires_recipient=True)
        | Q(events__to_unit__requires_recipient=True)
    ).values_list("pk", flat=True)
    Application.objects.filter(pk__in=ids).update(recipient_restricted=True)
    # A historical unit watch does not identify the intended person. Keep its
    # row for audit, but do not invent an audience or broadcast it to the unit.


class Migration(migrations.Migration):
    dependencies = [("applications", "0008_recipient_and_reply_visibility")]
    operations = [
        migrations.AddField("application", "recipient_restricted", models.BooleanField(default=False, editable=False)),
        migrations.AddField(
            "applicationwatch", "recipient_ids", models.JSONField(blank=True, default=list, editable=False)
        ),
        migrations.RunPython(restrict_existing, migrations.RunPython.noop),
    ]
