"""Make journal publication equivalent to final workflow approval."""

from django.db import migrations, models


def ensure_clean_publish_state(apps, schema_editor):
    AssessmentScheme = apps.get_model("registrar", "AssessmentScheme")
    invalid = AssessmentScheme.objects.exclude(
        models.Q(is_published=True, approval_status="approved")
        | (models.Q(is_published=False) & ~models.Q(approval_status="approved"))
    ).count()
    if invalid:
        raise RuntimeError(
            "AssessmentScheme publication invariant cannot be installed: "
            f"{invalid} legacy row(s) require an explicit reconciliation decision."
        )


class Migration(migrations.Migration):
    dependencies = [("registrar", "0039_preserve_enrollment_transfer_history")]

    operations = [
        migrations.RunPython(ensure_clean_publish_state, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="assessmentscheme",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(is_published=True, approval_status="approved")
                    | (models.Q(is_published=False) & ~models.Q(approval_status="approved"))
                ),
                name="registrar_scheme_publish_state_valid",
            ),
        ),
    ]
