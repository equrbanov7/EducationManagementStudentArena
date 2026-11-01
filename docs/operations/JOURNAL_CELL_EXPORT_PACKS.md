# Fixed sequential journal audit packs

`workload-scoped-export.yml` accepts either the existing `journal_batch` or the
optional `journal_pack`, never both. Empty selectors retain the metadata export.
The operator comes from validated dispatch JSON and is masked before entering the
step environment. Export scope and permissions remain those of
`export_wcu_journal_cells`: fixed tenant/current fall, real read-only RLS
transaction, at most 25 physical courses including history closure, unchanged row,
cell and encryption budgets. A closure exceeding that limit is held explicitly.

`scripts/ops/journal_export_packs.json` pins 19 packs covering the existing 90
batches exactly once. The first pack contains batches 001 and 002. Remaining packs
contain at most five batches, starting with 089, 043, 076, 077, 082 and 055.
The registry hashes are verified before any command runs; arbitrary lists and IDs
are unsupported. One job executes each existing batch command sequentially.
Each command uses its own read-only transaction, so these are separate captures,
not one globally simultaneous database snapshot.

Each successful batch yields its own `<batch>.enc.json`. A strict safe manifest
records only fixed labels, commit/run identifiers, hashes, counts and allowlisted
failure codes. Only structurally validated encrypted envelopes and that manifest
are uploaded. A failed batch does not prevent later batches in its pack from
running; the final job fails with a partial manifest. Unknown files suppress the
artifact upload. Container and runner temporary files are always removed.
The final safe summary includes the manifest SHA256, and the validated input step
prints an actor-free pack/batch correlation marker.

The private local producer must authenticate each ciphertext with the pinned
existing decoder, check the manifest/log SHA, exact deployed head/run/pack and
individual payload scope, and retain the existing 90-batch consumer index.
A shared run ID does not imply another batch was captured. Completed files from a
failed pack are individually usable after authentication. A retry must retain
previously verified snapshots and accept only missing batches; uncertain dispatch
state requires reconciliation rather than another POST. Neither a partial capture
nor completion of this pinned current-fall registry establishes all-year coverage
or the absence of newly created unregistered courses. Export evidence never
authorizes a data repair.
