"""İmtahan ↔ elektron jurnal açıq bağlantısı (sahib 2026-10-24, «JS Loop» halı).

* ``Exam.journal_teacher`` — yaradanın seçdiyi müəllim (fənn siyahısı onun fənlərinə daralır);
* ``Exam.journal_offerings`` — fənn + qruplar üzrə hər qrupun öz jurnal açılışı.

M2M join cədvəli layihə qaydası ilə ``rls_tenant_isolation`` siyasəti daşıyır (``0069`` nümunəsi):
həm imtahan, həm açılış cari təşkilatın olmalıdır; ``FORCE``; qeyri-PostgreSQL → no-op.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "exams_exam_journal_offerings"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_CONDITION = (
    "exam_id IN (\n"
    "            SELECT id FROM exams_exam\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )\n"
    "        AND courseoffering_id IN (\n"
    "            SELECT id FROM registrar_courseoffering\n"
    f"            WHERE organization_id::text = {_CURRENT_ORG}\n"
    "        )"
)

_USING = f"{_BYPASS_EXPR}\n        OR {_CONDITION}"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_USING}
    )
    WITH CHECK (
        {_USING}
    );
"""

_REVERSE_SQL = f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0076_merge_night_2026_10_13"),
        ("registrar", "0095_componentscore_exam_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="exam",
            name="journal_offerings",
            field=models.ManyToManyField(
                blank=True,
                editable=False,
                related_name="linked_exams",
                to="registrar.courseoffering",
                verbose_name="Bağlı jurnallar",
            ),
        ),
        migrations.AddField(
            model_name="exam",
            name="journal_teacher",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="journal_linked_exams",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Müəllim (jurnal)",
            ),
        ),
        migrations.RunPython(_apply, _revert),
    ]
