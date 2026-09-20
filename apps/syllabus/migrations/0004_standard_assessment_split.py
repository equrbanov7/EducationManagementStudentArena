"""Sahib qərarı 2026-09-20: qiymətləndirmə bölgüsü universitet STANDARTIDIR
(kollokvium 20 · seminar/lab ədədi ortası 10; davamiyyət 10 · sərbəst iş 10 ·
yekun 50).  Redaktəyə AÇIQ versiyaların ``assess`` bölməsində köhnə «sərbəst
bölgü» (məs. 15/15) standarta gətirilir — əks halda bölmə tamamlanmamış sayılıb
təsdiqə göndərməni bloklayardı.  Təsdiqlənmiş versiyalar TOXUNULMUR (immutable);
oxu sənədi onsuz da standart düsturu göstərir.  ``note``/``exam_questions`` və
digər açarlar olduğu kimi qalır.
"""

from django.db import migrations

OPEN_EDITABLE = ("draft", "revision")  # EDITABLE_STATUSES (constants.py)
STANDARD = {"midterm": 20, "project": 10}


def forwards(apps, schema_editor):
    SyllabusSection = apps.get_model("syllabus", "SyllabusSection")
    rows = SyllabusSection.objects.filter(section_id="assess", version__status__in=OPEN_EDITABLE).only(
        "pk", "data"
    )
    for row in rows.iterator():
        data = dict(row.data or {})
        if data.get("midterm") == STANDARD["midterm"] and data.get("project") == STANDARD["project"]:
            continue
        data.update(STANDARD)
        SyllabusSection.objects.filter(pk=row.pk).update(data=data)


class Migration(migrations.Migration):
    dependencies = [("syllabus", "0003_normalize_open_assessment_split")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
