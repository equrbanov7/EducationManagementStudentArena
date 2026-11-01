# Fixed recovery audit-size diagnostic

`recovery-audit-diagnostic.yml` accepts only an active fixed-tenant superadmin
actor. It verifies the deployed image SHA, then runs
`export_wcu_recovery_audit_diagnostic` inside a fresh PostgreSQL REPEATABLE READ
READ ONLY transaction with the existing query/time/row budgets.

The two code-owned scopes are the Four existing cells and Source28. They use
the identical resource/source-reference locator as the strict history reader.
Only record UUIDs, allowed resource codes, SHA256 values, byte sizes and timestamps
are selected. JSON audit bodies, names, notes, passwords and contacts are never
fetched into Python or exported. SHA and byte lengths are calculated in PostgreSQL.
Oversized records can therefore be diagnosed without increasing the normal
reader's 8MiB total / 1MiB per-row raw-body budgets.

The artifact is encrypted with the existing pinned RSA/AES envelope. Use the
separate `scripts/ops/decrypt_recovery_audit_diagnostic.py` decoder and private
output directory. Distinct format `wcu-recovery-audit-diagnostic/1` explicitly
sets `eligible_for_apply=False`, `absence_claim=False`, and each scope's
`history_cleared_for_apply=False`. It is not complete audit/grade evidence and
cannot authorize any restoration. An oversized or unresolved mutation still
holds the normal writer until a separately reviewed bounded projection can
prove its effect. No audit record or grade is edited by this diagnostic.

Tests exercise real oversized JSON, unchanged row fingerprints, both RLS modes,
foreign-tenant exclusion, actual write rejection, cryptographic round-trip,
strict offline schema and rejection by the normal syllabus decoder.
