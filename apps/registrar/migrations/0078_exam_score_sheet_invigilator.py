"""``ExamScoreSheet.invigilator`` — nəzarətçi FK-sı (sahibin rəyi, 2026-09-14, W2 `w2paper`).

Sahib: «Yoxlayan müəllim» və «Nəzarətçi» sərbəst mətn yox, təşkilatın
müəllimlərindən axtarışlı seçim olsun. ``examiner`` FK-sı onsuz da var idi;
nəzarətçi üçün ``invigilator`` FK-sı əlavə olunur, ``invigilator_name`` snapshot
kimi qalır (köhnə vərəqlərdə yalnız ad var — toxunulmur).
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0077_exam_score_questions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="examscoresheet",
            name="invigilator",
            field=models.ForeignKey(
                blank=True,
                help_text="Nəzarətçi (təşkilatın müəllimi) — opsional.",
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="invigilated_score_sheets",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="examscoresheet",
            name="invigilator_name",
            field=models.CharField(blank=True, help_text="Nəzarətçinin adı (snapshot).", max_length=200),
        ),
    ]
