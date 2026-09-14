"""W4 `w4wizard` 2026-09-14, R2 — imtahana qrup reyestri (OrgUnit GROUP) təyinatı.

Sehrbazın «İcazəli qruplar» seçicisi yalnız köhnə imtahan kohortlarını
(`exams.StudentGroup`) tanıyırdı; real akademik qruplar («634 ing» kimi
`OrgUnit` tipi `group`) imtahana təyin oluna bilmirdi. `Exam.allowed_units`
M2M-i reyestr qrupunu birbaşa imtahana bağlayır (sahibin 2026-09-07 qərarı:
qrup reyestri əsasdır, kohort səthi silinməlidir).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0067_drop_duplicate_student_pin_index"),
        ("organizations", "0052_rim_final_score_entry"),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="allowed_units",
            field=models.ManyToManyField(
                blank=True,
                help_text="allowed_units",
                limit_choices_to={"unit_type": "group"},
                related_name="assigned_exams",
                to="organizations.orgunit",
                verbose_name="allowed_units",
            ),
        ),
    ]
