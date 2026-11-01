# Reviewed9544 seminar access

This fixed repair gives teacher9544 access to seminar cells in exactly one BIO
journal, e09d3997-ac19-4e7d-97fb-e1d170a58bff. The official24Oct workbook SHA is
209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16.
Sheet `Dərs yükü`, teacher anchorA98, groupsB101, subjectC101 and seminarH101=15
prove this teacher/group/kind. G101/I101 and A99:A101 must be blank. The English
BIO row is separate. The immutable full file and exact normalized cell hashes
are checked before use; the current teacher's complete surname/name/patronymic
must match the pinned identity hash.

Existing lecturer8170 is deliberately retained as an existing identity. The
workbook's different lecturer surname has no approved identity bridge. This
repair makes no source-authority claim for that lecturer, changes no owner,
load assignment, contact hours or official grade, and creates no owner share.
It compares the owner's effective access before/after and rolls back even an
indirect narrowing caused by another share.

The new registrar public API creates a truthful `workload` share containing
exactly `['seminar']` and explicit enrollment IDs. It never normalizes these to
ALL kinds or all future students. The roster must be nonempty, active,
nonsuperseded and independently verified against active BIO student records;
foreign guest origins, English/partitioned group changes and unknown section
notes fail closed. Future enrollments need their own review and are not granted
automatically. Active manual/legacy shares and historical manual decisions for
this teacher require separate review. Existing inactive legacy shares remain
unchanged and are never reactivated.

```bash
python manage.py repair_biostat_seminar_share --org qku --actor OPERATOR \
  --file /private/biostat-official-20261024.xlsx \
  --sha256 209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16
```

Dry runs use PostgreSQL `READ ONLY`, including under either RLS pooling mode;
they create no scheme, audit or grant. The fixed tenant and real actor RLS
context are established in an explicit transaction. The central public API also
requires the actor’s explicitly selected tenant to match the course, including
under database bypass, and checks live superuser status. The existing
`core.tenancy` global-superadmin policy allows an explicitly selected active
tenant without creating a membership. Foreign-selected actors/courses refuse. Applying requires the
fresh dry-run `--baseline SHA --apply`; stale metadata, roles, source, roster,
workload, manual scope, handover or history refuses. A full reverse graph of the
current journal and bounded supersession history is fingerprinted. Only one new
share and its explicit M2M rows may differ; every academic row/ID/value, owner
scope, other share and workload row must remain unchanged. Source/load rows and
assignments are fixed by ID and hours.

Success output is numeric/hash metadata only:
`biostat_kind_share: mode=... already_present=... baseline=... owner_unchanged=1 roster=... seminar_hours=15 shares_to_create=...`.
A second execution reports `already_present=1` with no write. A manually
revoked repair grant is held, never automatically recreated.

Undo first runs `--undo` without apply to obtain a fresh baseline, then uses
`--undo --baseline SHA --apply`. It requires the exact applied receipt and
unchanged full graph, removes only the repair-created unchanged grant/M2M IDs,
and verifies the entire original graph/IDs are restored. Audit evidence remains.
Any subsequent source/roster/content/scope change blocks undo for review.

The old `apply_journal_shares` command is not used: it represents legacy journal
restoration, can normalize explicit kinds/roster to ALL, and does not accept this
repair's runtime graph baseline. Three stale11588 cases belong to the separately
reviewed MR34 canonical9510 load identity repair. Other unproved teacher/owner
conflicts are excluded from this command.
