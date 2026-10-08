"""Sual göndərişi → REYESTR qrupları (``OrgUnit`` GROUP) M2M — müəllim rəyi S2 davamı, 2026-10-08.

Fənn/qrup siyahısı indi müəllimin dərs yükündən gəlir; reyestr qrupu ilə göndərilən
dəstin köhnə kohort FK-sı yoxdur və o, mərkəzin fakültə/kafedra süzgəcinə düşmürdü.

1. ``registry_groups`` M2M sahəsi;
2. join cədvəlinə RLS (organizations 0020 «cross-FK» forması): göndəriş və vahid EYNİ
   təşkilatın və CARİ təşkilatın olmalıdır; ``USING`` + ``WITH CHECK`` + ``FORCE``;
   qeyri-PostgreSQL → no-op; geri qaytarıla bilir;
3. backfill: mövcud göndərişlərin ``group_label``-indəki adlar (vergüllə) təşkilatda
   TƏK bir reyestr qrupuna uyğun gəlirsə bağlanır. Göndərişin köhnə kohortlarının
   adları və birdən çox qrupa uyğun gələn adlar (qeyri-müəyyən) atlanır — uydurma bağ
   yaradılmır. ``bypass_rls`` ilə (bax 0070); idempotentdir; geri dönüşdə cədvəl silinir.
"""

from django.db import migrations, models

_TABLE = "exams_questionsubmission_registry_groups"
_BYPASS = "current_setting('app.bypass_rls', true) = 'on'"
_CURRENT_ORG = "NULLIF(current_setting('app.current_org_id', true), '')"
_CONDITION = f"""
        EXISTS (
            SELECT 1
            FROM exams_questionsubmission qs
            JOIN organizations_orgunit unit
              ON unit.id = {_TABLE}.orgunit_id
            WHERE qs.id = {_TABLE}.questionsubmission_id
              AND qs.organization_id = unit.organization_id
              AND qs.organization_id::text = {_CURRENT_ORG}
        )"""
_ALLOWED = f"{_BYPASS}\n        OR ({_CONDITION})"

_FORWARD_SQL = f"""
ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
CREATE POLICY rls_tenant_isolation ON {_TABLE}
    USING (
        {_ALLOWED}
    )
    WITH CHECK (
        {_ALLOWED}
    );
"""

_REVERSE_SQL = f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {_TABLE};
ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY;
"""


def _apply_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_FORWARD_SQL)


def _revert_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REVERSE_SQL)


def label_names(label: str) -> list[str]:
    """``group_label`` («2233 İ, 2232 İ») → təkrarsız adlar."""
    names = []
    for part in (label or "").split(","):
        name = part.strip()
        if name and name not in names:
            names.append(name)
    return names


def backfill_registry_groups(apps, schema_editor):
    from core.rls import bypass_rls

    QuestionSubmission = apps.get_model("exams", "QuestionSubmission")
    OrgUnit = apps.get_model("organizations", "OrgUnit")
    by_org: dict = {}

    def groups_of(organization_id):
        if organization_id not in by_org:
            index: dict[str, list] = {}
            for unit_id, name in OrgUnit.objects.filter(organization_id=organization_id, unit_type="group").values_list(
                "id", "name"
            ):
                index.setdefault((name or "").strip(), []).append(unit_id)
            by_org[organization_id] = index
        return by_org[organization_id]

    with bypass_rls():
        submissions = (
            QuestionSubmission.objects.exclude(group_label="")
            .select_related("student_group")
            .prefetch_related("student_groups")
            .order_by("pk")
        )
        for submission in submissions.iterator(chunk_size=500):
            cohort_names = {group.name.strip() for group in submission.student_groups.all()}
            if submission.student_group_id:
                cohort_names.add(submission.student_group.name.strip())
            index = groups_of(submission.organization_id)
            unit_ids = [
                index[name][0]
                for name in label_names(submission.group_label)
                if name not in cohort_names and len(index.get(name, [])) == 1
            ]
            if unit_ids:
                submission.registry_groups.add(*unit_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("exams", "0073_final_attempt_device"),
        ("organizations", "0057_capacity_drop_unused_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="questionsubmission",
            name="registry_groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="registry_question_submissions",
                to="organizations.orgunit",
                verbose_name="Reyestr qrupları",
            ),
        ),
        migrations.RunPython(_apply_rls, _revert_rls),
        migrations.RunPython(backfill_registry_groups, migrations.RunPython.noop),
    ]
