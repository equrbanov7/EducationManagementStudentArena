"""Cədvəl slotu: yumşaq silmə + «park» vəziyyəti (cədvəl redaktoru, 2026-09-09).

``is_deleted``/``deleted_at`` — ``core.models.SoftDeleteModel``: slot artıq
bazadan SİLİNMİR (layihə qaydası), default meneceri onu süzgəcləyir.

``is_parked``/``parked_at``/``parked_by``/``park_reason`` — MƏCBURİ dəyişiklikdə
(forced move) yerindən çıxarılan BAŞQA qrupun slotu itmir: parklanır, cədvəldən
və konflikt hesabından çıxır, amma redaktorun «yenidən yerləşdirilməli»
siyahısında qalır (sahibin tələbi, 2026-09-09).

Sahələr yalnız ƏLAVƏ olunur — mövcud sətirlər default dəyərlərlə (aktiv,
parklanmamış) qalır, məlumat köçürülməsi lazım deyil.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0050_tutor_coordinator_parity"),
        ("registrar", "0069_guest_roster_document"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduleslot",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scheduleslot",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="scheduleslot",
            name="is_parked",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Məcburi dəyişiklik nəticəsində yerindən çıxarılıb — yenidən yerləşdirilməlidir.",
            ),
        ),
        migrations.AddField(
            model_name="scheduleslot",
            name="park_reason",
            field=models.TextField(blank=True, help_text="Parklama səbəbi (audit + redaktorda görünür)."),
        ),
        migrations.AddField(
            model_name="scheduleslot",
            name="parked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="scheduleslot",
            name="parked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="scheduleslot",
            index=models.Index(fields=["organization", "is_parked", "weekday"], name="registrar_s_organiz_3bb363_idx"),
        ),
    ]
