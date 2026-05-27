from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contact", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="reply_body",
            field=models.TextField(blank=True, max_length=10000, verbose_name="Cavab mətni"),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reply_from",
            field=models.CharField(
                blank=True,
                choices=[
                    ("info", "info@emsarena.com"),
                    ("support", "support@emsarena.com"),
                ],
                max_length=16,
                verbose_name="Hansı maildən",
            ),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reply_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Cavab göndərilmə tarixi"),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reply_sent_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="contact_replies",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Cavab verən admin",
            ),
        ),
    ]
