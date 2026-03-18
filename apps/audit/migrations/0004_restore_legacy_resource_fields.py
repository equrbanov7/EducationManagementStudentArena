from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0003_remove_legacy_resource_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditlog",
            name="resource_type",
            field=models.CharField(blank=True, default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="auditlog",
            name="resource_id",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="auditlog",
            name="resource_repr",
            field=models.CharField(blank=True, default="", max_length=500),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="auditlog",
            index=models.Index(fields=["resource_type", "resource_id"], name="audit_audit_resourc_2a3aef_idx"),
        ),
    ]
