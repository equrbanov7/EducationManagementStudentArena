"""«Jurnal təmizliyi»: yeni qərar kateqoriyası ``not_held`` — keçirilməyən fənn (sahib 2026-10-11).

Yalnız seçim siyahısı və ``reg_hygiene_category_valid`` CHECK-i genişlənir; mövcud sətirlərə toxunulmur,
append-only trigger və RLS (``0086``) dəyişmir. Kiçik cədvəl — CHECK yenidən yaradılması anidir.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0087_midterm_max_change_with_scores"),
    ]

    operations = [
        migrations.AlterField(
            model_name="journalhygienedecision",
            name="category",
            field=models.CharField(
                choices=[
                    ("left_student", "Ayrılmış tələbə"),
                    ("empty_subject", "Boş fənn"),
                    ("not_held", "Keçirilməyən fənn"),
                ],
                max_length=24,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="journalhygienedecision",
            name="reg_hygiene_category_valid",
        ),
        migrations.AddConstraint(
            model_name="journalhygienedecision",
            constraint=models.CheckConstraint(
                condition=models.Q(("category__in", ["left_student", "empty_subject", "not_held"])),
                name="reg_hygiene_category_valid",
            ),
        ),
    ]
