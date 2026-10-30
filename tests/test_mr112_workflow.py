"""The exact repair is dispatchable with baseline guard and sanitized output."""

from pathlib import Path

import yaml


def test_mr112_dispatch_contract():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/prod-data-ops.yml"
    text = path.read_text()
    workflow = yaml.safe_load(text)
    trigger = workflow.get("on", workflow.get(True))
    assert "repair_mr112_hours" in trigger["workflow_dispatch"]["inputs"]["command"]["options"]
    case = text.split("            repair_mr112_hours)\n", 1)[1].split("              ;;", 1)[0]
    assert '--expected-baseline "$ROW_SUBJECT"' in case
    assert "^[0-9a-f]{64}$" in case
    assert '[ "$APPLY" = "true" ] && [ -z "$ROW_SUBJECT" ]' in case
    output = text.split('elif [ "$COMMAND" = "repair_mr112_hours" ]; then', 1)[1].split("          elif", 1)[0]
    assert "^mr112_hours: mode=" in output
    assert 'cat "$RUNNER_TEMP/summary.log"' in output
    assert 'cat "$RUNNER_TEMP/out.log"' not in output
    assert 'rm -f "$RUNNER_TEMP/out.log"' in output
