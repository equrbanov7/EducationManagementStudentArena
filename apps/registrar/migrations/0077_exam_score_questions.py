"""Kağız imtahan balının SUAL-SUAL köçürülməsi + apellyasiya növü (W2 `w2paper`, 2026-09-14).

Sahibin tələbi (2026-09-14): «kağızda verilən imtahanlarda tələbənin aldığı
qiyməti sistemə köçürmək mümkün olsun … apellyasiyadan və ya nədənsə sonra
DƏYİŞƏN nəticələrin izlənməsi lazımdır. İmtahandan max bal 50, hər sualdan max
10, yekun bal 100-dən çox ola bilməz.»

* ``ExamScoreSheet.question_count`` (defolt 5, 0..10; 0 = tək yekun bal) və
  ``question_max`` (defolt 10) — vərəqin sual şəbəkəsi;
* ``ExamScoreEntry.question_scores`` — sual-sual ballar (JSON siyahı), köhnə
  sətirlərdə NULL;
* ``ExamScoreEntryKind.APPEAL`` — yalnız ``choices`` (DB-də CHECK yoxdur);
* ``ExamScoreSheet.exam_kind`` (addendum, eyni gün) — ``written`` / ``practical``,
  köhnə vərəqlər ``written``.

Cəmin tavanı (50) sxemdən gəlir (``finals.exam_score_max``) — burada da, kodda
da sabit yazılmır. Mövcud sətirlər toxunulmur (append-only jurnal).
"""

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0076_lesson_org_date_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="examscoreentry",
            name="question_scores",
            field=models.JSONField(
                blank=True,
                help_text="Sual-sual ballar (siyahı) — tək yekun bal rejimində NULL.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="exam_kind",
            field=models.CharField(
                choices=[("written", "Written"), ("practical", "Practical")],
                default="written",
                help_text="Kağız imtahanın növü — yazılı / praktiki (2026-09-14).",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="question_count",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="Vərəqdəki sual sayı (0 = tək yekun bal).",
                validators=[django.core.validators.MaxValueValidator(10)],
            ),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="question_max",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="Bir sualın maksimum balı.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="examscoreentry",
            name="kind",
            field=models.CharField(
                choices=[
                    ("initial", "Initial entry"),
                    ("correction", "Documented change"),
                    ("appeal", "Appeal result"),
                ],
                default="initial",
                max_length=12,
            ),
        ),
    ]
