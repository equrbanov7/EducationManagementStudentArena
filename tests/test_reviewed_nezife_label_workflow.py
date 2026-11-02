import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
spec = importlib.util.spec_from_file_location("nezife_host", ROOT / "scripts/ops/reviewed_nezife_label.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def valid():
    return dict(status="dry_run", applied=False, count=1, baseline="a" * 64, receipt=None)


def test_exact_safe_summary():
    assert host.summary(host.PREFIX + json.dumps(valid()), apply=False, undo="").startswith(host.PREFIX)


@pytest.mark.parametrize(
    "change",
    [
        {"count": 2},
        {"count": True},
        {"status": "applied"},
        {"applied": True},
        {"receipt": "secret"},
        {"baseline": "wrong"},
        {"private": "student"},
    ],
)
def test_false_or_private_summary_refused(change):
    with pytest.raises(ValueError):
        host.summary(host.PREFIX + json.dumps({**valid(), **change}), apply=False, undo="")


def test_scope_workflow_has_no_arbitrary_targets():
    text = (ROOT / ".github/workflows/reviewed-nezife-label.yml").read_text()
    assert "production-deploy" in text
    assert "lesson_id:" not in text and "teacher_id:" not in text


def test_exact_production_source_scope():
    import ast

    tree = ast.parse((ROOT / "apps/registrar/reviewed_nezife_label.py").read_text())
    names = {"ORG", "PERIOD", "OFFERING", "GROUP", "SUBJECT", "TEACHER", "LESSON", "SLOT", "ROOM", "REASON"}
    fixed = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names
    }
    assert fixed == dict(
        ORG="526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
        PERIOD="a4f88744-8d49-4772-84ef-c28a96c3b372",
        OFFERING="3326514c-9fe5-4bc0-8167-3f949fa9a054",
        GROUP="0a1783b0-1f13-41ff-bbeb-51652b68b70d",
        SUBJECT="86f4817f-802b-43ec-9774-ec7f869a35ad",
        TEACHER=8420,
        LESSON="6a2f801f-a770-48c2-aa3c-73043c461865",
        SLOT="c7b0d9bc-03fa-4398-a676-4a9747b73b1d",
        ROOM=379,
        REASON="Cədvələ aiddir bu dərs",
    )
