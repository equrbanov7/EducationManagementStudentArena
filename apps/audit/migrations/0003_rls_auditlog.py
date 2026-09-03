"""``audit_auditlog`` üçün OXU səviyyəli tenant izolyasiyası (RLS).

Kontekst (2026-09-02 auditi, D bölməsi)
--------------------------------------
Klonda ``organization_id`` sütunu daşıyan 79 cədvəldən 75-inin RLS siyasəti var
idi; ``audit_auditlog`` (22 301 sətir) qorunmayan dördlükdən biri idi — yəni
kim-nə-etdi izi DB səviyyəsində tenantlar arasında açıq qalırdı.

Siyasətin FORMASI niyə asimmetrikdir
------------------------------------
``USING`` (OXU) — tam tenant filtri::

    bypass  OR  organization_id IS NULL  OR  organization_id = current_org

NULL org QƏSDƏN buraxılır: platforma səviyyəli hadisələr (login/logout, admin
2FA, superadmin cross-org qeydləri) heç bir tenanta aid deyil.  Bu,
``notifications.0005`` ilə eyni fail-closed naxışdır — NULL artıq «unudulmuş
sahə» yox, açıq qərar sayılır.

``WITH CHECK`` (YAZI) — **permissiv**.  Səbəb təhlükəsizlik mühakiməsidir, süstlük
deyil:

* ``core.audit.log_action`` audit sətrini SERVER yazır; dəyər heç vaxt
  istifadəçi girişindən gəlmir, ona görə «yad org id ilə sətir uydurmaq»
  vektoru yoxdur.
* Həmin funksiya ``bypass_rls()`` sarğısı ilə çağırılmır və onlarla axından
  (middleware, Celery, management əmrləri, ``log_superadmin_cross_org_action``
  — sonuncu QƏSDƏN başqa tenantın org-u ilə yazır) işə düşür.  Sərt
  ``WITH CHECK`` həmin INSERT-ləri rədd edərdi; çağıranların çoxu isə audit
  yazısını ``except`` içində udur → nəticə SƏSSİZ İZ İTKİSİ olardı, yəni
  qoruma özü auditi məhv edərdi.
* Sətirlərin dəyişməzliyi onsuz da DB tərəfdə təmin olunur:
  ``organizations.0019_audit_log_append_only`` UPDATE/DELETE triggerləri.

Superadmin oxu səthləri (``apps/audit/views.py``) açıq ``bypass_rls()`` ilə
işləyir — platforma administratoru bütün tenantları görməyə davam edir.
"""

from django.db import migrations

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"

_TABLE = "audit_auditlog"

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
        ("audit", "0002_alter_auditlog_action"),
        # RLS köməkçi rolu (``rls_app_role``) və GUC konvensiyası burada yaranır.
        ("organizations", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunPython(_apply, _revert),
    ]
