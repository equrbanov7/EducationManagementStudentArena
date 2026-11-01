"""Fixed readonly schedule evidence boundaries and offline decoder validation."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scope = load("test_timetable_scope", ROOT / "scripts/ops/timetable_evidence_scope.py")
spec = scope._spec
HASH = "a" * 64
STAMP = "2026-11-01T12:30:00+00:00"


def valid_payload():
    chosen = scope.selection("timetable-review-008")
    data = {key: [] for key in spec.LIMITS}
    for root in chosen:
        data["offerings"].append(
            {
                "id": root["id"],
                "organization_id": spec.ORG,
                "subject_id": root["subject_id"],
                "period_id": spec.PERIOD,
                "group_id": None,
                "instructor_id": root["teachers"][0],
                "is_active": True,
                "lesson_hours": "60",
                "created_at": STAMP,
                "updated_at": STAMP,
                "raw_record_sha256": HASH,
            }
        )
    data["periods"] = [
        {
            "id": spec.PERIOD,
            "organization_id": spec.ORG,
            "name_sha256": HASH,
            "academic_year": "2026/2027",
            "start_date": "2026-09-15",
            "end_date": "2027-02-01",
            "is_active": True,
            "raw_record_sha256": HASH,
        }
    ]
    return {
        "format": spec.FORMAT,
        "organization_id": spec.ORG,
        "period_id": spec.PERIOD,
        "academic_year": "2026/2027",
        "batch": "timetable-review-008",
        "actor_id": 1,
        "manifest_sha256": spec.MANIFEST_SHA,
        "source_report_sha256": spec.SOURCE_REPORT_SHA,
        "captured_at": STAMP,
        "read_only": True,
        "eligible_for_apply": False,
        "selection": chosen,
        "clock_policy": {
            "standard_times": [["18:40", "20:00"]],
            "explicit_minute_settings": {},
            "organization_settings_sha256": HASH,
            "missing_duration_policy_is_unknown": True,
            "bells_are_not_academic_duration_authority": True,
        },
        "counts": {k: len(v) for k, v in data.items()},
        "data": data,
    }


def test_manifest_is_exact_bounded_partition_of188_roots_and85_teachers():
    all_rows = [r for batch in spec.BATCHES for r in scope.selection(batch)]
    assert len(all_rows) == len({r["id"] for r in all_rows}) == 188
    assert len({t for r in all_rows for t in r["teachers"]}) == 85
    assert all(1 <= len(scope.selection(b)) <= 25 for b in spec.BATCHES)
    for invalid in ("all", "timetable-review-000", spec.ORG, [], None):
        with pytest.raises(ValueError):
            scope.selection(invalid)


def test_minimal_full_scope_capsule_validates():
    assert scope.validate(valid_payload())["eligible_for_apply"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(eligible_for_apply=True),
        lambda p: p.update(read_only=False),
        lambda p: p.update(manifest_sha256=HASH),
        lambda p: p["selection"].pop(),
        lambda p: p["data"]["offerings"].pop(),
        lambda p: p["data"]["offerings"][0].update(organization_id=spec.PERIOD),
        lambda p: p["data"]["offerings"][0].update(score=10),
        lambda p: p["data"]["offerings"][0].update(note="secret contact"),
        lambda p: p["data"].update(marks=[]),
        lambda p: p["clock_policy"]["explicit_minute_settings"].update(secret="password"),
        lambda p: p.update(actor_id=True),
        lambda p: p["data"]["offerings"][0].update(raw_record_sha256="bad"),
    ],
)
def test_decoder_refuses_scope_privacy_and_authority_changes(mutate):
    payload = valid_payload()
    mutate(payload)
    with pytest.raises((ValueError, TypeError)):
        scope.validate(payload)


def test_all_model_projection_fields_exist_without_querying_database():
    from django.apps import apps

    from apps.workload.services.timetable_evidence.data import MODELS

    for table, label in MODELS.items():
        model = apps.get_model(label)
        # Query compilation catches an accidental invented or renamed column.
        model.objects.values(*spec.FIELDS[table]).query.get_compiler("default").as_sql()


def test_workflow_fixed_choices_and_no_mutation_inputs():
    text = (ROOT / ".github/workflows/timetable-evidence-export.yml").read_text()
    for batch in spec.BATCHES:
        assert f"- {batch}" in text
    assert "cancel-in-progress: false" in text
    assert "persist-credentials: false" in text
    assert "--apply" not in text
    assert "retention-days: 1" in text


def test_host_inputs_reject_arbitrary_roots_and_extra_flags(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts/ops"))
    host = load("test_timetable_host", ROOT / "scripts/ops/timetable_evidence_export.py")
    assert host.inputs({"actor": "ops.admin", "batch": spec.BATCHES[0]}) == ("ops.admin", spec.BATCHES[0])
    for value in (
        {"actor": "ops.admin", "batch": "all"},
        {"actor": "x;cat", "batch": spec.BATCHES[0]},
        {"actor": "ops.admin", "batch": spec.BATCHES[0], "ids": [spec.ORG]},
    ):
        with pytest.raises(ValueError):
            host.inputs(value)


def test_no_plaintext_names_notes_or_audit_material_in_contract():
    for fields in spec.FIELDS.values():
        assert not set(fields) & {
            "name",
            "note",
            "groups_note",
            "groups_text",
            "reason",
            "topic",
            "email",
            "username",
            "score",
            "status",
        }
    assert not spec.AUDIT_FIELDS & {"reason", "changes", "old_values", "new_values", "resource_id"}


def test_authenticated_ciphertext_roundtrip_scope_rejection_and_private_output(monkeypatch, tmp_path):
    import base64
    import hashlib
    import json
    import stat

    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from apps.workload.services import scoped_snapshot

    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    fingerprint = hashlib.sha256(der).hexdigest()
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    decoder = load("test_timetable_decrypt", ROOT / "scripts/ops/decrypt_timetable_evidence.py")
    monkeypatch.setattr(scoped_snapshot, "KEY_FINGERPRINT", fingerprint)
    monkeypatch.setattr(decoder, "KEY_FINGERPRINT", fingerprint)
    payload = valid_payload()
    envelope = scoped_snapshot.encrypt(payload, public)
    assert decoder.decrypt_snapshot(json.dumps(envelope).encode(), private) == payload
    output = decoder.write_new_snapshot(payload, tmp_path)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == payload
    corrupted = dict(envelope)
    ciphertext = bytearray(base64.b64decode(corrupted["ciphertext"]))
    ciphertext[-1] ^= 1
    corrupted["ciphertext"] = base64.b64encode(ciphertext).decode()
    with pytest.raises(InvalidTag):
        decoder.decrypt_snapshot(json.dumps(corrupted).encode(), private)
    payload["data"]["offerings"][0]["score"] = 10
    bad_scope = scoped_snapshot.encrypt(payload, public)
    with pytest.raises(ValueError):
        decoder.decrypt_snapshot(json.dumps(bad_scope).encode(), private)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="existing_private_output_directory_required"):
        decoder.write_new_snapshot(valid_payload(), tmp_path)
