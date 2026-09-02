"""Sərbəst iş «təhvil sayı» aqreqatı üçün örtən indeks (2026-09-02 performans auditi, F3).

``accounts.academic_records`` icmalı belə sorğulayır::

    SELECT enrollment_id, COUNT(id) FROM registrar_selfworkmark
    WHERE done AND enrollment_id IN (…) GROUP BY enrollment_id

Mövcud indekslər (``organization``+``enrollment``, FK ``enrollment_id``)
``done`` süzgəcini örtmürdü; org-səviyyəli (fakültə filtri olmayan) çağırışda
bu, tam sətir oxumasına çevrilirdi.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registrar", "0062_legacy_grade_review_category_snapshot"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="selfworkmark",
            index=models.Index(fields=["enrollment", "done"], name="selfwork_enrollment_done"),
        ),
    ]
