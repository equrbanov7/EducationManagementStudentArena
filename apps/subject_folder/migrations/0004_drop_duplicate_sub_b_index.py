"""``subject_folder_similaritymatch`` — dublikat ``submission_b`` indeksi silinir.

``submission_b`` ForeignKey-dir və Django onun sütununa öz indeksini qurur; ``Meta.indexes``-dəki
``sf_match_sub_b`` eyni sütunda İKİNCİ indeks idi (``registrar.tests.test_w2_indexes`` —
``pg_index`` dublikat yoxlaması). Qalan: FK indeksi + ``sf_match_uniq_pair`` (a, b).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("subject_folder", "0003_submission_guards"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="similaritymatch",
            name="sf_match_sub_b",
        ),
    ]
