"""Four fixed foreign journals: encrypted-only current handover and alias evidence."""

from django.apps import apps

from .data import ORG

OFFERINGS = (
    "73d33235-e875-4100-8ce4-4ae4b42a9a8a",
    "7182d9c2-4bbf-4475-9603-97eb59f4e6e7",
    "4d33dcb4-6605-472c-ac9e-793d5461aa25",
    "123c0134-fb83-4337-99b2-13a4f18430b5",
)
TEACHERS = (7730, 8388)


def _rows(label, fields, cap, **filters):
    values = list(
        apps.get_model(label).objects.filter(organization_id=ORG, **filters).order_by("pk").values(*fields)[: cap + 1]
    )
    if len(values) > cap:
        raise ValueError("jale_handover_evidence_budget_exceeded")
    return values


def collect_jale_handovers():
    """No password, FIN, personal contact, student roster or new access is exported."""
    return {
        "jale_current_handovers": _rows(
            "registrar.TeachingHandover",
            (
                "id",
                "organization_id",
                "offering_id",
                "from_instructor_id",
                "to_instructor_id",
                "performed_by_id",
                "created_at",
                "updated_at",
                "reason",
                "deactivated_share_ids",
                "reverted_at",
                "reverted_by_id",
                "revert_reason",
            ),
            12,
            offering_id__in=OFFERINGS,
        ),
        "jale_current_journal_shares": _rows(
            "registrar.JournalShare",
            (
                "id",
                "organization_id",
                "offering_id",
                "teacher_id",
                "is_active",
                "kinds",
                "source",
                "created_at",
                "updated_at",
            ),
            16,
            offering_id__in=OFFERINGS,
        ),
        "jale_account_memberships": _rows(
            "organizations.Membership",
            ("id", "organization_id", "user_id", "role_id", "scope_unit_id", "is_active"),
            30,
            user_id__in=TEACHERS,
        ),
    }
