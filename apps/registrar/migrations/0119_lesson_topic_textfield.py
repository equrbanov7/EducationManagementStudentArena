"""Sahib 2026-11-03: dərs mövzusunda uzunluq həddi olmasın.

``Lesson.topic`` və ``LessonCorrection.old_topic/new_topic`` CharField(255) → TextField.
PostgreSQL-də ``varchar(255) → text`` binar uyğun çevrilmədir: cədvəl yenidən yazılmır,
mövcud dəyərlər olduğu kimi qalır (data toxunulmur).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("registrar", "0118_seminar_groups")]

    operations = [
        migrations.AlterField(
            model_name="lesson",
            name="topic",
            field=models.TextField(blank=True, help_text="Mövzu (opsional)."),
        ),
        migrations.AlterField(
            model_name="lessoncorrection",
            name="new_topic",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="lessoncorrection",
            name="old_topic",
            field=models.TextField(blank=True, default=""),
        ),
    ]
