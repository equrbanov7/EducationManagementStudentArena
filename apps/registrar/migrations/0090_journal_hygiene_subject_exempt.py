"""«Jurnal təmizliyi»: yeni qərar kateqoriyası ``subject_exempt`` — «Fəndən azad» (sahib 2026-10-15).

Tələbə qrupda qalır, yalnız bir fənnin jurnalından çıxır (qeydiyyat ``dropped``, «Bərpa et» qaytarır).
Yalnız seçim siyahısı və ``reg_hygiene_category_valid`` CHECK-i genişlənir (``0088`` naxışı); mövcud
sətirlərə toxunulmur, append-only trigger və RLS (``0086``) dəyişmir.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registrar", "0089_journal_windows_in_minutes"),
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
                    ("subject_exempt", "Fəndən azad"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="journalhygienedecision",
            name="reason",
            field=models.TextField(
                help_text="Qərarın səbəbi (təmizlik əməlində ≥20 simvol; «Fəndən azad»da istəyə bağlı)."
            ),
        ),
        migrations.RemoveConstraint(
            model_name="journalhygienedecision",
            name="reg_hygiene_category_valid",
        ),
        migrations.AddConstraint(
            model_name="journalhygienedecision",
            constraint=models.CheckConstraint(
                condition=models.Q(("category__in", ["left_student", "empty_subject", "not_held", "subject_exempt"])),
                name="reg_hygiene_category_valid",
            ),
        ),
    ]
