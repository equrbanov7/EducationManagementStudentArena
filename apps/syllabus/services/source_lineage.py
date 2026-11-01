"""Reject cyclic mutable-copy provenance before sections or approval state are written."""

import hashlib

from django.db import connection

from ..models import SyllabusVersion
from ..state_machine import TransitionDenied

MAX_ANCESTORS = 64
INVALID = "version.source_lineage_invalid"
BUSY = "version.source_lineage_busy"


def lock_lineage(organization_id):
    """Serialize provenance rewrites within a tenant; never wait after taking other locks.

    A reverse copy can otherwise pass two independent ancestry checks concurrently.
    Fresh-version-only paths cannot create an edge back into an existing version.
    """
    if not connection.in_atomic_block:
        raise TransitionDenied(INVALID)
    if connection.vendor == "postgresql":
        key = int.from_bytes(
            hashlib.blake2b(("syllabus.source-lineage:" + str(organization_id)).encode(), digest_size=8).digest(),
            "big",
            signed=True,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [key])
            if not cursor.fetchone()[0]:
                raise TransitionDenied(BUSY)


def validate_source(*, organization_id, target_id, source):
    """Read fresh typed ancestry, reject self/ancestor/existing-cycle/foreign/missing refs.

    Timestamps cannot establish copy order: an old draft may have been replaced
    in place later. No edge is removed or guessed by this guard.
    """
    lock_lineage(organization_id)
    seen = {str(target_id)}
    current = source.pk
    for _ in range(MAX_ANCESTORS):
        if str(current) in seen:
            raise TransitionDenied(INVALID)
        seen.add(str(current))
        row = (
            SyllabusVersion.objects.select_for_update()
            .filter(pk=current)
            .values("organization_id", "source_version_id")
            .first()
        )
        if row is None or row["organization_id"] != organization_id:
            raise TransitionDenied(INVALID)
        current = row["source_version_id"]
        if current is None:
            return
    raise TransitionDenied(INVALID)
