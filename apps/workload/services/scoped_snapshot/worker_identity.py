"""Fixed worker1068 identity probe; no broad auth export or raw contact fields."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import CharField, Func, Q
from django.db.models.functions import Lower, Trim

from core.search_text import tolerant_q

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
# Exact legacy1068 source email digest, never a password/reset token.
SOURCE_EMAIL_SHA256 = "cbe415de219a499a05f3b73e60d8a0946c26cbba4efd887248b5fde8f480e6bf"
SOURCE_ROW_SHA256 = "20fb728a9acd65bff4c1d38958236276b7da5a01abc1d01c4b96e919792f6fe4"


def collect_worker1068():
    ledger = list(
        apps.get_model("legacy_import", "LegacyEntityMap")
        .objects.filter(
            organization_id=ORG,
            legacy_pk="1068",
            entity_type__in=["worker", "workers", "worker_materialisation", "teacher"],
            target_model_label="auth.user",
        )
        .values("id", "source_system", "entity_type", "state", "target_pk")
    )
    mapped = [int(row["target_pk"]) for row in ledger if row["target_pk"].isdigit()]
    surname = tolerant_q("Rezvanian", ("first_name", "last_name", "username"))
    surname |= tolerant_q("Rezvaniyan", ("first_name", "last_name", "username"))
    query = (
        get_user_model()
        .objects.annotate(
            source_email_sha=Func(
                Lower(Trim("email")),
                template="encode(sha256(convert_to(%(expressions)s, 'UTF8')), 'hex')",
                output_field=CharField(),
            )
        )
        .filter(Q(source_email_sha=SOURCE_EMAIL_SHA256) | surname | Q(pk__in=mapped))
        .distinct()
    )
    global_count = query.values("id").count()
    scoped = query.filter(Q(profile__organization_id=ORG) | Q(memberships__organization_id=ORG)).distinct()
    users = list(
        scoped.order_by("pk").values("id", "username", "first_name", "last_name", "is_active", "source_email_sha")
    )
    profiles = {
        row["user_id"]: row
        for row in apps.get_model("accounts", "UserProfile")
        .objects.filter(organization_id=ORG, user_id__in=[u["id"] for u in users])
        .values("user_id", "patronymic", "access_state")
    }
    for user in users:
        user.update({key: value for key, value in profiles.get(user["id"], {}).items() if key != "user_id"})
        user["email_matches_source"] = user.pop("source_email_sha") == SOURCE_EMAIL_SHA256
        user["legacy_worker_id"] = 1068
    return {
        "worker1068_identity_candidates": users,
        "worker1068_identity_mappings": ledger,
        "worker1068_identity_summary": [
            {
                "legacy_worker_id": 1068,
                "global_candidate_count": global_count,
                "tenant_candidate_count": len(users),
                "outside_tenant_candidate_count": global_count - len(users),
                "mapping_count": len(ledger),
                "source_email_sha256": SOURCE_EMAIL_SHA256,
                "source_row_sha256": SOURCE_ROW_SHA256,
            }
        ],
    }
