# Sahib 2026-11-26 («Bölgü sehrbazı»): lab qruplarının sayı seminar alt qruplarından fərqli ola bilər
# (seminar 2 alt qrup, lab hər alt qrupda 2 → 4 lab qrupu). YALNIZ SXEMA: bir sütun, defolt 0 = «subgroup_count ilə
# eyni» — mövcud sətirlərin saatı, bölgüsü və xəbərdarlıqları dəyişmir. Geri qaytarıla bilər (RemoveField).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workload", "0011_assignment_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="teachingtaskrow",
            name="lab_group_count",
            field=models.PositiveSmallIntegerField(
                default=0, help_text="Laboratoriya qruplarının sayı; 0 — «Qrup/yarımqrup sayı» ilə eyni."
            ),
        ),
    ]
