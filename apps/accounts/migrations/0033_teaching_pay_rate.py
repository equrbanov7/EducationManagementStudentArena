"""«Dərs saatının ödəniş dərəcələri» (Mühasibatlıq, sahib 2026-10-19) — ``TeachingPayRate`` cədvəli.

* ``rls_tenant_isolation`` (ENABLE + FORCE) — ``organization_id`` sütunlu hər cədvəl kimi.
* TARİXÇƏ QORUYUCUSU (``accounts_guard_pay_rate_history``): DELETE həmişə bloklanır (keçmiş ixracda istifadə
  olunmuş dərəcə itməsin); UPDATE yalnız aktiv sətri BİR DƏFƏ arxivləyə bilər (``archived_at`` / səbəb / kim) və
  istifadəçi silinəndə ``created_by`` / ``archived_by`` FK-sının NULL-a düşməsinə icazə verir — dərəcə, il, vəzifə,
  növ, qeyd, id dəyişmir; ``archive_reason`` CHECK ilə «» / replaced / removed. TRUNCATE yalnız superuser və ya boş cədvəl üçün (test flush-u; registrar 0091 naxışı).
Postgres olmayan backend-də RunPython no-op-dur.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "accounts_teachingpayrate"
_BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
_ORG = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"

_GUARD_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.accounts_guard_pay_rate_history()
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
        RAISE EXCEPTION USING MESSAGE = 'teaching pay rate history is append-only: TRUNCATE', ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING MESSAGE = 'teaching pay rate history is append-only: DELETE', ERRCODE = '23514';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
        OR NEW.academic_year IS DISTINCT FROM OLD.academic_year
        OR NEW.position IS DISTINCT FROM OLD.position
        OR NEW.activity IS DISTINCT FROM OLD.activity
        OR NEW.hourly_rate IS DISTINCT FROM OLD.hourly_rate
        OR NEW.note IS DISTINCT FROM OLD.note
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
        OR NEW.created_by_name IS DISTINCT FROM OLD.created_by_name
        OR (NEW.created_by_id IS DISTINCT FROM OLD.created_by_id AND NEW.created_by_id IS NOT NULL) THEN
        RAISE EXCEPTION USING MESSAGE = 'teaching pay rate is immutable — archive it and add a new rate',
            ERRCODE = '23514';
    END IF;
    IF OLD.archived_at IS NOT NULL THEN
        IF NEW.archived_at IS DISTINCT FROM OLD.archived_at
            OR NEW.archive_reason IS DISTINCT FROM OLD.archive_reason
            OR NEW.archived_by_name IS DISTINCT FROM OLD.archived_by_name
            OR (NEW.archived_by_id IS DISTINCT FROM OLD.archived_by_id AND NEW.archived_by_id IS NOT NULL) THEN
            RAISE EXCEPTION USING MESSAGE = 'archived teaching pay rate cannot change', ERRCODE = '23514';
        END IF;
    ELSIF NEW.archived_at IS NOT NULL AND COALESCE(NEW.archive_reason, '') = '' THEN
        RAISE EXCEPTION USING MESSAGE = 'archiving a teaching pay rate needs a reason', ERRCODE = '23514';
    ELSIF NEW.archived_at IS NULL AND (COALESCE(NEW.archive_reason, '') <> '' OR NEW.archived_by_id IS NOT NULL) THEN
        RAISE EXCEPTION USING MESSAGE = 'archive fields need archived_at', ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION public.accounts_guard_pay_rate_history() FROM PUBLIC;
"""


def _apply_security(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE public.{_TABLE} ENABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE public.{_TABLE} FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON public.{_TABLE}")
    schema_editor.execute(
        f"CREATE POLICY rls_tenant_isolation ON public.{_TABLE} "
        f"USING ({_BYPASS} OR {_ORG}) WITH CHECK ({_BYPASS} OR {_ORG})"
    )
    schema_editor.execute(_GUARD_FUNCTION)
    for op, scope in (("update", "ROW"), ("delete", "ROW"), ("truncate", "STATEMENT")):
        schema_editor.execute(
            f"CREATE TRIGGER accounts_pay_rate_history_{op} BEFORE {op.upper()} ON public.{_TABLE} "
            f"FOR EACH {scope} EXECUTE FUNCTION public.accounts_guard_pay_rate_history()"
        )


def _revert_security(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for op in ("update", "delete", "truncate"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS accounts_pay_rate_history_{op} ON public.{_TABLE}")
    schema_editor.execute("DROP FUNCTION IF EXISTS public.accounts_guard_pay_rate_history()")
    schema_editor.execute(f"DROP POLICY IF EXISTS rls_tenant_isolation ON public.{_TABLE}")
    schema_editor.execute(f"ALTER TABLE public.{_TABLE} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE public.{_TABLE} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0032_profile_fin_self_reported"),
        ("organizations", "0069_hr_contract_permissions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TeachingPayRate",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "academic_year",
                    models.CharField(help_text="Məs. «2026/2027» (AcademicPeriod.academic_year).", max_length=20),
                ),
                (
                    "position",
                    models.CharField(help_text="workload.TeacherWorkloadProfile.position açarı.", max_length=32),
                ),
                (
                    "activity",
                    models.CharField(
                        blank=True, help_text="lecture / seminar / lab; boş — bütün növlər.", max_length=16
                    ),
                ),
                (
                    "hourly_rate",
                    models.DecimalField(decimal_places=2, help_text="1 akademik saatın dərəcəsi (AZN).", max_digits=10),
                ),
                ("note", models.CharField(blank=True, max_length=300)),
                ("created_by_name", models.CharField(blank=True, max_length=200)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("archived_by_name", models.CharField(blank=True, max_length=200)),
                (
                    "archive_reason",
                    models.CharField(
                        blank=True,
                        choices=[("replaced", "Yeni dərəcə ilə əvəzləndi"), ("removed", "Ləğv edildi")],
                        max_length=16,
                    ),
                ),
                (
                    "archived_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="organizations.organization"
                    ),
                ),
            ],
            options={
                "verbose_name": "teaching pay rate",
                "verbose_name_plural": "teaching pay rates",
                "ordering": ["-academic_year", "position", "activity", "-created_at"],
                "indexes": [models.Index(fields=["organization", "academic_year"], name="acc_pay_rate_org_year_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("archived_at__isnull", True)),
                        fields=("organization", "academic_year", "position", "activity"),
                        name="accounts_pay_rate_active_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("hourly_rate__gt", 0)), name="accounts_pay_rate_positive"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("activity__in", ("", "lecture", "seminar", "lab"))),
                        name="accounts_pay_rate_activity_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("archive_reason__in", ("", "replaced", "removed"))),
                        name="accounts_pay_rate_archive_reason_valid",
                    ),
                ],
            },
        ),
        migrations.RunPython(_apply_security, _revert_security),
    ]
