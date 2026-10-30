"""Do not delete batch-created identities referenced by later independent work."""

from django.apps import apps as django_apps

from .reviewed_batch_manifest import ORG
from .sbio235_state import RepairError, model


def _inbound_fields(target):
    """Include hidden ``related_name='+'`` and auto-created M2M through FKs.

    Reverse accessors alone omit anonymous survey references. Inspect concrete
    registry fields instead; no related object or identifying value is exposed.
    """
    for related in django_apps.get_models(include_auto_created=True):
        if related._meta.proxy:
            continue
        for field in related._meta.concrete_fields:
            if not (field.many_to_one or field.one_to_one):
                continue
            if field.remote_field.model._meta.concrete_model is target._meta.concrete_model:
                yield related, field


def _check(target, ids, *, allowed, code):
    if not ids:
        return
    for related, field in _inbound_fields(target):
        query = related._base_manager.filter(**{field.attname + "__in": ids})
        permitted = allowed.get((related._meta.label_lower, field.name))
        if permitted is not None:
            query = query.exclude(pk__in=permitted)
        if query.exists():
            raise RepairError(code + ":" + related._meta.label_lower + "." + field.name)


def ensure_created_reference_ownership(details):
    """Run after receipt baseline verification and before the first deletion.

    Only exact batch-created course/load identities and their unchanged initial
    roster/shares may cascade. The caller already locks the created parents and
    checks the receipt's complete academic fingerprint, so later roster changes
    cannot borrow this allowlist. Other FK policies (including SET_NULL) and M2M
    joins fail closed, irrespective of whether Django would protect deletion.
    """
    offerings = details.get("created_offering_ids", [])
    subjects = details.get("created_subject_ids", [])
    _check(
        model("registrar.Subject"),
        subjects,
        allowed={
            ("registrar.courseoffering", "subject"): offerings,
            ("workload.teachingtaskrow", "subject"): details.get("created_row_ids", []),
        },
        code="undo_created_subject_has_unreviewed_reference",
    )
    _check(
        model("registrar.CourseOffering"),
        offerings,
        allowed={
            ("registrar.enrollment", "offering"): model("registrar.Enrollment")
            .objects.filter(organization_id=ORG, offering_id__in=offerings)
            .values("pk"),
            ("registrar.journalshare", "offering"): details.get("created_share_ids", []),
        },
        code="undo_created_journal_has_unreviewed_reference",
    )
