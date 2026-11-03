"""2026-11-03: prod-data-ops dispatches both repairs with validated UUID inputs and count-only output."""

from pathlib import Path

import yaml

PATH = Path(__file__).resolve().parents[1] / ".github/workflows/prod-data-ops.yml"


def _case(text, command):
    return text.split(f"            {command})\n", 1)[1].split("              ;;", 1)[0]


def test_commands_are_whitelisted_choices():
    workflow = yaml.safe_load(PATH.read_text())
    trigger = workflow.get("on", workflow.get(True))
    inputs = trigger["workflow_dispatch"]["inputs"]
    assert len(inputs) <= 25  # GitHub workflow_dispatch limiti — yeni giriş əlavə edilmir
    options = inputs["command"]["options"]
    assert "clear_stale_off_schedule_flags" in options
    assert "fix_offering_subject" in options


def test_clear_stale_flags_case():
    case = _case(PATH.read_text(), "clear_stale_off_schedule_flags")
    assert "^(Payız|Yaz|Yay) 20[0-9]{2}/20[0-9]{2}$" in case
    assert '"--offering=$BATCH"' in case
    assert "::add-mask::$actor" in case


def test_fix_offering_subject_case_validates_every_uuid():
    case = _case(PATH.read_text(), "fix_offering_subject")
    for needle in (
        'match "$BATCH" "^${uuid_re}$"',
        'match "$ROW_SUBJECT" "^${uuid_re}$"',
        'match "$ROW_GROUP" "^${uuid_re}$"',
        '"--offering=$BATCH" "--subject=$ROW_SUBJECT"',
        '"--row=$ROW_GROUP"',
        "--detach-syllabus=",
        "--attach-syllabus=",
        "::add-mask::$actor",
    ):
        assert needle in case


def test_output_is_count_lines_only():
    text = PATH.read_text()
    branch = text.split('[ "$COMMAND" = "fix_offering_subject" ]; then', 1)[1].split("          elif", 1)[0]
    assert "off_schedule_flags|offering_subject_fix" in branch
    assert 'cat "$RUNNER_TEMP/summary.log"' in branch
    assert 'cat "$RUNNER_TEMP/out.log"' not in branch
