"""Immutable code-compiled scopes for the existing available-history projection.

Only internal fixed wrappers construct these; no request, command or settings
selector is accepted by any public recovery/history endpoint.
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CompiledHistoryScope:
    prefix: str
    undo_operation: str
    cases_json: str
    source_keys_json: str

    @property
    def cases(self):
        return {int(key): value for key, value in json.loads(self.cases_json).items()}

    @property
    def source_keys(self):
        return json.loads(self.source_keys_json)


def approved_history_scope(value):
    """Object identity closes the internal extension to the one compiled scope."""
    from ..source28_spec import HISTORY_SCOPE

    return value is HISTORY_SCOPE
