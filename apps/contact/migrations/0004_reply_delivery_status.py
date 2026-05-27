from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contact", "0003_merge_20260527_1505"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="reply_delivery_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Göndərilir"),
                    ("sent", "Göndərildi"),
                    ("failed", "Göndərilmədi"),
                    ("recorded", "Qeyd edildi"),
                ],
                max_length=16,
                verbose_name="Cavab email statusu",
            ),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reply_delivery_error",
            field=models.CharField(blank=True, max_length=500, verbose_name="Cavab email xətası"),
        ),
        migrations.RunSQL(
            sql=(
                "UPDATE contact_contactmessage "
                "SET reply_delivery_status = 'recorded' "
                "WHERE reply_sent_at IS NOT NULL"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
