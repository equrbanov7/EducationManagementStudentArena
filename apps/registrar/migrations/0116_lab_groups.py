"""Laboratoriya qrupları bir jurnal daxilində — ``Enrollment.lab_group`` + ``Lesson.lab_group`` (sahib 2026-11-06).

Hər iki sahə NULL-able, defoltsuzdur: PostgreSQL-də ``ADD COLUMN … NULL`` yalnız kataloq dəyişikliyidir (cədvəl
yenidən yazılmır, qısa kilid). Mövcud sətirlər boş qalır = köhnə davranış.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0115_journal_removal"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="lab_group",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, help_text="Laboratoriya qrupu (1, 2 …) bu jurnal daxilində; boş = bölünməyib."
            ),
        ),
        migrations.AddField(
            model_name="lesson",
            name="lab_group",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, help_text="Laboratoriya qrupu (yalnız lab dərsi); boş = bütün qrup."
            ),
        ),
    ]
