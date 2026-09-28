# Audit 2026-09-28 S1: `Enrollment.Status.SUSPENDED` — yalnız `choices` dəyişir.
# `status` sütunu varchar(16)-dır və onun üzərində DB CHECK YOXDUR (0039/0045
# yalnız `superseded_by` ↔ `dropped` cütünü yoxlayır), ona görə sxem dəyişmir;
# miqrasiya tam geri qaytarılandır və mövcud sətirlərə toxunmur.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0082_scheduleslot_instructor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="enrollment",
            name="status",
            field=models.CharField(
                choices=[
                    ("enrolled", "Enrolled"),
                    ("completed", "Completed"),
                    ("dropped", "Dropped"),
                    ("suspended", "Suspended"),
                ],
                db_index=True,
                default="enrolled",
                max_length=16,
            ),
        ),
    ]
