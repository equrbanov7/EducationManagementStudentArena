# Reviewed own active BASE syllabus bank

This fixed bank restores four genuine source documents to five current Fall
2026/2027 courses. It asserts no semester-specific legacy journal pointer and
no legacy human approval. New approvals use `approval_source=migration` and
`approved_by=NULL`; original source status `0` remains in the sealed evidence
and audit receipt.

The fixed modes are `ordinary` (Seymur7121, Mehdi8839; two courses), `design`
(Aysel4164, two courses; Fatimə8473, one course), and `all`. There is no arbitrary
teacher, subject, source, offering or organization selector. Each mode has its
own audit receipt namespace; the ordinary pair can proceed independently of
Design metadata prerequisites. Existing approved courses are skipped. Any
existing draft/dossier is preserved, including incomplete teacher drafts.

Aysel's two empty courses share one newly imported dossier using the established
`link_legacy_share` API. If one target already has its own live dossier, it stays
untouched. The other target may receive the reviewed original source without
rewriting the live dossier or claiming that its new body equals that source.

## Source fidelity and Design prerequisites

All twelve source tables are sealed and hash pinned. The established native
converter retains every nonblank text surface and original practical-hour
columns. Welcome text is also surfaced in the regular description; exam
questions are also surfaced in the regular assessment note. Original extension
fields remain unchanged. Converted and visible body hashes are separately
recorded; blank source placeholder rows are not invented as meaningful topics.

Three fixed Design targets have original **60 practical hours**, while their
current official assignments use **60 seminar hours**. These are separate pins;
the bank never rewrites the source calendar into fabricated seminar columns or
changes official assignments. That alias requires the existing domain rule:
the offering's practical flag and an actual Design chair on its Subject. No
other source/target or non-Design subject can use this alias. The topic provider
exposes original practical topics as seminar choices only in that same Design
scope; lecture choices remain unchanged.

The earlier snapshot had NULL Subject chairs for both Design catalog cards.
Fresh independent source/current/all-uses review is required before any separate
metadata correction. This bank never sets a chair or practical flag. Use the
ordinary fixed mode while those three prerequisites remain unresolved.

## Operations and preservation

`recover_own_base_syllabi --actor USER --file PRIVATE --sha256 PIN` defaults to
read-only dry-run. `--batch` is one of the fixed modes above. Apply requires the
exact fresh baseline; the workflow additionally requires explicit `APPLY`.
The workflow verifies the deployed HEAD, downloads one fixed encrypted asset,
checks both ciphertext/plaintext SHA256, copies it privately into the container
and cleans plaintext afterward. Do not publish a release before source review.

The bank locks tenant/actor/teacher scope, full teacher names, exact catalog
UUID/code/title, current period, full-time groups, fixed official rows, credits,
row groups, assignments and task revisions. Any existing contradictory typed
legacy identity mapping blocks the operation. An intentionally reviewed unique
full-name/source-context bridge is permitted where the historical worker map
is absent; it never creates or changes a legacy mapping.

The full reverse offering/workload academic graph and authority metadata must
remain identical, excluding only the exact new syllabus/version/section/share
IDs. No Lesson, Mark, Enrollment, timetable, role, workload or credit is written.
Repeated apply verifies the exact prior graph/body receipt. Undo removes only
its new share, archives only its created dossier/version, and refuses drift or
new dependent data. It never deletes pre-existing dossiers or academic rows.

Validation: bank PostgreSQL regressions cover fresh approval/draft skips,
baseline races, source identity/hours/body failures, tenant and allocation guards,
share/idempotence/undo, unchanged academic counts and original Design practical
topic visibility. The sealed host has separate closed-protocol tests.
