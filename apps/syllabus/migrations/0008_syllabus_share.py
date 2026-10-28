"""Bir sillabus — bir neçə jurnal: ``SyllabusShare`` + RLS + eyni-təşkilat qoruyucuları (sahib 2026-10-27).

``registrar.0105_journal_share`` naxışı:

1. **Cədvəl** — sillabusu öz yerində istifadə edən əlavə açılış; bir açılış ən çox bir paylaşıma bağlanır.
2. **RLS / FORCE RLS** — birbaşa ``organization_id`` izolyasiyası.
3. **DB qoruyucuları** — paylaşımın açılışı və sillabusu öz təşkilatına aid olmalıdır (mövcud
   ``registrar_guard_same_org_fk`` funksiyası təkrar işlədilir).

Qeyri-PostgreSQL backend-lərdə RunPython no-op-dur; tam geri qaytarılandır.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_TABLE = "syllabus_syllabusshare"
_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_ORG_EXPR = f"organization_id::text = {_CURRENT_ORG}"
_GUARDS = (
    ("syllabus_share_offering_same_org", "offering_id", "registrar_courseoffering", "syllabus share offering"),
    ("syllabus_share_syllabus_same_org", "syllabus_id", "syllabus_syllabus", "syllabus share syllabus"),
)


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
    for name, field, parent, label in _GUARDS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{_TABLE}", params=None)
        schema_editor.execute(
            f"CREATE TRIGGER {name} "
            f"BEFORE INSERT OR UPDATE OF {field}, organization_id ON public.{_TABLE} "
            f"FOR EACH ROW EXECUTE FUNCTION public.registrar_guard_same_org_fk('{field}', '{parent}', '{label}')",
            params=None,
        )


def _revert(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for name, _field, _parent, _label in _GUARDS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON public.{_TABLE}", params=None)
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
        ("organizations", "0074_tutor_laborant_unit_view"),
        ("registrar", "0106_journal_mark_guard_open_presence"),
        ("syllabus", "0007_syllabus_plan_hours_override"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SyllabusShare",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("teacher", "Müəllimin seçimi"),
                            ("legacy", "Köhnə sistem (bir sillabus bir neçə jurnalda)"),
                        ],
                        default="teacher",
                        max_length=16,
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
                    "offering",
                    models.ForeignKey(
                        db_index=False,
                        help_text="Sillabusu öz yerində istifadə edən açılış (jurnal) — dosyenin öz açılışı DEYİL.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="syllabus_shares",
                        to="registrar.courseoffering",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        db_index=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="syllabus_shares",
                        to="organizations.organization",
                    ),
                ),
                (
                    "syllabus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="shares", to="syllabus.syllabus"
                    ),
                ),
            ],
            options={
                "verbose_name": "paylaşılan sillabus",
                "verbose_name_plural": "paylaşılan sillabuslar",
                "ordering": ["created_at"],
                "indexes": [models.Index(fields=["organization", "syllabus"], name="syllabus_share_org_syl")],
                "constraints": [
                    models.UniqueConstraint(fields=("offering",), name="uniq_syllabus_share_offering"),
                    models.CheckConstraint(
                        condition=models.Q(("source__in", ["teacher", "legacy"])), name="syllabus_share_source_valid"
                    ),
                ],
            },
        ),
        migrations.RunPython(_apply, _revert),
    ]
