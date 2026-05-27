from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ContactMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, verbose_name="Ad Soyad")),
                ("email", models.EmailField(max_length=254, verbose_name="Email")),
                ("phone", models.CharField(blank=True, max_length=32, verbose_name="Telefon")),
                (
                    "subject",
                    models.CharField(
                        choices=[
                            ("general", "Ümumi sual"),
                            ("sales", "Satış / Demo"),
                            ("support", "Texniki dəstək"),
                            ("partnership", "Əməkdaşlıq"),
                            ("feedback", "Rəy və təklif"),
                            ("other", "Digər"),
                        ],
                        default="general",
                        max_length=32,
                        verbose_name="Mövzu",
                    ),
                ),
                ("message", models.TextField(max_length=5000, verbose_name="Mesaj")),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, null=True, verbose_name="IP ünvan"),
                ),
                ("user_agent", models.CharField(blank=True, max_length=512, verbose_name="User-Agent")),
                ("is_handled", models.BooleanField(default=False, verbose_name="Cavablandırılıb")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Göndərilmə tarixi")),
                ("handled_at", models.DateTimeField(blank=True, null=True, verbose_name="Cavab tarixi")),
            ],
            options={
                "verbose_name": "Əlaqə mesajı",
                "verbose_name_plural": "Əlaqə mesajları",
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["-created_at"], name="contact_con_created_idx"),
                    models.Index(fields=["is_handled", "-created_at"], name="contact_con_handled_idx"),
                ],
            },
        ),
    ]
