"""Bölünmüş jurnal — ``JournalShare`` + RLS + eyni-təşkilat qoruyucusu (sahib 2026-10-26).

``0086_journal_hygiene_decision`` naxışı:

1. **Cədvəl** — açılış × müəllim payı (dərs növləri + tələbələr; boş = hamısı), bir AKTİV sətir.
2. **RLS / FORCE RLS** — birbaşa ``organization_id`` izolyasiyası.
3. **DB qoruyucusu** ``registrar_share_same_org_guard`` — payın açılışı öz təşkilatına aid olmalıdır
   (mövcud ``registrar_guard_same_org_fk`` funksiyası təkrar işlədilir).

M2M ara cədvəli (``registrar_journalshare_enrollments``) ``organization_id`` daşımır — ona yalnız RLS-li
ana sətir üzərindən çatılır; tələbələrin açılışa aidliyi servis qatında yoxlanır.

Qeyri-PostgreSQL backend-lərdə RunPython no-op-dur; tam geri qaytarılandır.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "registrar_journalshare"
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
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_share_same_org_guard ON public.{_TABLE}", params=None)
    schema_editor.execute(
        "CREATE TRIGGER registrar_share_same_org_guard "
        f"BEFORE INSERT OR UPDATE OF offering_id, organization_id ON public.{_TABLE} "
        "FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk("
        "'offering_id', 'registrar_courseoffering', 'journal share offering')",
        params=None,
    )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP TRIGGER IF EXISTS registrar_share_same_org_guard ON public.{_TABLE}", params=None)
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
        ("registrar", "0104_exam_score_assessment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="JournalShare",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kinds", models.JSONField(blank=True, default=list)),
                (
                    "source",
                    models.CharField(
                        choices=[("legacy", "Köhnə sistem"), ("manual", "Əl ilə")], default="manual", max_length=16
                    ),
                ),
                ("batch", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("is_active", models.BooleanField(default=True)),
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
                    "enrollments",
                    models.ManyToManyField(blank=True, related_name="journal_shares", to="registrar.enrollment"),
                ),
                (
                    "offering",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shares",
                        to="registrar.courseoffering",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="journal_shares",
                        to="organizations.organization",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="journal_shares",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "jurnal payı",
                "verbose_name_plural": "jurnal payları",
                "ordering": ["offering_id", "created_at"],
                "indexes": [models.Index(fields=["organization", "teacher"], name="reg_share_org_teacher")],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("offering", "teacher"),
                        name="reg_share_active_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("source__in", ["legacy", "manual"])), name="reg_share_source_valid"
                    ),
                ],
            },
        ),
        migrations.RunPython(_apply, _revert),
    ]
