# Fixed Onomastics home-roster supplement

This separate operation must follow the reviewed `az_onomastics` contacts
correction. It does not amend workload, owners, hours, subjects, syllabi,
registrations, lessons, marks, roles, memberships or any `JournalShare` field.
It appends ten through-table links for five fixed enrolled home students to four
existing, explicitly kind-limited LEGACY shares. Morphology is excluded.

Authority is the reviewed whole-group official workload source
`765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff` and the
current read-only registry/browser proof
`a022d1d77c1d583a1f9c21c18a8145a2a75955324648702893d04a8b1eb3452f`.
Four students match their own F1 target and one matches its own F2 target.
The private proof records the exact current enrollment and SAR identifiers.
Absence of modern movement UI is not a claim that historical guest provenance
never existed. Runtime rechecks exact active SAR, home group, program,
admission year, enrolled status and supersession. A foreign source group holds
the operation; neither guest provenance nor a home-group mismatch is guessed.

The central registrar public API accepts no caller-selected student, teacher or
kind list. It validates the four fixed share PKs and full raw-record hashes,
original Onomastics through hashes, current authorized teachers and explicit
lecture/seminar kinds. It appends to existing explicit rosters; it never changes
source flags, replaces rosters, creates shares or grants ALL/future kinds.
The central owner policy is not changed. Completing the seminar roster makes
that kind fully claimed by its source teacher, so the existing policy removes
the owner's prior unclaimed-seminar fallback. The owner retains the complete current lecture roster, score-management access,
owned historical seminar columns, and still-unclaimed-kind fallback. The seminar
teacher retains access to all historical seminar columns. A pure canonical-scope
projection checks these effects before any write; unexpected kind or management
changes hold the operation. No stored role, source flag or kind list is
rewritten. This derived scope effect must be reviewed with the source split.

The workload wrapper validates the complete corrected source-row/assignment
geometry, teacher/group identities, released source task and corrected active
syllabus plans. All ten reviewed legacy shares and the original 116 through PKs
are pinned. A fresh baseline captures the full reverse academic/configuration
and supersession closure plus workload, SAR/program, membership and role state.
Apply succeeds only if exactly ten new links are the entire difference.

```sh
python manage.py repair_onomastics_roster --org qku --actor AUDIT_OPERATOR
python manage.py repair_onomastics_roster --org qku --actor AUDIT_OPERATOR --baseline DRY_BASELINE --apply
python manage.py repair_onomastics_roster --org qku --actor AUDIT_OPERATOR --undo APPLY_RECEIPT_UUID
python manage.py repair_onomastics_roster --org qku --actor AUDIT_OPERATOR --undo APPLY_RECEIPT_UUID --baseline UNDO_DRY_BASELINE --apply
```

Dry execution is a real read-only PostgreSQL/RLS transaction under both pooling
modes. Apply requires its fresh baseline. Repeat reports `already_present` only
for the exact receipt state. Undo removes only the ten receipt-created through
PKs and must exactly restore the original graph. New or updated marks and any
other graph drift block undo. A repeat undo reports `already_undone` only when
its exact restored state remains. Audit records remain append-only.

Output prefix is `onomastics_roster`, with `mode`, `status`, `baseline`, numeric
`links`, `owner_seminar_access_narrowed` (1 for apply/its dry run; 0 for undo), and `receipt` (UUID or `none`). There are no source/target selectors or
uploaded assets. The original contacts command intentionally refuses its old
selected-roster pins after this supplement; it must not normalize or overwrite
the newly reviewed rights. This command is not a general roster expansion path.

The independent `reviewed-onomastics-roster.yml` workflow exposes only `actor`,
`baseline`, `undo`, `apply` and `confirm`. It invokes the exact command above;
apply requires a fresh baseline and `confirm=APPLY`, and undo uses the exact
append receipt UUID. No teacher, student, source, group or kind selectors are
accepted. Checkout HEAD must match deployed `/app/build-info.json`; the job
shares the `production-deploy` concurrency lock. Only the fixed safe summary
is printed. A timeout or missing summary after a possible apply requires
receipt inspection before retry; this wrapper never dispatches an automatic
retry. Rollback order is append first, then contacts, with a new dry baseline
for each operation. Existing Math and contacts workflow routes are unchanged.
