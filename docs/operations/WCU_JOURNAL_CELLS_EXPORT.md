# Bounded encrypted journal audit

This command reads data only. It does not reconcile or change grades, defaults,
assessment schemes, assignments, or history. The registry is an audit selection,
not official authority for any corrective write.

```bash
python manage.py export_wcu_journal_cells \
  --actor OPERATOR \
  --batch chair-cells-001 \
  --public-key /private/wcu_workload_export_public.pem \
  --output /private/cells.enc.json
```

The server-side SHA-pinned registry contains `chair-cells-001` through
`chair-cells-090`: all 1,756 distinct active physical offerings in the reviewed
2026-11-01 snapshot's fall period. Each seed batch has at most 20 offerings,
leaving space for linked history. Dedicated batches 089–090 additionally pin the 35
inactive fall offerings as `inactive_history_audit`; old zero counts are never
assumed to remain zero. This scope covers the current fall period, not all years. Registry order prioritizes exact source
identity candidates, then metadata chair and offering UUID. An arbitrary UUID,
file, organization, period, chair, SQL expression, or query cannot be supplied.
Current subject/teacher/activity values are exported as facts and need not still
match the old inventory after reviewed repairs. Chair classification is inherited
inventory metadata; `unassigned` explicitly records unresolved ownership.

Every selected ID must still exist in fixed organization
`526cfa63-4f80-4bba-a7a7-61c8fbb3d918` and period
`a4f88744-8d49-4772-84ef-c28a96c3b372`.
The operator must be active, a superuser, and affiliated with that active tenant
through an active membership, profile, or ownership. The collector requires a
fresh PostgreSQL transaction, sets `REPEATABLE READ READ ONLY`, fixes tenant RLS
with bypass disabled, and establishes the actor in that transaction. An enclosing
worker atomic transaction is deliberately forbidden.

The collector follows complete enrollment supersession closure in both
directions, including inactive offerings, dropped/suspended enrollments and all
stored marks. Same-period tenant guards apply to every linked offering. If the
closure exceeds 25 physical offerings, the command fails; review and repartition
the pinned registry before retrying. No history is silently omitted. Cross-scope
mark references and unresolved supersession references also fail closed.

Payload `wcu-journal-cells/1` contains explicit schemas for offering identities,
enrollments, lessons and marks, timestamps and actor IDs, plus typed legacy
mapping rows for selected course/student/teacher/subject/group identities.
Only `myedu_mariadb` mappings whose target model AND ID match the captured scope
are included. Source keys must use the canonical bounded ASCII alphanumeric opaque syntax. Unexpected
keys require schema review; no arbitrary source payload is exported. No auth or
profile row, password/hash, PIN, email, phone, or contact field is selected.
Scoped journal/lesson/selfwork/coursework/component correction and reversal
evidence, plus hygiene decisions, include typed values and IDs only. Notes are
represented by presence flags; names, document paths/URLs, raw notes and JSON
are excluded. Unlocatable deleted-lesson evidence creates an explicit coverage
gap, never proof of no override. Separate component/final-grade values still
require their own scoped audit before a repair affecting those values.

Hard limits: 25 physical offerings including history,250,000 marks, 300,000 total
rows, 200 queries, 120-second SQL deadline, and 128 MiB encoded encrypted envelope.
A failed limit produces no output file. The file is created exclusively at 0600;
existing output is never overwritten. Use a private 0700 parent directory.

Encryption reuses the existing pinned 3072-bit RSA/OAEP-SHA256 key fingerprint,
random AES-256-GCM key/nonce and authenticated `wcu-workload-envelope/1` metadata.
No plaintext file is created on the server. Only ciphertext may be uploaded as a
CI artifact, with the existing short retention/cleanup rules. Do not log payloads,
tracebacks, command environments, decrypted records, or operator identities.
Command success output is exactly:

```text
encrypted_sha256=<64 lowercase hexadecimal> offerings=<integer> marks=<integer>
```

`scripts/ops/decrypt_workload_snapshot.py` accepts both the existing workload
payload and this additive format, authenticates before parsing, validates the
new fixed scope/field schemas/counts, and writes a new 0600 local file. Private
keys and plaintext remain local. No broad export has been run to validate this
registry; successful processing of every batch and its history is a separate
coverage claim and must be established from encrypted batch receipts.
