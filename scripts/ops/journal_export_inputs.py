"""Read dispatch JSON privately, mask validated actor before exporting step env."""

import json
import os
import re
import sys
from pathlib import Path

from journal_export_pack import BATCH_SHA, ROOT, pack_batches, sha


def validate(inputs):
    if not isinstance(inputs, dict) or not set(inputs) <= {"actor", "journal_batch", "journal_pack"}:
        raise ValueError("fixed_export_inputs_required")
    actor = inputs.get("actor")
    batch, pack = inputs.get("journal_batch", ""), inputs.get("journal_pack", "")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("valid_actor_required")
    if not isinstance(batch, str) or not isinstance(pack, str) or (batch and pack):
        raise ValueError("one_export_selector_required")
    if batch:
        raw = (ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes()
        if sha(raw) != BATCH_SHA or batch not in json.loads(raw)["batches"]:
            raise ValueError("pinned_batch_required")
    if pack:
        pack_batches(pack)
    return actor, batch, pack


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        actor, batch, pack = validate(event.get("inputs"))
    except Exception:
        print("fixed_export_inputs_refused", file=sys.stderr)
        return 2
    # No raw event or value was printed before this workflow masking command.
    print("::add-mask::" + actor, flush=True)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write(f"ACTOR={actor}\nJOURNAL_BATCH={batch}\nJOURNAL_PACK={pack}\n")
    print(f"journal_export_selection: pack={pack or 'none'} batch={batch or 'none'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
