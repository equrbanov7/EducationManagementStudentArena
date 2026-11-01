"""Mask the operator before exposing only one fixed supplementary parent selection."""

import json
import os
import re
import sys
from pathlib import Path

from journal_cells_part_scope import PARENTS


def main():
    try:
        inputs = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["inputs"]
        if not isinstance(inputs, dict) or set(inputs) != {"actor", "journal_parent"}:
            raise ValueError
        actor, parent = inputs["actor"], inputs["journal_parent"]
        if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor) or parent not in PARENTS:
            raise ValueError
        print("::add-mask::" + actor, flush=True)
        with open(os.environ["GITHUB_ENV"], "a") as stream:
            stream.write(f"ACTOR={actor}\nJOURNAL_PARENT={parent}\n")
        print(f"journal_part_selection: parent={parent}", flush=True)
        return 0
    except Exception:
        print("fixed_part_inputs_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
