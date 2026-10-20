"""Apellyasiyanın verilmə rejimi — «imtahan sonunda» / «sonradan» (sahib 2026-10-20).

Mövcud sətirlər ``False`` («sonradan») alır: köhnə müraciətlər üçün rejim məlum deyil, defolt
ehtiyatlı tərəfdir. Sütun ``NOT NULL DEFAULT false`` — böyük cədvəldə də sürətli (PG 11+).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("appeals", "0006_rls_answer_key_correction"),
    ]

    operations = [
        migrations.AddField(
            model_name="appeal",
            name="filed_onsite",
            field=models.BooleanField(default=False, verbose_name="filed_onsite"),
        ),
    ]
