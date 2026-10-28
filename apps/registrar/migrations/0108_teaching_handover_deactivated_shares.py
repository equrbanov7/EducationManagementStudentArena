from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registrar", "0107_offering_seminar_is_practical")]
    operations = [
        migrations.AddField(
            model_name="teachinghandover",
            name="deactivated_share_ids",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
