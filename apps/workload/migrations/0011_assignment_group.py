# Sahib 2026-11-09 («bir fənn = bir kart»): bölgünün struktur qrup bağı + lab/seminar alt qrupu nömrəsi.
#
# YALNIZ SXEMA: iki nullable sütun + CHECK. Heç bir sətir yenidən yazılmır (sahib: «müəllimlərin yüklərini
# pozmayacaq ki?» — saat, müəllim, fəaliyyət toxunulmur). Köhnə ``groups_note`` qeydləri əvvəlki kimi parse olunur
# (``offering_shares._assignment_group``); qeyddən bağa köçürmə ayrıca, dry-run-lı servisdir
# (``services.assignment_groups.backfill_groups`` — prod-data-ops yolu ilə, istənilsə).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0032_seed_alumni_role"),
        ("workload", "0010_row_patok_lead"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherassignment",
            name="group",
            field=models.ForeignKey(
                blank=True,
                help_text="Bölgünün qrupu (sətrin qruplarından biri); boş = sətrin bütün qrupları.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="workload_assignments_as_group",
                to="organizations.orgunit",
            ),
        ),
        migrations.AddField(
            model_name="teacherassignment",
            name="sub_number",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Lab qrupu / seminar alt qrupu nömrəsi (jurnaldakı Lab-1, Lab-2 …); boş = bütün qrup.",
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="teacherassignment",
            constraint=models.CheckConstraint(
                check=models.Q(sub_number__isnull=True) | models.Q(sub_number__gte=1, sub_number__lte=9),
                name="workload_assignment_sub_number_range",
            ),
        ),
    ]
