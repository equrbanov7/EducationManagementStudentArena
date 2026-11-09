# Sahib 2026-11-09 («bir fənn = bir kart»): bölgünün struktur qrup bağı + lab/seminar alt qrupu nömrəsi.
#
# Backfill: ``groups_note`` sətrin qruplarından DÜZ BİRİNİN adına/koduna parse olunursa (``offering_shares.
# _assignment_group`` qaydası — vergül/nöqtəli vergül/«+» ilə bir neçə hissə, hamısı eyni qrup) ``group`` yazılır;
# birdən çox qrup və ya tanınmayan mətn — qeyd olduğu kimi qalır (jurnal onu əvvəlki kimi parse edir). Saat
# dəyişmir; DB balans trigger-i yalnız sütun yeniləməsini görür (``id <> NEW.id`` — cəm eyni qalır).

import re

import django.db.models.deletion
from django.db import migrations, models, transaction


def _normalize(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _backfill(apps, schema_editor):
    TeacherAssignment = apps.get_model("workload", "TeacherAssignment")
    Through = apps.get_model("workload", "TeachingTaskRow").groups.through
    OrgUnit = apps.get_model("organizations", "OrgUnit")
    pending = list(
        TeacherAssignment.objects.filter(group__isnull=True).exclude(groups_note="").values("id", "row_id", "groups_note")
    )
    if not pending:
        return
    row_ids = {item["row_id"] for item in pending}
    groups_by_row = {}
    links = list(Through.objects.filter(teachingtaskrow_id__in=row_ids).values_list("teachingtaskrow_id", "orgunit_id"))
    units = {
        unit.pk: unit for unit in OrgUnit.objects.filter(pk__in={unit_id for _row_id, unit_id in links}).only("name", "code")
    }
    for row_id, unit_id in links:
        groups_by_row.setdefault(row_id, []).append(units[unit_id])
    for item in pending:
        known = {}
        for unit in groups_by_row.get(item["row_id"], ()):
            for label in (unit.name, getattr(unit, "code", "")):
                if label:
                    known.setdefault(_normalize(label), set()).add(unit.pk)
        parts = [_normalize(part) for part in re.split(r"[,;+\n]+", item["groups_note"]) if part.strip()]
        if not parts or any(part not in known or len(known[part]) != 1 for part in parts):
            continue
        found = {next(iter(known[part])) for part in parts}
        if len(found) != 1:
            continue
        try:
            with transaction.atomic():
                TeacherAssignment.objects.filter(pk=item["id"]).update(group_id=found.pop())
        except Exception:  # noqa: BLE001 — bir sətrin köhnə balans pozuntusu miqrasiyanı dayandırmasın
            continue


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
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
