from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("contact", "0005_alter_contactmessage_reply_from")]
    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="submission_key",
            field=models.UUIDField(editable=False, null=True, unique=True),
        )
    ]
