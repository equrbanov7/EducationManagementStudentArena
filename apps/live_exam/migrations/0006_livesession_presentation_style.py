"""2026-10-19: LiveSession.presentation_style — «Rəsmi» / «Qeyri-rəsmi».

Mövcud sessiyalar əvvəlki (oyunbaz) görünüşü saxlayır: sütun ``playful`` defoltu ilə əlavə olunur
(köhnə sətirlər doldurulur), sonra model defoltu ``formal``-a keçir — yalnız YENİ sessiyalar rəsmidir.
Additiv və geri qaytarıla biləndir (geri: sütun silinir).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("live_exam", "0005_liveplayer_removed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="livesession",
            name="presentation_style",
            field=models.CharField(
                choices=[("formal", "Rəsmi"), ("playful", "Qeyri-rəsmi")],
                default="playful",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="livesession",
            name="presentation_style",
            field=models.CharField(
                choices=[("formal", "Rəsmi"), ("playful", "Qeyri-rəsmi")],
                default="formal",
                max_length=12,
            ),
        ),
    ]
