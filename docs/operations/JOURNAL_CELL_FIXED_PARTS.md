# Fixed supplementary journal-cell partitions

The primary90-batch registry and its SHA
`1783da2b28d6a669266d09f7c313ea8a4d1b59a80e76b730f2dcda20a0cc7b87`
remain unchanged. Primary completion was80/90; the exact held parents are
040,043,053,064,065,066,067,068,069,070, each with20 roots and the existing
`history_course_budget_exceeded_split_batch` refusal.

The additive `export_wcu_journal_cells_part` command accepts only20 enumerated
selectors: `chair-cells-NNN-part-001` and `-002` for those ten parents.
Each selects the ordered first10 or second10 roots from the pinned parent.
There is no arbitrary ID input. The command delegates to the existing `_capture`
with that exact subset, inside the existing query budget and a fresh PostgreSQL
REPEATABLE READ READ ONLY transaction. Actor affiliation, fixed tenant/current
fall, explicit old12-table schemas and all privacy rules remain unchanged.

The limit is still25 TOTAL physical courses including the complete bidirectional
supersession closure. Marks250000, total rows300000, query/time budgets and128MiB
encrypted limit are unchanged. A parent with40 courses can yield two independent
20-course captures. A single26-course connected component still fails, even
inside a part; no rows or history are silently omitted.

```sh
python manage.py export_wcu_journal_cells_part --actor AUDIT_OPERATOR --part chair-cells-043-part-001 --public-key scripts/data/wcu_workload_export_public.pem --output /private/part-001.enc.json
```

Payload format is `wcu-journal-cells-part/1`. `batch` and `parent_batch` identify
the logical parent; `part`, `part_count=2`, the fixed partition policy and a
SHA256 of the full ordered parent selection bind the part. Old data schemas and
correction coverage/gaps remain explicit. A separate standalone decoder
`scripts/ops/decrypt_journal_cells_part.py` authenticates the existing RSA/AESGCM
envelope/key pin and validates exact selection, schemas, references and connected
closure before writing a new0600 private file. It does not retag the format or
manufacture a server-authenticated merged parent.

The separate `journal-cells-parts.yml` workflow accepts `actor` and one fixed
`journal_parent`. It masks the actor from event JSON before exporting environment,
requires `/app/build-info.json.sha == GITHUB_SHA` before any capture, and runs the
two commands sequentially. They use separate read-only transactions, not one
simultaneous parent snapshot. Each ciphertext is copied outside the artifact
folder into quarantine, envelope/hash checked, then atomically approved. An
always finalizer validates the exact manifest allowlist before enabling upload.
A failed part retains completed independent ciphertext proofs with an explicit
partial manifest; capture is never falsely marked complete. Raw logs, source
notes and plaintext payloads are not uploaded. Temporary folders are always
removed.

Private orchestration uses a separate `verified-journal-cell-parts/1` index.
Each part retains its own authenticated ciphertext/plaintext SHA, path, run,
commit and capture timestamp. A parent is `proof_type=authenticated_parts` only
when both exact parts authenticate, all20 roots are present and every overlapping
row across all12 core/evidence tables is identical. A parent has no synthetic
ciphertext or plaintext path. Different run IDs may represent retries, but one
fixed deployed head is required. Already verified proofs are retained; uncertain
POST state is reconciled rather than blindly retried. The global consumer also
checks overlaps with primary captures, with temporal drift held explicitly.
One completed pair contributes one logical batch and20 seeds to the existing
90/1791 denominator. Partial pairs contribute no complete-parent coverage.
Coverage is pinned current-fall evidence, not all years or newly unregistered
courses, and never authorizes a data repair.
