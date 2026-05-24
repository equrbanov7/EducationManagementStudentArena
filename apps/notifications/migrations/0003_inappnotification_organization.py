"""Add a real organization FK to InAppNotification (FAZA 4).

Previously the notification's tenant scope lived only inside the ``metadata``
JSONB blob, and the RLS policy in ``organizations.0004_expand_rls_scope`` read
it from there with a fail-OPEN rule (``organization_id IS NULL`` was allowed).

This migration introduces a proper, indexed ``organization`` FK column and
backfills it from the existing ``metadata->>'organization_id'`` value so the
RLS policy can be moved onto a reliable column (see
``organizations.0005_notification_org_fk_rls``).

NULL ``organization`` is legitimate: platform/system and blog notifications
are deliberately global. Those rows stay protected by the recipient_id check
in the RLS policy.
"""

from django.db import migrations, models
import django.db.models.deletion


def _backfill_organization_from_metadata(apps, schema_editor):
    """Copy metadata['organization_id'] into the new organization_id column."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        UPDATE notifications_inappnotification AS n
        SET organization_id = o.id
        FROM organizations_organization AS o
        WHERE n.organization_id IS NULL
          AND NULLIF(COALESCE(n.metadata, '{}'::jsonb) ->> 'organization_id', '') IS NOT NULL
          AND o.id::text = NULLIF(COALESCE(n.metadata, '{}'::jsonb) ->> 'organization_id', '');
        """
    )


def _noop_reverse(apps, schema_editor):
    """Reverse: the column is dropped by RemoveField; nothing else to undo."""


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_add_role_type_to_org_request"),
        ("organizations", "0004_expand_rls_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="inappnotification",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="in_app_notifications",
                to="organizations.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="inappnotification",
            index=models.Index(
                fields=["organization", "recipient"],
                name="notif_org_recipient_idx",
            ),
        ),
        migrations.RunPython(_backfill_organization_from_metadata, _noop_reverse),
    ]
