"""``ai_assistant_aiassistantlog`` üçün OXU səviyyəli tenant izolyasiyası (RLS).

2026-09-02 auditi (D bölməsi): ``organization_id`` daşıyan 79 cədvəldən dördü
RLS-siz idi; bu, onlardan biridir.

AI köməkçisinin sorğu jurnalı istifadəçinin PROMPT mətnini saxlayır — yəni
tenant məzmunu.  Cədvəl klonda boşdur, ona görə siyasəti indi qoymaq ən ucuz
andır.

Siyasət ``apps/audit/migrations/0003_rls_auditlog.py`` ilə eyni formadadır:
``USING`` tenant filtridir (NULL org = qəsdən platforma-səviyyəli sətir),
``WITH CHECK`` isə permissivdir — sətirləri SERVER yazır, yazı yolu
``bypass_rls()`` ilə sarınmayıb və sərt yoxlama telemetriyanı səssizcə
itirərdi.  Postgres xaricində no-op.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_TABLE = "ai_assistant_aiassistantlog"

_READ_CONDITION = (
    f"{_BYPASS_EXPR}\n" "        OR organization_id IS NULL\n" f"        OR organization_id::text = {_CURRENT_ORG}"
)

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_READ_CONDITION}
    )
    WITH CHECK (true);
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
        ("ai_assistant", "0002_rename_ai_assistant_user_cr_idx_ai_assistan_user_id_59dc22_idx_and_more"),
        ("organizations", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
