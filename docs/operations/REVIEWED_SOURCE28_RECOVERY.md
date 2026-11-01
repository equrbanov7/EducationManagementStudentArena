# Fixed source28 recovery

This case uses the existing reviewed-content engine for one missing seminar:
source journal 14434 → offering `1aca3f3c-5677-494e-af12-5622d2c1ea0a`,
2026-10-29 15:15, exactly 28 source PRESENT cells. It creates at most one
lesson and 28 marks. The other 58 QB cells remain deferred; the generic
absence-only lesson guard is unchanged. No future/authority/other-slot cases
are included.

The private executable `reviewed-journal-content/1` payload must have SHA256
`ce94b0cfc7a35f5d4595005474283492854f690b8532e9c57463f3a5ff377bc3`.
Its normalized digest and exact point/student/enrollment bindings are compiled
into the fixed registry. Source metadata 315602/calendar 385260 supply the
reviewed topic/date/start; raw pair1 means two academic hours under the existing
post-2024-02 documented recovery conversion. End time and authors remain NULL.
No current teacher is attributed as the author of the historical rows.

Default audit, using the decrypted private file on the operator's machine:

```sh
python manage.py repair_reviewed_journal_content --actor "$ACTOR" \
  --manifest "$PRIVATE_MANIFEST" --manifest-sha256 "$SOURCE_SHA256" \
  --targets 1aca3f3c-5677-494e-af12-5622d2c1ea0a
```

An approved apply requires the fresh audit baseline with the same arguments
plus `--apply --expected-baseline "$BASELINE"`. Repeat first obtains a new dry
baseline; unchanged inserted rows resolve as already done. No workflow,
dispatch, permission/membership or student enrollment is created by this change.

Runtime guards require active, unblocked, undeleted tenant profiles and exact
current active enrollments/home groups; the reviewed teacher/kind/subject/group
workload assignment; exact typed worker/student/catalog/group maps; and no
contradictory core ledger, source claims, corrections, hygiene or deletion
intent. Canonical checks cover inactive and dropped courses for the same
student/subject/period/date, across all groups and owners. Unknown deletion
locators and unresolved editing audits hold the case. The available audit is
best effort, not a claim that audit absence proves no deletion.

The source28 history scope is a single immutable compiled object. The existing
four-cell collector's default shape, hash, scope and budgets stay unchanged.
The public helper accepts no caller-defined source selectors.

All existing marks, numeric zero, EXCUSED, scores, official/written grades,
roster and authors remain untouched. PRESENT-only insertion must not change
any existing derived absence counter; a stale counter causes atomic rollback.

Receipt-bound undo defaults to audit:

```sh
python manage.py undo_reviewed_source28_content --actor "$ACTOR" \
  --manifest "$PRIVATE_MANIFEST" --manifest-sha256 "$SOURCE_SHA256" \
  --batch "$RECEIPT"
```

After review, repeat with `--apply --expected-baseline "$UNDO_BASELINE"`.
Undo deletes only the unchanged lesson/marks created by that exact receipt,
requires no additional reverse references, restores the original fingerprint,
and appends an undo receipt. Later edits, source claims or references block it.
A deliberate undo blocks silent reapplication. The ledger/audit is never deleted.

CLI diagnostics emit only closed stage/class/guard/module/function/line tokens;
no source rows, exception values, names, notes, SQL or private paths are logged.
Undo stdout is a bounded `reviewed_source28_undo:` token summary.
