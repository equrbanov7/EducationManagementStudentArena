"""İmtahan balının daxil edilməsi — midterm / final, sütun-sütun tavan, yoxlanma tarixi (sahib 2026-10-25).

Mövcud sətir və vərəqlər yekun imtahana aiddir: ``assessment`` defoltu ``final`` (prod kopyasında
``registrar_examscoreentry`` / ``registrar_examscoresheet`` 0 sətir idi — 2026-10-25 yoxlanıb).
``question_maxes`` / ``checked_on`` NULL qalır (köhnə bərabər şəbəkə). CHECK-lər yalnız zibil tutur
(``new_score`` 0..100, ``assessment`` məlum dəyər) — tavanlar (30 / 50) servis + komponent qoruyucusundadır.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0072_credit_recognition_permission"),
        ("registrar", "0103_student_movement_graduation_kind"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="examscoreentry",
            name="assessment",
            field=models.CharField(
                choices=[("final", "Final"), ("midterm", "Midterm")],
                default="final",
                help_text="Midterm (jurnalın Midterm xanası) və ya final (yekun imtahan balı) — 2026-10-25.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="assessment",
            field=models.CharField(
                choices=[("final", "Final"), ("midterm", "Midterm")],
                default="final",
                help_text="Midterm və ya final — vərəqin bütün sətirləri eyni imtahana aiddir (2026-10-25).",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="checked_on",
            field=models.DateField(blank=True, help_text="İmtahan vərəqlərinin yoxlandığı tarix.", null=True),
        ),
        migrations.AddField(
            model_name="examscoresheet",
            name="question_maxes",
            field=models.JSONField(
                blank=True,
                help_text="Sütunların (sualların) maksimum balları — cəmi imtahan tavanına bərabərdir.",
                null=True,
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
                    ("window_edit", "Edit within 15 minutes"),
                ],
                default="initial",
                max_length=12,
            ),
        ),
        migrations.AddIndex(
            model_name="examscoreentry",
            index=models.Index(fields=["enrollment", "assessment", "kind"], name="reg_ese_enr_assess_kind_idx"),
        ),
        migrations.AddConstraint(
            model_name="examscoreentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("new_score__isnull", True),
                    models.Q(("new_score__gte", 0), ("new_score__lte", 100)),
                    _connector="OR",
                ),
                name="registrar_ese_new_score_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="examscoreentry",
            constraint=models.CheckConstraint(
                condition=models.Q(("assessment__in", ["final", "midterm"])), name="registrar_ese_assessment_valid"
            ),
        ),
        migrations.AddConstraint(
            model_name="examscoresheet",
            constraint=models.CheckConstraint(
                condition=models.Q(("assessment__in", ["final", "midterm"])), name="registrar_ess_assessment_valid"
            ),
        ),
    ]
