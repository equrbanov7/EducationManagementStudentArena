# Approved own source beside preserved human drafts

`recover_blank_draft_syllabi` is a compiled two-case append, not a general
syllabus import. The fixed targets and complete-source hashes are in
`blank_draft_syllabus_spec.py`:

- source 7474 → target 123f89bf, author 8306, QKU-14, 15 contact hours;
- source 8744 → target 0a71ca40, author 8333, QKU-846, 30 contact hours.

Each target has an existing human draft and no effective approved version.
The first draft has zero nonblank sections. The second has exactly its pinned
`desc` and `info` sections. Every original version/section ID, field, status,
content hash, author and timestamp is pinned and retained. The second draft's
semantic correctness is not asserted. Its authored work is neither published
nor overwritten.

The public syllabus migration engine creates a separate approved source
version and new section rows in the existing exact dossier. Approval source is
`migration`, `approved_by` remains NULL, and current reviewed user authority is
recorded; historical legacy approval is never asserted. The engine naturally
keeps the existing open draft as the editing pointer and selects the new
approved version separately. The journal's published reader uses that approved
version; the teacher's editor retains the original draft.

The source packet contains the complete original twelve-table academic bodies,
including all weekly topics and self-work. No new content is invented. Exact
source worker/catalog mappings, tenant, period, group sector/degree/form,
current contact-hours, approved workload row, through-group identities and
assignment geometry are guarded. Source files are private and encrypted during
transport. Published V1 source bytes remain immutable; the two-case operation
uses a separately pinned V2 packet.

```text
recover_blank_draft_syllabi --org qku --actor ACTOR --file PRIVATE_SOURCE --sha256 PINNED_SHA
recover_blank_draft_syllabi --org qku --actor ACTOR --file PRIVATE_SOURCE --sha256 PINNED_SHA --baseline FRESH_DRY_BASELINE --apply
recover_blank_draft_syllabi --org qku --actor ACTOR --undo APPLY_RECEIPT_UUID
recover_blank_draft_syllabi --org qku --actor ACTOR --undo APPLY_RECEIPT_UUID --baseline FRESH_UNDO_BASELINE --apply
```

The default dry run reads and locks state without creating versions or audit
receipts. An apply, including a repeat, requires a fresh 64-hex baseline.
Authorization precedes source-file and receipt reads. The command owns an
explicit atomic transaction inside the worker wrapper, establishes fixed tenant
RLS scope locally with bypass disabled, and sets bounded lock/statement
timeouts. Both RLS modes have migrated PostgreSQL tests.

A changed draft, section/completion flag, additional version/review/share/reuse,
identity mapping, teacher access state, workload or protected journal graph
causes refusal. Full-field database fingerprints preserve lessons, grades,
enrollments and assessment configuration. Both cases apply atomically; failure
after the second import rolls the first back too.

Undo accepts only the recorded apply UUID and exact unchanged post-apply graph.
It uses the canonical syllabus archive transition on the newly created source
versions. No original draft/version/section/grade is deleted or rewritten. The
new source records remain inspectable as archived history, and original dossier
pointers are restored. Later grades or teacher/source edits block undo.

JSON output is restricted to status, baseline, optional after_baseline, receipt
UUID and numeric counters (`cases`, `human_drafts_preserved`, `versions_created`,
`versions_archived`). Failure diagnostics use the shared closed class/module/
function/line/guard format without exception values, body text or SQL. The
standalone reviewed workflow verifies the deployed head, uses the pinned V2
ciphertext, and removes private temporary files.
