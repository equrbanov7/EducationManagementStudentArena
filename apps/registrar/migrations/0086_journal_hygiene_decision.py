"""«Jurnal təmizliyi» qərar jurnalı — ``JournalHygieneDecision`` + RLS + append-only qoruyucu (sahib 2026-10-10).

Üç qat (``0058_teaching_handover`` / ``0067_rls_student_movement`` naxışı):

1. **Cədvəl** — qeydiyyatın status qərarı (kateqoriya, köhnə → yeni status, sübut + sha256, aktor, səbəb).
2. **RLS / FORCE RLS** — birbaşa ``organization_id`` izolyasiyası.
3. **DB qoruyucuları**:
   * ``registrar_journal_hygiene_decision_guard`` — DELETE qadağandır; UPDATE yalnız BİR DƏFƏ və yalnız
     geri qaytarma sahələrinə (``reverted_at`` / ``reverted_by_id`` / ``reverted_by_name`` /
     ``revert_reason`` / ``updated_at``) toxuna bilər. İstisna: hesab silinəndə Django-nun ``SET_NULL``
     emulyasiyası aktor FK-larını NULL edir — yalnız bu keçid (başqa heç nə dəyişmədən) buraxılır.
   * ``registrar_hygiene_same_org_guard`` — qərarın qeydiyyatı öz təşkilatına aid olmalıdır (mövcud
     ``registrar_guard_same_org_fk`` funksiyası təkrar işlədilir).

Qeyri-PostgreSQL backend-lərdə RunPython no-op-dur; tam geri qaytarılandır.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "registrar_journalhygienedecision"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"

_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION public.registrar_journal_hygiene_decision_guard()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $function$
DECLARE
    revert_columns text[] := ARRAY['reverted_at', 'reverted_by_id', 'reverted_by_name', 'revert_reason', 'updated_at'];
    actor_columns text[] := ARRAY['decided_by_id', 'reverted_by_id'];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'registrar_journalhygienedecision append-only: DELETE is not allowed'
            USING ERRCODE = '23514';
    END IF;

    -- Hesab silinir: Django SET_NULL emulyasiyası yalnız aktor FK-larını NULL edir.
    IF (to_jsonb(NEW) - actor_columns) = (to_jsonb(OLD) - actor_columns)
       AND (NEW.decided_by_id IS NULL OR NEW.decided_by_id = OLD.decided_by_id)
       AND (NEW.reverted_by_id IS NULL OR NEW.reverted_by_id IS NOT DISTINCT FROM OLD.reverted_by_id) THEN
        RETURN NEW;
    END IF;

    IF OLD.reverted_at IS NOT NULL THEN
        RAISE EXCEPTION 'registrar_journalhygienedecision: decision is already reverted'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.reverted_at IS NULL THEN
        RAISE EXCEPTION 'registrar_journalhygienedecision append-only: only the one-time revert is allowed'
            USING ERRCODE = '23514';
    END IF;
    IF (to_jsonb(NEW) - revert_columns) IS DISTINCT FROM (to_jsonb(OLD) - revert_columns) THEN
        RAISE EXCEPTION 'registrar_journalhygienedecision append-only: decision fields are immutable'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
"""


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # ⚠️ `params=None`: plpgsql gövdəsi psycopg interpolyasiyasına düşməsin (0067 şərhi).
    schema_editor.execute(
        f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING ({_BYPASS_EXPR} OR {_ORG_EXPR})
    WITH CHECK ({_BYPASS_EXPR} OR {_ORG_EXPR});
""",
        params=None,
    )
    schema_editor.execute(_GUARD_SQL, params=None)
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS registrar_journal_hygiene_decision_guard ON public.{_TABLE}", params=None
    )
    schema_editor.execute(
        f"CREATE TRIGGER registrar_journal_hygiene_decision_guard BEFORE UPDATE OR DELETE ON public.{_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_journal_hygiene_decision_guard()",
        params=None,
    )
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_hygiene_same_org_guard ON public.{_TABLE}", params=None)
    schema_editor.execute(
        "CREATE TRIGGER registrar_hygiene_same_org_guard "
        f"BEFORE INSERT OR UPDATE OF enrollment_id, organization_id ON public.{_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk("
        "'enrollment_id', 'registrar_enrollment', 'journal hygiene enrollment')",
        params=None,
    )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_hygiene_same_org_guard ON public.{_TABLE}", params=None)
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS registrar_journal_hygiene_decision_guard ON public.{_TABLE}", params=None
    )
    schema_editor.execute("DROP FUNCTION IF EXISTS public.registrar_journal_hygiene_decision_guard()", params=None)
    schema_editor.execute(
        f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
""",
        params=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0057_capacity_drop_unused_indexes"),
        ("registrar", "0085_capacity_drop_unused_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="JournalHygieneDecision",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("batch", models.UUIDField()),
                (
                    "category",
                    models.CharField(
                        choices=[("left_student", "Ayrılmış tələbə"), ("empty_subject", "Boş fənn")], max_length=24
                    ),
                ),
                ("reason_code", models.CharField(max_length=32)),
                ("from_status", models.CharField(max_length=16)),
                ("to_status", models.CharField(max_length=16)),
                (
                    "evidence",
                    models.JSONField(default=dict, help_text="Qərar anındakı sübut snapshot-u (saylar, etiketlər)."),
                ),
                ("evidence_digest", models.CharField(help_text="Sübut snapshot-unun sha256 izi.", max_length=64)),
                ("reason", models.TextField(help_text="Qərarın səbəbi — ən azı 20 simvol.")),
                ("decided_by_name", models.CharField(blank=True, default="", max_length=200)),
                ("reverted_at", models.DateTimeField(blank=True, null=True)),
                ("reverted_by_name", models.CharField(blank=True, default="", max_length=200)),
                ("revert_reason", models.TextField(blank=True, default="")),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "enrollment",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="hygiene_decisions",
                        to="registrar.enrollment",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="journal_hygiene_decisions",
                        to="organizations.organization",
                    ),
                ),
                (
                    "reverted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "journal hygiene decision",
                "verbose_name_plural": "journal hygiene decisions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["organization", "-created_at"], name="reg_hygiene_org_created"),
                    models.Index(fields=["enrollment", "-created_at"], name="reg_hygiene_enrollment"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("category__in", ["left_student", "empty_subject"])),
                        name="reg_hygiene_category_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("to_status__in", ["suspended", "dropped"])),
                        name="reg_hygiene_to_status_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("revert_reason", ""), ("reverted_at__isnull", True)),
                            models.Q(("reverted_at__isnull", False), models.Q(("revert_reason", ""), _negated=True)),
                            _connector="OR",
                        ),
                        name="reg_hygiene_revert_complete",
                    ),
                ],
            },
        ),
        migrations.RunPython(_apply, _revert),
    ]
