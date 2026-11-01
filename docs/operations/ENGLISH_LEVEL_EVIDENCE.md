# English level metadata evidence

This is a read-only audit, never a placement, roster, grade or account repair.
The fixed tenant, Fall 2026/2027, six subject UUIDs, 1235 source student IDs and
source-input SHA are pinned in `english_level_evidence/spec.py`.

The input namespace is `myedu_new.students.id`. The private reviewed source
packet contains only exact source IDs, institutional identifiers, optional
normalized seven-character ASCII FIN and provenance hashes. The source input
must remain private and encrypted during transport. Never print it or upload
plaintext as an artifact. No name matching, account creation or priority choice
between conflicting identity evidence is supported.

After a reviewed deployment, use the command with an active fixed-tenant
superadmin, private source input and the established pinned public key:

```text
export_wcu_english_level_evidence --actor ACTOR --file PRIVATE_SOURCE --sha256 PINNED_SHA --public-key PINNED_PUBLIC_KEY --output NEW_CIPHERTEXT_PATH
```

The command accepts no arbitrary course or student selector and has no apply
mode. It requires a fresh PostgreSQL transaction, starts REPEATABLE READ READ
ONLY, and establishes tenant/actor RLS scope locally with bypass disabled. An
outer worker transaction would invalidate `SET TRANSACTION`; this exact command
therefore has a documented worker-atomic exemption. Actual command tests prove
both RLS settings and PostgreSQL-enforced write rejection.

Capture bounds are 150 physical courses, 5000 enrollment references, 10000
placements, 1000 relevant teachers, 5000 share-through links, 30000 output rows
and 16 MiB. The internal same-tenant profile scan is bounded at 50000, and the
existing query budget enforces 200 statements/120 seconds. Any exceeded or
outside-scope closure fails explicitly. The separate raw journal-cell collector
keeps its existing 25-physical-course cap unchanged.

All course/enrollment states and profile access/deletion/block flags are
retained. Modern cohorts, append-only placements, SAR homegroups, source group
and supersession references remain facts. They do not authorize reactivation or
removal. New teacher work and old dropped enrollments are never mutated.

Typed migrated student ledger, exact institutional identifier and normalized
valid FIN must agree. Ambiguous or contradictory evidence is held. Duplicate
source FIN cannot resolve by FIN alone; unique typed/institutional proof may
resolve that specific entity while preserving the duplicate flag. Missing typed
ledger coverage is not proof of a missing student. `immutable_mapping` and
`eligible_for_apply` are always false.

Teacher metadata includes relevant owners, positive current approved/distributed
teaching assignments, exact shares/source/kinds and existing roster-through PKs.
Role/profile/membership flags are not an edit permission decision. In particular,
`teacher_access_attested` remains false; canonical live RBAC, kind and roster
scope must be checked separately before any future repair. No raw role
permissions, notes, names, contact, file URLs, FIN, scores or lesson marks leave
the collector. Aggregate mark counts/latest activity timestamps are diagnostic.

Output is a separate `wcu-english-level-evidence/1` payload using the existing
RSA-3072/AES-GCM encrypted envelope and pinned key fingerprint. Stdout contains
only the ciphertext SHA and numeric counts. Decode locally using:

```text
python scripts/ops/decrypt_english_level_evidence.py --input CIPHERTEXT --private-key PRIVATE_KEY --output-dir EXISTING_0700_DIRECTORY
```

The standalone decoder rejects unknown keys, foreign references, wrong scope,
invalid enums, unbounded payloads and any claim of write authority. It creates a
new private file only. Existing snapshot contracts and decoders are unchanged.
