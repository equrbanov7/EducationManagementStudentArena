"""Sahib 2026-10-25: sillabusun plan saatını kafedra / tədris şöbəsi əl ilə düzəldə bilsin.

``Syllabus.plan_hours_override`` — boş dict defolt; yalnız sütun əlavə olunur (RLS siyasətləri cədvəl
səviyyəsindədir, dəyişmir).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("syllabus", "0005_syllabus_reuse")]

    operations = [
        migrations.AddField(
            model_name="syllabus",
            name="plan_hours_override",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Kafedranın / tədris şöbəsinin əl ilə düzəltdiyi plan saatı (BİR qrup üçün): "
                    "{'lecture': .., 'seminar': .., 'lab': ..}. Boşdursa saat tədris planı / dərs yükündən hesablanır."
                ),
            ),
        ),
    ]
