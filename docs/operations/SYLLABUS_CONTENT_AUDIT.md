# Read-only syllabus content fingerprints

`export_wcu_syllabus_content` is an independent encrypted export. It does not
change the workload/journal-cell collector, existing decoder, producer or
workflow. Workflow wiring and production capture are a separate release step.

The command accepts an actor, one existing `chair-cells-NNN` batch, public key,
and a new output path. It reuses the existing ninety-batch registry and its
SHA-256 pin. Those 1,791 roots include unassigned and inactive history roots;
registry classifications do not establish teaching or write authority. New
openings created after the registry require an explicit supplement. No root is
silently added, skipped or replaced.

A fresh PostgreSQL transaction uses REPEATABLE READ READ ONLY, fixed tenant,
active tenant-linked superuser, no RLS bypass and explicit local context in both
session/pooling modes. There is no write-on-read API. Canonical
`syllabus_for_offering(..., _metadata_only=True)` and approved-version fallback
select the actual effective document. Current draft and effective approved
versions remain distinct. Direct owned inactive documents, selected documents,
current/approved pointers, reused-from and source-version ancestry are captured.
Whole-tenant subject-specific unbound/base candidates include all authors,
inactive records, other periods and NULL periods as metadata, without guessing
identity or interpreting an old metadata hole as absence.

The output includes only identities, enums, numeric facts, flags and SHA-256
fingerprints. Raw section data, topic text, unknown JSON key names, contact
fields, notes, decision text, file paths and auth/profile records are not
exported. Meaningful teacher additions and unsurfaced legacy subtrees remain in
canonical body hashes. Numeric strings are counted; boolean hours are invalid,
never silently one. Counts and hashes are evidence, not an automatic verdict
that a syllabus is wrong or eligible to overwrite.

The canonical body policy matches `exact_syllabus_recovery.digest/1` exactly:
object-key ordering is irrelevant; string contents, math symbols, data types and
list order remain significant. The course-only lens excludes only known
`info.teacher/office_hours/email/phone` fields. The complete body hash retains
those fields for drift detection. Topic order and multiset hashes are separate.
Legacy bindings expose only reviewed typed identity codes, numeric source IDs
where applicable and opaque hashes; they do not prove an author/subject bridge
or authorize a restore by themselves.

Hard limits fail the entire batch: 25 total root/source course contexts,
1,500 candidate metadata records, 300 body documents, 500 versions, 5,000
sections, 100,000 topic rows, 110,000 total output rows, 32 MiB logical source
JSON, 2 MiB per section, 8 MiB plaintext output, 600 counted SQL statements and
120 seconds overall. Oversized ancestry needs a separately reviewed split;
there is no truncation or absence claim.

`decrypt_syllabus_content.py` authenticates the existing AES-GCM/RSA envelope
and accepts only `wcu-syllabus-content/1`. It validates the actual same pinned
registry, strict schemas, tenant, root equality, typed nested fields, closure
links and size caps before creating a new 0600 JSON file. Existing workload and
journal decoders are untouched. Success logs contain only encrypted SHA and
counts; errors use fixed codes. A future capture receipt must also bind the
workflow run/head, registry, batch, encrypted artifact and authenticated payload
SHA before offline comparisons or any source-backed review.

The worker-coverage gate has one exact documented exemption for this command,
matching the existing two read-only exports: an outer worker transaction would
prevent `SET TRANSACTION ... READ ONLY`. The delegated collector rejects nested
transactions and its actual PostgreSQL no-DML and both-RLS tests cover this
boundary. It is not a general bypass option.
