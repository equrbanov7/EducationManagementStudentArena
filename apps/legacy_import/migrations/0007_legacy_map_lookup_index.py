"""«Bu açılış köçürülüb?» sorğusu üçün uyğun indeks (2026-09-02 performans auditi).

``exam_eligibility._migrated_offering_ids`` belə sorğulayır::

    SELECT target_pk FROM legacy_import_legacyentitymap
    WHERE entity_type = 'course_offering' AND state = 'migrated' AND target_pk IN (…)

``target_model_label`` süzülmədiyi üçün mövcud ``legacy_map_target``
(``target_model_label``, ``target_pk``) indeksinin APARICI sütununa oturmurdu —
777 901 sətirlik cədvəldə tək sətirlik axtarış ~5 011 səhifə (≈40 MB) oxuyurdu
(20-97 ms/çağırış, EXPLAIN (ANALYZE, BUFFERS) ilə təsdiqlənib).
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("legacy_import", "0006_scalable_batch_accounting"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="legacyentitymap",
            index=models.Index(fields=["entity_type", "state", "target_pk"], name="legacy_map_lookup"),
        ),
    ]
