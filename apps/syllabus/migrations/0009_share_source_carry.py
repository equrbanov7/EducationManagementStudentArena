"""``SyllabusShare.source`` — «carry» (sahib 2026-11-08): müəllimin başqa qrupda TƏSDİQLƏNMİŞ sillabusu.

Yalnız seçim siyahısı və ``syllabus_share_source_valid`` CHECK-i genişlənir; mövcud sətirlər dəyişmir.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("syllabus", "0008_syllabus_share"),
    ]

    operations = [
        migrations.AlterField(
            model_name="syllabusshare",
            name="source",
            field=models.CharField(
                choices=[
                    ("teacher", "Müəllimin seçimi"),
                    ("legacy", "Köhnə sistem (bir sillabus bir neçə jurnalda)"),
                    ("carry", "Təsdiqlənmiş sillabus başqa qrupdan (avtomatik)"),
                ],
                default="teacher",
                max_length=16,
            ),
        ),
        migrations.RemoveConstraint(model_name="syllabusshare", name="syllabus_share_source_valid"),
        migrations.AddConstraint(
            model_name="syllabusshare",
            constraint=models.CheckConstraint(
                condition=models.Q(("source__in", ["teacher", "legacy", "carry"])), name="syllabus_share_source_valid"
            ),
        ),
    ]
