"""Dondurma (akademik məzuniyyət) səbəbinin kateqoriyası — sahib 2026-11-04.

* ``ADD COLUMN ... DEFAULT ''`` — PG 11+ cədvəli yenidən yazmır və sətir trigger-i işə düşmür, yəni
  append-only qoruyucu (``0067``: UPDATE/DELETE bloku) köhnə əmrlərə toxunmur; köhnə sətirlər boş qalır.
* CHECK: kateqoriya yalnız ``kind='academic_leave'`` sətrində ola bilər (köhnə sətirlər onsuz da boşdur).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0113_enrollment_legacy_qb_fail"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentmovement",
            name="leave_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("academic", "Akademik məzuniyyət"),
                    ("maternity", "Analıq (doğuş) məzuniyyəti"),
                    ("childcare", "Uşağa qulluq məzuniyyəti"),
                    ("medical", "Səhhətlə bağlı (tibbi)"),
                    ("military", "Hərbi xidmət"),
                    ("family", "Ailə vəziyyəti"),
                    ("financial", "Maliyyə səbəbi"),
                    ("other", "Digər"),
                ],
                default="",
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="studentmovement",
            constraint=models.CheckConstraint(
                condition=models.Q(("leave_reason", ""), ("kind", "academic_leave"), _connector="OR"),
                name="registrar_movement_leave_reason_only_on_leave",
            ),
        ),
    ]
