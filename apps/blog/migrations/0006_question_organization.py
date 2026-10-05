"""``blog.Question`` təşkilata bağlanır (təhlükəsizlik auditi 2026-10-05).

``visible_to_all`` sualı bütün tenant-lara görünürdü. Sahə nullable-dır: köhnə
sətirlər NULL qalır (tətbiq qatında yalnız müəllifi və superadmin görür).

RLS (yalnız PostgreSQL): ``organization_id`` sütunu olan hər cədvəlin tenant
siyasəti olmalıdır (``core/tests/test_audit_2026_09_13_rls_coverage.py``).
Siyasət ``ai_assistant/0003`` formasındadır — NULL org (köhnə sətir) oxunur,
qalanı yalnız cari təşkilatda.
"""

import django.db.models.deletion
from django.db import migrations, models

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_TABLE = "blog_question"
_CONDITION = f"{_BYPASS_EXPR} OR organization_id IS NULL OR organization_id::text = {_CURRENT_ORG}"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING ({_CONDITION})
    WITH CHECK ({_CONDITION});
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
        ("blog", "0005_post_indexes"),
        ("organizations", "0056_system_monitoring_view_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="blog_questions",
                to="organizations.organization",
            ),
        ),
        migrations.RunPython(_apply, _revert),
    ]
