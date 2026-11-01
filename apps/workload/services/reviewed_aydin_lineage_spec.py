"""Compiled historical-audit-backed cut; never choose an edge by timestamp alone."""

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
AUTHOR = 9529
SUBJECT = "4034f137-1081-4336-ad63-5a56705075d2"
OLDER = "5f163fe9-9549-4a39-99f4-110b28afefe8"
NEWER = "db3632d4-35e1-4208-ab19-8e88697d9fe5"
OWNERS = {
    OLDER: "554794a1-7d07-469b-af23-d6016b7ea623",
    NEWER: "eee1c528-1332-450d-b73d-872f52e91c5f",
}
OFFERINGS = {
    OLDER: "155b8a8b-42e1-4e77-b832-e8273979ff83",
    NEWER: "bbc42780-8b70-4e67-b237-2d7b06b56426",
}
BODY = {
    OLDER: "a54c257ca74fd2d81c25049ed4a79ff9e60eab070c0fe9cba338521731609359",
    NEWER: "595a482900b87958834a038bf90380fe8bf5c45c1e8c774e52b0fb9d980673ff",
}
CREATED = {OLDER: "2026-10-20T06:38:39.399756+00:00", NEWER: "2026-10-21T06:17:02.405862+00:00"}
CREATE_AUDITS = {
    OLDER: "99c467cb-17d8-4a48-aa29-88bef68a67d1",
    NEWER: "35640079-301e-4729-9315-a7e482a0661a",
}
COPY_AUDIT = "23553479-bd69-466b-b228-4a761f1db3f0"
AUDIT_CREATED = {
    CREATE_AUDITS[OLDER]: "2026-10-20T06:38:39.417908+00:00",
    CREATE_AUDITS[NEWER]: "2026-10-21T06:17:02.419937+00:00",
    COPY_AUDIT: "2026-10-21T06:17:02.439406+00:00",
}
HISTORICAL_EVIDENCE_SHA = "24144166330af64a1b88eba1bbc6db6d650dd93ab2d4e1f1208cae8b356fda84"
RESOURCE = "workload.reviewed_aydin_lineage_v1"
SAFE_GUARDS = frozenset(
    "aydin_postgresql_required aydin_actor_scope_refused aydin_fixed_versions_changed "
    "aydin_fixed_owners_changed aydin_body_changed aydin_creation_anchor_changed "
    "aydin_copy_anchor_changed aydin_graph_changed aydin_fresh_baseline_required "
    "aydin_exact_receipt_required aydin_undo_state_changed aydin_corrected_without_receipt "
    "aydin_prior_undo_changed aydin_write_conflict aydin_preservation_failed "
    "aydin_history_budget aydin_reviewed_guard_failed aydin_snapshot_or_repair_failed "
    "aydin_scoped_superadmin_required aydin_lineage_lock_refused".split()
)
