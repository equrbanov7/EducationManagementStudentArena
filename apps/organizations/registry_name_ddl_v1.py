"""Frozen PostgreSQL guard for 0089 installations with pre-existing duplicate keys."""

# A separate schema keeps the folded names and reservation rows outside the
# production role's grants on all tables in public. Only fixed-path trigger
# functions can change a reservation on behalf of an ordinary OrgUnit writer.
_SETUP = r"""
CREATE SCHEMA ems_registry_guard;
REVOKE ALL ON SCHEMA ems_registry_guard FROM PUBLIC;

CREATE TABLE ems_registry_guard.reservation (
    organization_id uuid NOT NULL,
    faculty boolean NOT NULL,
    name_key text COLLATE pg_catalog."C" NOT NULL,
    occupants bigint NOT NULL CHECK (occupants >= 0),
    CONSTRAINT orgunit_active_registry_name_uniq PRIMARY KEY (organization_id, faculty, name_key)
);

CREATE FUNCTION ems_registry_guard.name_key(text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = pg_catalog, pg_temp AS $key$
    SELECT lower(normalize(btrim($1, U&'__TRIM__')) COLLATE pg_catalog."az-x-icu")
$key$;

INSERT INTO ems_registry_guard.reservation (organization_id, faculty, name_key, occupants)
SELECT organization_id, unit_type = 'faculty', ems_registry_guard.name_key(name) COLLATE pg_catalog."C", count(*)
FROM public.organizations_orgunit
WHERE is_active AND unit_type IN ('faculty', 'chair', 'department')
GROUP BY 1, 2, 3;

CREATE FUNCTION ems_registry_guard.track() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $track$
DECLARE
    old_key text COLLATE pg_catalog."C";
    new_key text COLLATE pg_catalog."C";
    remaining bigint;
BEGIN
    -- Use the resulting row, including changes made by other BEFORE triggers.
    IF TG_OP = 'UPDATE' AND OLD.name COLLATE pg_catalog."C" = NEW.name COLLATE pg_catalog."C"
       AND OLD.organization_id = NEW.organization_id AND OLD.is_active = NEW.is_active
       AND OLD.unit_type = NEW.unit_type THEN
        RETURN NULL;
    END IF;
    IF TG_OP <> 'INSERT' AND OLD.is_active AND OLD.unit_type IN ('faculty', 'chair', 'department') THEN
        old_key := ems_registry_guard.name_key(OLD.name);
    END IF;
    IF TG_OP <> 'DELETE' AND NEW.is_active AND NEW.unit_type IN ('faculty', 'chair', 'department') THEN
        new_key := ems_registry_guard.name_key(NEW.name);
    END IF;

    IF old_key IS NOT NULL AND new_key IS NOT NULL AND old_key = new_key
       AND OLD.organization_id = NEW.organization_id AND (OLD.unit_type = 'faculty') = (NEW.unit_type = 'faculty') THEN
        RETURN NULL;
    END IF;
    IF old_key IS NOT NULL THEN
        UPDATE ems_registry_guard.reservation SET occupants = occupants - 1
        WHERE organization_id = OLD.organization_id AND faculty = (OLD.unit_type = 'faculty') AND name_key = old_key
        RETURNING occupants INTO STRICT remaining;
        IF remaining = 0 THEN
            DELETE FROM ems_registry_guard.reservation
            WHERE organization_id = OLD.organization_id AND faculty = (OLD.unit_type = 'faculty') AND name_key = old_key;
        END IF;
    END IF;
    IF new_key IS NOT NULL THEN
        -- The real unique index arbitrates even uncommitted inserts. Conflicts
        -- roll back the entire OrgUnit statement, including an old-key release.
        INSERT INTO ems_registry_guard.reservation (organization_id, faculty, name_key, occupants)
        VALUES (NEW.organization_id, NEW.unit_type = 'faculty', new_key, 1);
    END IF;
    RETURN NULL;
END
$track$;

CREATE FUNCTION ems_registry_guard.clear() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $clear$
BEGIN
    TRUNCATE ems_registry_guard.reservation;
    RETURN NULL;
END
$clear$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ems_registry_guard FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA ems_registry_guard FROM PUBLIC;
CREATE TRIGGER orgunit_registry_name_guard
AFTER INSERT OR DELETE OR UPDATE
ON public.organizations_orgunit FOR EACH ROW EXECUTE FUNCTION ems_registry_guard.track();
CREATE TRIGGER orgunit_registry_name_truncate
AFTER TRUNCATE ON public.organizations_orgunit FOR EACH STATEMENT EXECUTE FUNCTION ems_registry_guard.clear();
"""

_REMOVE = """
DROP TRIGGER orgunit_registry_name_guard ON public.organizations_orgunit;
DROP TRIGGER orgunit_registry_name_truncate ON public.organizations_orgunit;
DROP FUNCTION ems_registry_guard.track();
DROP FUNCTION ems_registry_guard.clear();
DROP FUNCTION ems_registry_guard.name_key(text);
DROP TABLE ems_registry_guard.reservation;
DROP SCHEMA ems_registry_guard;
"""


def create_sql(native, trim_chars):
    escapes = "".join(f"\\{ord(char):04x}" for char in trim_chars)
    setup = _SETUP.replace("__TRIM__", escapes)
    return f"""
        DO $registry_migration$
        BEGIN
            SET LOCAL app.bypass_rls = 'on';
            LOCK TABLE public.organizations_orgunit IN SHARE ROW EXCLUSIVE MODE;
            -- An older release rolling 0089 back knows only the public index:
            -- its DROP INDEX IF EXISTS leaves the working compatibility guard intact.
            IF to_regclass('ems_registry_guard.reservation') IS NOT NULL AND EXISTS (
                SELECT 1 FROM pg_catalog.pg_trigger
                WHERE tgrelid = 'public.organizations_orgunit'::regclass AND tgname = 'orgunit_registry_name_guard'
                  AND tgfoid = to_regprocedure('ems_registry_guard.track()') AND tgenabled IN ('O', 'A')
            ) AND EXISTS (
                SELECT 1 FROM pg_catalog.pg_trigger
                WHERE tgrelid = 'public.organizations_orgunit'::regclass AND tgname = 'orgunit_registry_name_truncate'
                  AND tgfoid = to_regprocedure('ems_registry_guard.clear()') AND tgenabled IN ('O', 'A')
            ) THEN
                RETURN;
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.organizations_orgunit
                WHERE is_active AND unit_type IN ('faculty', 'chair', 'department')
                GROUP BY organization_id, (unit_type = 'faculty'),
                         lower(normalize(btrim(name, U&'{escapes}')) COLLATE pg_catalog."az-x-icu") COLLATE pg_catalog."C"
                HAVING count(*) > 1
            ) THEN
                {setup}
            ELSE
                {native};
            END IF;
        END
        $registry_migration$
    """


def remove_sql(native):
    return f"""
        DO $registry_migration$
        BEGIN
            LOCK TABLE public.organizations_orgunit IN SHARE ROW EXCLUSIVE MODE;
            IF to_regnamespace('ems_registry_guard') IS NOT NULL THEN
                {_REMOVE}
            ELSE
                {native};
            END IF;
        END
        $registry_migration$
    """
