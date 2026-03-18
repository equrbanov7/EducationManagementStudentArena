from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_auditlog_audit_audit_resourc_2a3aef_idx_and_more"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="auditlog",
            name="audit_audit_resourc_2a3aef_idx",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_type",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_id",
        ),
        migrations.RemoveField(
            model_name="auditlog",
            name="resource_repr",
        ),
    ]
