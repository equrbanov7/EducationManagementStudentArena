# Fixed027 syllabus pointer diagnostic

This is a separate, metadata-only forensic export for the immutable
`chair-cells-027` roots. It does not repair or ignore cycles in the normal
`wcu-syllabus-content/1` collector. A diagnostic must never count as a verified
normal syllabus capsule or authorize a content/pointer write.

The `syllabus-lineage-diagnostic.yml` workflow accepts only an actor. The host
checks the deployed `/app/build-info.json` SHA against the checked-out workflow
HEAD before invoking:

```text
export_wcu_syllabus_lineage_diagnostic --actor ACTOR --public-key FIXED_PUBLIC_KEY --output NEW_CIPHERTEXT
```

There are no course, batch, SQL, apply or undo selectors. The service starts a
fresh repeatable-read READ ONLY transaction, establishes the fixed tenant with
bypass disabled, and requires an active affiliated superadmin. It retains the
existing query/time budgets and bounds 25 total physical course contexts,
300 lineage dossiers, 500 versions, 16 discovery rounds and 2 MiB plaintext.
Any incomplete, foreign-tenant or over-budget closure refuses the whole export.

The encrypted `wcu-syllabus-lineage-diagnostic/1` payload contains exact root
and course IDs, dossier/current/approved/reuse pointers, source-version pointers,
all approved fallback ancestry, enum metadata, timestamps and opaque row SHA256.
It reports canonical cycle node lists and pointer ownership mismatches. It does
not query sections, export bodies, names, notes, contacts, URLs, passwords or
assessment/attendance cells. `eligible_for_apply` and absence claims are false.

The host copies into a private quarantine directory, validates the envelope and
its exact reported ciphertext SHA, then atomically approves the encrypted file.
Only the approved ciphertext and safe capture manifest can be uploaded after a
successful step. Always-run cleanup removes local and container temporary files.

On a private workstation, authenticate and validate the separate format with:

```text
python scripts/ops/decrypt_syllabus_lineage.py --input ENVELOPE --private-key PRIVATE_KEY --output-dir PRIVATE_DIRECTORY
```

The decoder pins the RSA public-key fingerprint, authenticates AES-GCM, validates
the exact immutable registry/selection/schema, checks complete pointer closure,
and recomputes the reported edges, cycles and ownership mismatches. It creates
a new mode0600 file. The ordinary syllabus decoder rejects this format.

Review the resulting cycles against the existing source-ledger/provenance and
all current work before proposing any separate repair. No pointer is changed by
this workflow, even when a cycle is found.
