"""Fixed actor/pack dispatch inputs; no raw event or identity printed before masking."""

import json
import os
import re
import sys
from pathlib import Path

from syllabus_export_pack import batches


def validate(value):
    if not isinstance(value, dict) or set(value) != {"actor", "pack"}:
        raise ValueError("fixed_syllabus_pack_inputs_required")
    actor, name = value["actor"], value["pack"]
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("valid_actor_required")
    batches(name)
    return actor, name


def main():
    try:
        actor, name = validate(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
        print("::add-mask::" + actor, flush=True)
        with open(os.environ["GITHUB_ENV"], "a") as stream:
            stream.write(f"ACTOR={actor}\nSYLLABUS_PACK={name}\n")
        print("syllabus_pack_selection: pack=" + name, flush=True)
        return 0
    except Exception:
        print("syllabus_pack_inputs_refused", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
