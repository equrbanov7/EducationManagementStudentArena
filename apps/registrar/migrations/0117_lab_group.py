"""Jurnalın laboratoriya qrupu — ``LabGroup`` (nömrə + ad) + RLS + eyni-təşkilat qoruyucusu (sahib 2026-11-06).

``0105_journal_share`` naxışı:

1. **Cədvəl** — açılış × nömrə üzrə BİR sətir (unikal), nömrə 1..9 (CHECK), ad istəyə bağlı.
2. **RLS / FORCE RLS** — birbaşa ``organization_id`` izolyasiyası.
3. **DB qoruyucusu** ``registrar_labgroup_same_org_guard`` — qrupun açılışı öz təşkilatına aid olmalıdır
   (mövcud ``registrar_guard_same_org_fk`` funksiyası təkrar işlədilir).

Data köçürülmür: mövcud Lab-1 / Lab-2 (``Enrollment.lab_group``, sətirsiz) ``lab_groups.offering_groups``-da
siyahıdan oxunur və «Lab-N» adı ilə görünür. Qeyri-PostgreSQL backend-lərdə RunPython no-op-dur; tam geri
qaytarılandır.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models

_TABLE = "registrar_labgroup"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"


def _apply(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
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
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_labgroup_same_org_guard ON public.{_TABLE}", params=None)
    schema_editor.execute(
        "CREATE TRIGGER registrar_labgroup_same_org_guard "
        f"BEFORE INSERT OR UPDATE OF offering_id, organization_id ON public.{_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk("
        "'offering_id', 'registrar_courseoffering', 'lab group offering')",
        params=None,
    )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_labgroup_same_org_guard ON public.{_TABLE}", params=None)
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
        ("organizations", "0073_grade_event_attempt_purge_exception"),
        ("registrar", "0116_lab_groups"),
    ]

    operations = [
        migrations.CreateModel(
            name="LabGroup",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "number",
                    models.PositiveSmallIntegerField(
                        help_text="Qrup nömrəsi (Enrollment.lab_group / Lesson.lab_group)."
                    ),
                ),
                (
                    "name",
                    models.CharField(blank=True, default="", help_text="Görünən ad; boş = «Lab-N».", max_length=40),
                ),
                (
                    "offering",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lab_groups",
                        to="registrar.courseoffering",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lab_groups",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "verbose_name": "laboratoriya qrupu",
                "verbose_name_plural": "laboratoriya qrupları",
                "ordering": ["offering_id", "number"],
                "constraints": [
                    models.UniqueConstraint(fields=("offering", "number"), name="reg_labgroup_offering_number_uniq"),
                    models.CheckConstraint(
                        condition=models.Q(("number__gte", 1), ("number__lte", 9)), name="reg_labgroup_number_range"
                    ),
                ],
            },
        ),
        migrations.RunPython(_apply, _revert),
    ]
