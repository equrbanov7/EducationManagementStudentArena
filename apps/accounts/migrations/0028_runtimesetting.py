"""«Sistem tənzimləmələri» cədvəli + sahibin 2026-10-03 qərarı ilə ilkin artırılmış limitlər.

Sahib: «hələlik parol cəhdində baş verən problemə görə bloklanmanı, OTP göndərmə limitini artıraq — ilk başda
səhv etmə ehtimalı yüksəkdir». Dəyərlər «Sistem tənzimləmələri» bölməsində görünür və oradan dəyişir /
standarta qaytarılır (sətir silinəndə mühitin defoltu işləyir).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

RAISED_DEFAULTS = {
    "login.device_rate": "10/10m",
    "login.account_rate": "40/60m",
    "login.ip_rate": "300/10m",
    "otp.expiry_minutes": 10,
    "otp.max_sends_per_hour": 10,
    "otp.max_attempts": 8,
    "otp.resend_rate": "6/10m",
    "otp.verify_rate": "10/10m",
    "otp.send_ip_rate": "150/10m",
    "otp.verify_ip_rate": "300/10m",
}


def seed(apps, schema_editor):
    RuntimeSetting = apps.get_model("accounts", "RuntimeSetting")
    for key, value in RAISED_DEFAULTS.items():
        RuntimeSetting.objects.get_or_create(key=key, defaults={"value": value})


def unseed(apps, schema_editor):
    apps.get_model("accounts", "RuntimeSetting").objects.filter(key__in=RAISED_DEFAULTS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0027_userprofile_block_reason_contact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RuntimeSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64, unique=True, verbose_name="Açar")),
                ("value", models.JSONField(verbose_name="Dəyər")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Dəyişmə vaxtı")),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Dəyişən",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sistem tənzimləməsi",
                "verbose_name_plural": "Sistem tənzimləmələri",
                "ordering": ("key",),
            },
        ),
        migrations.RunPython(seed, unseed),
    ]
