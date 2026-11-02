"""prod-data-ops: merge_duplicate_staff — yalnız id-lər, sanitarlaşdırılmış çıxış (sahib 2026-11-03)."""

from pathlib import Path

import yaml


def test_merge_duplicate_staff_dispatch_contract():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/prod-data-ops.yml"
    text = path.read_text()
    workflow = yaml.safe_load(text)
    trigger = workflow.get("on", workflow.get(True))
    assert "merge_duplicate_staff" in trigger["workflow_dispatch"]["inputs"]["command"]["options"]
    assert len(trigger["workflow_dispatch"]["inputs"]) <= 25  # GitHub workflow_dispatch həddi
    case = text.split("            merge_duplicate_staff)\n", 1)[1].split("              ;;", 1)[0]
    assert "'^[0-9]{1,12}:[0-9]{1,12}$'" in case
    assert '"--source-user=${BATCH%%:*}" "--target-user=${BATCH##*:}"' in case
    assert "--reason" in case
    assert "args+=(--force-name-mismatch)" in case
    assert "custom_apply=1" not in case  # --apply ümumi yoldan: əvvəl backup, sonra --apply
    output = text.split('elif [ "$COMMAND" = "merge_duplicate_staff" ]; then', 1)[1].split("          elif", 1)[0]
    assert "^staff_merge(_left)?: " in output
    assert 'cat "$RUNNER_TEMP/summary.log"' in output
    assert 'cat "$RUNNER_TEMP/out.log"' not in output
    assert 'rm -f "$RUNNER_TEMP/out.log"' in output
