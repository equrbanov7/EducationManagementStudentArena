"""One pinned Aida two-group course/load alias, using the same reviewed host protection."""

import json
import os
import sys
from pathlib import Path

from reviewed_two_catalog import Refused, execute


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(
            event.get("inputs"),
            os.environ,
            command="repair_reviewed_aida_catalog",
            prefix="reviewed_aida_catalog: ",
            expected_rows=2,
        )
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("reviewed_aida_catalog_host_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
