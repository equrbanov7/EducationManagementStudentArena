"""Sahib 2026-11-09: eyni FİN — bir adamın tələbə və işçi hesabı (``apps/accounts/shared_fin.py``).

FİN unikallığı ƏSAS hesablar arasında qalır (şərti unikal indeks ``fin_shared_with IS NULL``); bağlı ikinci hesab
eyni FİN-i ``fin_shared_with`` (əsas hesab, OneToOne) və ``fin_shared_confirmed_at`` (sahibin təsdiqi) ilə daşıyır.
Mövcud məlumat üçün heç nə dəyişmir: bütün profillərdə ``fin_shared_with`` boşdur, köhnə unikal indeks eyni
qaydanı şərti indeks kimi davam etdirir.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0035_runtime_limits_semester_start_2026_10_23"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="fin_shared_with",
            field=models.OneToOneField(
                blank=True,
                default=None,
                help_text="Eyni FİN-li digər (əsas) hesab — tələbə + işçi hesabı bir adama məxsusdur.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fin_shared_secondary",
                to=settings.AUTH_USER_MODEL,
                verbose_name="FİN-i paylaşdığı əsas hesab",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="fin_shared_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Sahibin «hər iki hesab mənimdir» təsdiqinin vaxtı.",
                null=True,
                verbose_name="FİN paylaşımı təsdiqlənib",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="fin",
            field=models.CharField(
                blank=True,
                default=None,
                help_text="Şəxsiyyət vəsiqəsi FİN kodu (7 simvol, A-Z0-9) — idxal/uzlaşdırma açarı.",
                max_length=7,
                null=True,
                validators=[core.validators.validate_fin],
                verbose_name="FİN",
            ),
        ),
        migrations.AddConstraint(
            model_name="userprofile",
            constraint=models.UniqueConstraint(
                condition=models.Q(("fin_shared_with__isnull", True)),
                fields=("fin",),
                name="accounts_userprofile_fin_primary_uniq",
            ),
        ),
    ]
