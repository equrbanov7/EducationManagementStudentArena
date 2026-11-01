"""Fixed-four diagnostics: code locations and closed tokens, never exception values."""

import re
import traceback
from pathlib import Path

STAGES = {
    "input",
    "capture",
    "encrypt",
    "verify_head",
    "prepare",
    "remote_setup",
    "source_capture",
    "copy_cipher",
    "verify_cipher",
    "write_manifest",
    "publish_output",
}
CLASSES = {
    "exception",
    "valueerror",
    "typeerror",
    "keyerror",
    "attributeerror",
    "overflowerror",
    "programmingerror",
    "operationalerror",
    "databaseerror",
    "integrityerror",
    "dataerror",
    "interfaceerror",
    "internalerror",
    "permissiondenied",
    "validationerror",
    "oserror",
    "fileexistserror",
    "filenotfounderror",
    "snapshoterror",
    "timeouterror",
    "timeoutexpired",
    "invalidtag",
    "runtimeerror",
    "undefinedcolumn",
    "undefinedtable",
    "undefinedfunction",
    "insufficientprivilege",
    "readonlysqltransaction",
    "querycanceled",
    "numericvalueoutofrange",
    "invalidtextrepresentation",
}
GUARDS = {
    "unclassified",
    "four_cell_audit_shape_budget_exceeded",
    "four_cell_history_row_budget_exceeded",
    "four_cell_readonly_pg_required",
    "four_cell_atomic_pg_required",
    "four_cell_audit_byte_budget_exceeded",
    "four_cell_change_budget_exceeded",
    "fresh_postgresql_transaction_required",
    "active_fixed_tenant_required",
    "active_fixed_tenant_superuser_required",
    "four_cell_history_output_budget_exceeded",
    "syllabus_query_or_time_budget_exceeded",
    "syllabus_row_budget_exceeded",
    "workflow_run_required",
    "fixed_public_key_required",
    "fixed_history_summary_required",
    "history_ciphertext_invalid",
    "history_ciphertext_sha_changed",
    "followup_transport_failed",
    "followup_command_refused",
    "pinned_head_required",
    "deployed_head_changed",
    "fixed_history_actor_required",
    "source_capture_failed",
    "source_diagnostic_output_budget",
}
FIELDS = ("stage", "class", "cause", "module", "function", "line", "guard")


def describe(exc, stage):
    """No str/repr(exc), locals, SQL, paths, actor names or arbitrary exception args."""

    def name(value):
        token = type(value).__name__.lower()
        return token if token in CLASSES else "exception"

    code = exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], str) else None
    fields = {
        "stage": stage if stage in STAGES else "input",
        "class": name(exc),
        "cause": name(exc.__cause__) if exc.__cause__ is not None else "exception",
        "module": "unknown",
        "function": "unknown",
        "line": 0,
        "guard": code if code in GUARDS else "unclassified",
    }
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if not any(part in frame.filename for part in ("/apps/workload/", "/core/", "/scripts/ops/")):
            continue
        module = Path(frame.filename).stem
        if re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", module) and re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", frame.name):
            fields.update(module=module, function=frame.name, line=frame.lineno)
            break
    return fields


def render(fields):
    if (
        set(fields) != set(FIELDS)
        or fields["stage"] not in STAGES
        or fields["class"] not in CLASSES
        or fields["cause"] not in CLASSES
        or fields["guard"] not in GUARDS
        or type(fields["line"]) is not int
        or not 0 <= fields["line"] <= 999999
        or any(not re.fullmatch(r"[a-z_][a-z0-9_]{0,63}", fields[k]) for k in ("module", "function"))
    ):
        raise ValueError("invalid_fixed_diagnostic")
    return " ".join(f"{key}={fields[key]}" for key in FIELDS)


def parse(output):
    found = []
    for line in output.splitlines():
        if not line.startswith("four_cell_history_diagnostic: "):
            continue
        pairs = re.findall(r"([a-z]+)=([a-z0-9_]+)", line)
        fields = dict(pairs)
        if len(pairs) != len(FIELDS) or len(fields) != len(FIELDS):
            continue
        try:
            fields["line"] = int(fields["line"])
            if line != "four_cell_history_diagnostic: " + render(fields):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        found.append(fields)
    if len(found) == 1:
        return found[0]
    return None
