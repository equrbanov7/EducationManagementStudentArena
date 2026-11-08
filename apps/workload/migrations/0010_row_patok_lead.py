# Sahib 2026-11-08: patok tərəfdaşı → aparıcı sətir açıq bağı (nullable self-FK).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0009_intensive_row"),
    ]

    operations = [
        migrations.AddField(
            model_name="teachingtaskrow",
            name="patok_lead",
            field=models.ForeignKey(
                blank=True,
                help_text="Patok tərəfdaşı: mühazirəsi bu (eyni tapşırıq/fənn/semestr, lecture_total>0) sətirdədir.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="patok_partners",
                to="workload.teachingtaskrow",
            ),
        ),
    ]
