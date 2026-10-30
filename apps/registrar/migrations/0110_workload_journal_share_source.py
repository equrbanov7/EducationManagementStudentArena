"""Dərs yükündən törəyən paylar manual/legacy paylardan ayrıca idarə olunur."""

from django.db import migrations, models


def retire_workload_shares(apps, schema_editor):
    """Geri keçiddə pay tarixçəsi saxlanır, yeni avtomatik giriş söndürülür."""
    Share = apps.get_model("registrar", "JournalShare")
    Share.objects.filter(source="workload").update(source="manual", is_active=False)


class Migration(migrations.Migration):
    dependencies = [("registrar", "0109_aggregate_absence_credit")]

    operations = [
        migrations.RemoveConstraint(model_name="journalshare", name="reg_share_source_valid"),
        migrations.AlterField(
            model_name="journalshare",
            name="source",
            field=models.CharField(
                choices=[("legacy", "Köhnə sistem"), ("manual", "Əl ilə"), ("workload", "Dərs yükü")],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, retire_workload_shares),
        migrations.AddConstraint(
            model_name="journalshare",
            constraint=models.CheckConstraint(
                condition=models.Q(source__in=["legacy", "manual", "workload"]), name="reg_share_source_valid"
            ),
        ),
    ]
