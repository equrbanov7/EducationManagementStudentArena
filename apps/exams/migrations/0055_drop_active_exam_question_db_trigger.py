"""Drop the DB-level "active exam requires a question" trigger (0052).

Bu backstop çox aqressiv idi: `exams_exam`-a AFTER INSERT/UPDATE və
`exams_examquestion`-a AFTER DELETE constraint trigger-ləri kodun/testlərin
qanuni nümunəsini pozurdu — sual olmadan birbaşa aktiv imtahan yaratmaq (seed,
import, dublikat, yüzlərlə test fixture-u) və Django cascade-silmə (uşaq sualları
valideyn imtahandan əvvəl silinir → "son aktiv sual" yoxlaması commit-də partlayır).

İnvariant tətbiq qatında qalır: Seq3 publish qapısı (services/lifecycle.py) boş
imtahanı DƏRC ETMİR və question CRUD guard-ları (services/question_invariants.py)
müəllimin UI-dən son aktiv sualı silməsinin qarşısını alır. DB-backstop-u götürürük.
"""

from django.db import migrations

DROP_SQL = r"""
DROP TRIGGER IF EXISTS exams_question_preserve_active_exam ON exams_examquestion;
DROP FUNCTION IF EXISTS emsarena_preserve_active_exam_question();
DROP TRIGGER IF EXISTS exams_exam_publish_requires_question ON exams_exam;
DROP FUNCTION IF EXISTS emsarena_exam_publish_requires_question();
"""


def drop_trigger(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP_SQL)


def noop(apps, schema_editor):
    # Backstop qəsdən geri qaytarılmır (kod bazası ilə uyğunsuz idi).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0054_protect_exam_attempt_history"),
    ]

    operations = [
        migrations.RunPython(drop_trigger, noop),
    ]
