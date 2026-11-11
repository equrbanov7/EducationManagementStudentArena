"""``ExamQuestion.replaces`` — cavablanmış sualın «yeni versiya»sı köhnə suala bağlanır (sahib 2026-11-11).

Köhnə sual silinmir və dəyişdirilmir (keçmiş cəhdlər, apellyasiyalar, statistika); yalnız deaktiv olunur.
Nullable sütun + indeks — mövcud sətirlərə toxunmur.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0077_exam_journal_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="examquestion",
            name="replaces",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="newer_versions",
                to="exams.examquestion",
                verbose_name="replaces",
            ),
        ),
    ]
