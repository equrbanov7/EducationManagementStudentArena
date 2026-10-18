"""«Əmək müqavilələri» — RLS + APPEND-ONLY hadisə jurnalı + eyni-təşkilat FK trigger-ləri (sahib 2026-10-19).

* Hər iki cədvəl ``organization_id`` daşıyır → ``rls_tenant_isolation`` siyasəti (ENABLE + FORCE; registrar 0091 ilə
  EYNİ ifadə; əhatə testi ``core/tests/test_audit_2026_09_13_rls_coverage.py``).
* ``hr_contracts_employmentcontractevent`` APPEND-ONLY: UPDATE/DELETE həmişə, TRUNCATE yalnız cədvəl boş deyilsə
  və superuser deyilsə bloklanır (test flush-u boş cədvəli sərbəst təmizləyir).
* Cədvəllərarası FK-lar (müqavilənin bölməsi, yenilənmə zənciri, hadisə → müqavilə) EYNİ təşkilatda olmalıdır —
  ÖZ funksiyamız ``hr_contracts_guard_same_org_fk`` (registrar funksiyası bilərəkdən işlədilmir: registrar-ın
  trigger sayı testi və modul sərhədi toxunulmaz qalsın).
* SQL-də ``%`` işarəsi QƏSDƏN yoxdur (``schema_editor.execute`` parametr interpolyasiyası). Postgres olmayan
  backend-də no-op.
"""

from django.db import migrations

_TABLES = ("hr_contracts_employmentcontract", "hr_contracts_employmentcontractevent")
_EVENT_TABLE = "hr_contracts_employmentcontractevent"
_SAME_ORG_LINKS = (
    ("hr_contracts_employmentcontract", "unit_id", "organizations_orgunit", "contract unit"),
    ("hr_contracts_employmentcontract", "renewed_by_id", "hr_contracts_employmentcontract", "contract renewal"),
    ("hr_contracts_employmentcontractevent", "contract_id", "hr_contracts_employmentcontract", "contract event"),
)

_BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
_ORG = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"

_FUNCTIONS = r"""
CREATE OR REPLACE FUNCTION public.hr_contracts_guard_same_org_fk()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    relation_id uuid;
    parent_organization uuid;
BEGIN
    relation_id := NULLIF(to_jsonb(NEW) ->> TG_ARGV[0], '')::uuid;
    IF relation_id IS NULL THEN
        RETURN NEW;
    END IF;
    EXECUTE 'SELECT organization_id FROM public.' || quote_ident(TG_ARGV[1]) || ' WHERE id = $1'
        INTO parent_organization USING relation_id;
    IF parent_organization IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION USING
            MESSAGE = 'hr_contracts parent must belong to the same organization: ' || TG_ARGV[2],
            ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.hr_contracts_guard_same_org_fk() FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.hr_contracts_guard_append_only()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    has_rows boolean;
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        IF COALESCE((SELECT usesuper FROM pg_user WHERE usename = session_user), false) THEN
            RETURN NULL;
        END IF;
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM ' || quote_ident(TG_TABLE_SCHEMA) || '.'
            || quote_ident(TG_TABLE_NAME) || ')' INTO has_rows;
        IF NOT has_rows THEN
            RETURN NULL;
        END IF;
    END IF;
    RAISE EXCEPTION USING MESSAGE = 'hr_contracts history is append-only: ' || TG_OP, ERRCODE = '23514';
END;
$function$;
REVOKE ALL ON FUNCTION public.hr_contracts_guard_append_only() FROM PUBLIC;
"""


def _trigger_name(table, field):
    short = "event" if table == _EVENT_TABLE else "contract"
    return f"hr_contracts_same_org_{short}_{field.removesuffix('_id')}"


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON public.{table}")
        schema_editor.execute(
            f"CREATE POLICY rls_tenant_isolation ON public.{table} "
            f"USING ({_BYPASS} OR {_ORG}) WITH CHECK ({_BYPASS} OR {_ORG})"
        )
    schema_editor.execute(_FUNCTIONS)
    for table, field, parent, label in _SAME_ORG_LINKS:
        schema_editor.execute(
            f"CREATE TRIGGER {_trigger_name(table, field)} "
            f"BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.hr_contracts_guard_same_org_fk('{field}', '{parent}', '{label}')"
        )
    for op, scope in (("update", "ROW"), ("delete", "ROW"), ("truncate", "STATEMENT")):
        schema_editor.execute(
            f"CREATE TRIGGER hr_contracts_event_append_only_{op} BEFORE {op.upper()} ON public.{_EVENT_TABLE} "
            f"FOR EACH {scope} EXECUTE FUNCTION public.hr_contracts_guard_append_only()"
        )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for op in ("update", "delete", "truncate"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS hr_contracts_event_append_only_{op} ON public.{_EVENT_TABLE}")
    for table, field, _parent, _label in _SAME_ORG_LINKS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {_trigger_name(table, field)} ON public.{table}")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.hr_contracts_guard_append_only()")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.hr_contracts_guard_same_org_fk()")
    for table in _TABLES:
        schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON public.{table}")
        schema_editor.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):

    dependencies = [("hr_contracts", "0001_initial")]

    operations = [migrations.RunPython(_apply, _revert)]
