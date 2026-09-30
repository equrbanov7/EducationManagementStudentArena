# Sorğu qurucusu (2026-09-30): ümumi sorğular (auditoriya, qapı siyasəti, anonim/şəxsli), sual
# redaktoru (bölmələr, yeni sual növləri, kilidli sualın versiyalı mətn düzəlişi), iştirak/cavab/
# bufer/qaralama/keçid cədvəlləri + RLS.
#
# ƏLAVƏ və GERİ ÇEVRİLƏ BİLƏN: mövcud cədvəllərə yalnız boş defoltlu sahələr (``options``,
# ``history``, nullable ``page``) və ``kind`` seçimlərinin genişlənməsi (DB dəyişmir). Mövcud hər
# sual dəsti (``SurveyTemplate``) üçün ``teacher_evaluation`` növlü ``Survey`` sarğısı yaradılır ki,
# qurucu siyahısı vahid olsun — kampaniyalar əvvəlki kimi ``SurveyCampaign.template``-i oxuyur.

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_BYPASS_EXPR = "current_setting('app.bypass_rls', true) = 'on'"
_ORG_EXPR = "organization_id::text = NULLIF(current_setting('app.current_org_id', true), '')"
_TABLES = (
    "surveys_surveypage",
    "surveys_survey",
    "surveys_surveyparticipation",
    "surveys_surveysubmission",
    "surveys_surveysubmissionanswer",
    "surveys_surveypendingsubmission",
    "surveys_surveydraft",
    "surveys_surveygateskip",
)


def _rls_forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
CREATE POLICY rls_tenant_isolation ON {table}
    USING ({_BYPASS_EXPR} OR organization_id IS NULL OR {_ORG_EXPR})
    WITH CHECK ({_BYPASS_EXPR} OR organization_id IS NULL OR {_ORG_EXPR});
""")


def _rls_reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in _TABLES:
        schema_editor.execute(f"""
DROP POLICY IF EXISTS rls_tenant_isolation ON {table};
ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
""")


def _wrap_templates(apps, schema_editor):
    """Mövcud sual dəstləri → ``teacher_evaluation`` sorğu sarğısı (idempotent)."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    SurveyTemplate = apps.get_model("surveys", "SurveyTemplate")
    Survey = apps.get_model("surveys", "Survey")
    wrapped = set(Survey.objects.values_list("template_id", flat=True))
    rows = []
    for template in SurveyTemplate.objects.exclude(pk__in=wrapped):
        title = template.name if template.version <= 1 else f"{template.name} v{template.version}"
        rows.append(
            Survey(
                organization_id=template.organization_id,
                template_id=template.pk,
                kind="teacher_evaluation",
                title=title[:200],
                anonymous=True,
                audience="students",
                status="published" if template.is_active else "archived",
            )
        )
    Survey.objects.bulk_create(rows)
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("SELECT set_config('app.bypass_rls', 'off', true)")


class Migration(migrations.Migration):

    dependencies = [
        ("surveys", "0004_pending_buffer_and_results_published"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="surveyquestion",
            name="history",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="surveyquestion",
            name="options",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="surveyquestion",
            name="kind",
            field=models.CharField(
                choices=[
                    ("likert5", "Razılıq şkalası (1–5)"),
                    ("scale10", "Bal şkalası (1–10)"),
                    ("text", "Sərbəst mətn"),
                    ("single", "Tək seçim"),
                    ("multi", "Çox seçim"),
                    ("nps", "Reytinq / NPS (0–10)"),
                    ("yesno", "Bəli / Xeyr"),
                    ("short_text", "Qısa mətn"),
                ],
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="Survey",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("teacher_evaluation", "Müəllim qiymətləndirməsi"),
                            ("general", "Ümumi sorğu"),
                            ("course_feedback", "Fənn / kurs rəyi"),
                            ("event", "Tədbir / digər"),
                        ],
                        default="general",
                        max_length=24,
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("anonymous", models.BooleanField(default=True)),
                (
                    "audience",
                    models.CharField(
                        choices=[
                            ("students", "Tələbələr"),
                            ("teachers", "Müəllimlər"),
                            ("staff", "İnzibati heyət"),
                            ("everyone", "Hamı"),
                        ],
                        default="students",
                        max_length=16,
                    ),
                ),
                ("audience_filter", models.JSONField(blank=True, default=dict)),
                ("opens_on", models.DateField(blank=True, null=True)),
                ("closes_on", models.DateField(blank=True, null=True)),
                ("mandatory", models.BooleanField(default=False)),
                (
                    "gate_policy",
                    models.CharField(
                        choices=[
                            ("block", "Doldurulmayınca kabinet bağlıdır"),
                            ("skip_once", "Bir dəfə keçmək olar"),
                            ("defer_days", "«Sonra doldur» möhləti (gün)"),
                        ],
                        default="defer_days",
                        max_length=16,
                    ),
                ),
                (
                    "defer_days",
                    models.PositiveSmallIntegerField(
                        default=3,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(60),
                        ],
                    ),
                ),
                (
                    "min_group_size",
                    models.PositiveSmallIntegerField(
                        default=3,
                        validators=[
                            django.core.validators.MinValueValidator(3),
                            django.core.validators.MaxValueValidator(50),
                        ],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Qaralama"),
                            ("published", "Dərc olunub"),
                            ("closed", "Bağlı"),
                            ("archived", "Arxivdə"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=12,
                    ),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("results_published_at", models.DateTimeField(blank=True, null=True)),
                ("notified_at", models.DateTimeField(blank=True, null=True)),
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
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="surveys",
                        to="organizations.organization",
                    ),
                ),
                (
                    "template",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT, related_name="survey", to="surveys.surveytemplate"
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu",
                "verbose_name_plural": "sorğular",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SurveyDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("data", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="drafts", to="surveys.survey"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu qaralaması",
                "verbose_name_plural": "sorğu qaralamaları",
            },
        ),
        migrations.CreateModel(
            name="SurveyGateSkip",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("skipped_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="gate_skips", to="surveys.survey"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu keçidi",
                "verbose_name_plural": "sorğu keçidləri",
            },
        ),
        migrations.CreateModel(
            name="SurveyPage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(blank=True, max_length=200)),
                ("description", models.TextField(blank=True)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="pages", to="surveys.surveytemplate"
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu bölməsi",
                "verbose_name_plural": "sorğu bölmələri",
                "ordering": ["order", "id"],
            },
        ),
        migrations.AddField(
            model_name="surveyquestion",
            name="page",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="questions",
                to="surveys.surveypage",
            ),
        ),
        migrations.CreateModel(
            name="SurveyParticipation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("completed_on", models.DateField()),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="participations", to="surveys.survey"
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu iştirakı",
                "verbose_name_plural": "sorğu iştirakları",
            },
        ),
        migrations.CreateModel(
            name="SurveyPendingSubmission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("payload", models.JSONField(default=dict)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pending_submissions",
                        to="surveys.survey",
                    ),
                ),
            ],
            options={
                "verbose_name": "dərc gözləyən sorğu cavabı",
                "verbose_name_plural": "dərc gözləyən sorğu cavabları",
            },
        ),
        migrations.CreateModel(
            name="SurveySubmission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "respondent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "survey",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="surveys.survey"
                    ),
                ),
            ],
            options={
                "verbose_name": "sorğu cavabı (forma)",
                "verbose_name_plural": "sorğu cavabları (forma)",
            },
        ),
        migrations.CreateModel(
            name="SurveySubmissionAnswer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("number", models.SmallIntegerField(blank=True, null=True)),
                ("choices", models.JSONField(blank=True, default=list)),
                ("text", models.TextField(blank=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="organizations.organization"
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="surveys.surveyquestion"
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="surveys.surveysubmission",
                    ),
                ),
            ],
            options={
                "verbose_name": "sual cavabı",
                "verbose_name_plural": "sual cavabları",
            },
        ),
        migrations.AddIndex(
            model_name="survey",
            index=models.Index(fields=["organization", "status"], name="surveys_survey_org_status"),
        ),
        migrations.AddConstraint(
            model_name="survey",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("kind", "teacher_evaluation"), _negated=True), ("anonymous", True), _connector="OR"
                ),
                name="surveys_survey_teacher_eval_anonymous",
            ),
        ),
        migrations.AddConstraint(
            model_name="survey",
            constraint=models.CheckConstraint(
                condition=models.Q(("min_group_size__gte", 3)), name="surveys_survey_min_group_floor"
            ),
        ),
        migrations.AddConstraint(
            model_name="survey",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("closes_on__isnull", True),
                    ("opens_on__isnull", True),
                    ("closes_on__gte", models.F("opens_on")),
                    _connector="OR",
                ),
                name="surveys_survey_dates_ordered",
            ),
        ),
        migrations.AddConstraint(
            model_name="surveydraft",
            constraint=models.UniqueConstraint(fields=("survey", "user"), name="surveys_draft_once"),
        ),
        migrations.AddConstraint(
            model_name="surveygateskip",
            constraint=models.UniqueConstraint(fields=("survey", "user"), name="surveys_gate_skip_once"),
        ),
        migrations.AddConstraint(
            model_name="surveyparticipation",
            constraint=models.UniqueConstraint(fields=("survey", "user"), name="surveys_participation_once"),
        ),
        migrations.AddIndex(
            model_name="surveysubmissionanswer",
            index=models.Index(fields=["question", "number"], name="surveys_subanswer_q_number"),
        ),
        migrations.AddConstraint(
            model_name="surveysubmissionanswer",
            constraint=models.UniqueConstraint(fields=("submission", "question"), name="surveys_subanswer_once"),
        ),
        migrations.AddConstraint(
            model_name="surveysubmissionanswer",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("number__isnull", True), models.Q(("number__gte", 0), ("number__lte", 10)), _connector="OR"
                ),
                name="surveys_subanswer_number_range",
            ),
        ),
        migrations.RunPython(_rls_forward, _rls_reverse),
        migrations.RunPython(_wrap_templates, migrations.RunPython.noop),
    ]
