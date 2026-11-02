"""Non-DB privacy/completeness/guard tests for fixed forensic-only transport."""

import base64
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.workload.services import source58_audit_chunks as service


def row(body, name="audit-fixed"):
    return name, body, hashlib.sha256(body).hexdigest(), len(body)


@pytest.fixture
def paths(tmp_path):
    key = tmp_path / "public.pem"
    key.write_bytes(b"test-public-only")
    return key, tmp_path / "proof.zip"


def test_cipher_only_disk_and_complete_hashbound_chunk_inventory(paths):
    key, output = paths
    seen = []

    def encrypt(value, public):
        assert public == b"test-public-only"
        seen.append(value)
        return {"ciphertext": "opaque-" + str(len(seen))}

    raw = b'{"changes":"private-QB-IE-contact"}' * 100
    with patch.object(service, "CHUNK_BYTES", 100), patch.object(service, "encrypt", encrypt):
        sha = service.write_bundle([row(raw)], key, output, {"read_only": True, "matched_audit_count": 1})
    assert sha == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        for name in archive.namelist():
            assert b"private-QB" not in archive.read(name)
    chunks, manifest = seen[:-1], seen[-1]
    assert b"".join(base64.b64decode(c["content"]) for c in chunks) == raw
    assert [c["ordinal"] for c in chunks] == list(range(len(chunks)))
    assert manifest["complete"] and manifest["audit_count"] == manifest.get("matched_audit_count", 1)
    assert manifest["eligible_for_apply"] is False
    assert manifest["history_cleared_for_apply"] is False
    assert manifest["inventory"][0]["raw_record_sha256"] == hashlib.sha256(raw).hexdigest()
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failure", ["hash", "bytes", "duplicate", "total", "count", "encrypt"])
def test_bad_proof_never_leaves_partial_bundle(paths, failure):
    key, output = paths
    rows = [row(b"secret")]
    if failure == "hash":
        rows = [("a", b"secret", "0" * 64, 6)]
    elif failure == "bytes":
        rows = [("a", b"secret", row(b"secret")[2], 7)]
    elif failure == "duplicate":
        rows *= 2
    total = 1 if failure == "total" else 100
    count = 0 if failure == "count" else 100
    error = ValueError("secret exception") if failure == "encrypt" else None
    with patch.object(service, "MAX_TOTAL_BYTES", total), patch.object(service, "MAX_AUDITS", count):
        with patch.object(service, "encrypt", return_value={"ciphertext": "opaque"}, side_effect=error):
            with pytest.raises(ValueError):
                service.write_bundle(rows, key, output, {})
    assert not output.exists()


def test_existing_destination_is_never_overwritten_or_removed(paths):
    key, output = paths
    output.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        service.write_bundle([], key, output, {})
    assert output.read_bytes() == b"existing"


def test_native_history_budgets_and_diagnostic_fixed_locator_remain_separate():
    root = Path(__file__).resolve().parents[3]
    native = (root / "apps/workload/services/scoped_snapshot/source58_evidence_history.py").read_text()
    assert "MAX_RAW_AUDIT_BYTES = 8 * 1024 * 1024" in native
    assert 'raise EvidenceLimit("source58_unknown_audit_byte_budget")' in native
    diagnostic = (root / "apps/workload/services/source58_audit_diagnostic.py").read_text()
    assert "REPEATABLE READ READ ONLY" in diagnostic
    assert "validate_fixed_recovery_actor" in diagnostic
    assert "source_points=HISTORY_SCOPE.cases" in diagnostic
    assert "row_to_json" in diagnostic
    command = (root / "apps/workload/management/commands/export_wcu_source58_audit_chunks.py").read_text()
    assert "from None" in command and "encrypted_sha256=" in command


def test_incomplete_inventory_is_not_published(paths):
    key, output = paths
    with patch.object(service, "encrypt", return_value={"ciphertext": "opaque"}):
        with pytest.raises(ValueError, match="incomplete_inventory"):
            service.write_bundle([], key, output, {"matched_audit_count": 1})
    assert not output.exists()


def test_locator_graph_cannot_silently_drift_from_native_closure():
    root = Path(__file__).resolve().parents[3]
    native = (root / "apps/workload/services/scoped_snapshot/source58_evidence.py").read_text()
    start = native.index("def _capture")
    expected = native[native.index("    reader = Rows()", start) : native.index("    claims = _claims", start)]
    expected = expected.replace('    offering_map = {row["id"]: row for row in offerings}\n', "")
    for name in ("_family", "_closure", "_extra_evidence"):
        expected = expected.replace(name + "(", "source." + name + "(")
    actual = (root / "apps/workload/services/source58_audit_scope.py").read_text()
    actual = actual[actual.index("    reader = Rows()") : actual.index("    return {")]
    import ast

    def normalized(text):
        return ast.dump(ast.parse("def scope():\n" + text))

    assert normalized(actual) == normalized(expected)


def test_command_redacts_arbitrary_exception_details(capsys):
    from django.core.management.base import CommandError

    from apps.workload.management.commands import export_wcu_source58_audit_chunks as command

    with patch.object(command, "capture", side_effect=ValueError("private-user-and-QB")):
        with pytest.raises(CommandError, match="^source58_audit_diagnostic_refused$") as error:
            command.Command().handle(actor="operator", public_key="key", output="cipher")
    assert error.value.__suppress_context__
    assert capsys.readouterr() == ("", "")


def test_command_emits_only_cipher_digest(capsys):
    from apps.workload.management.commands import export_wcu_source58_audit_chunks as command

    with patch.object(command, "capture", return_value="a" * 64):
        command.Command().handle(actor="operator", public_key="key", output="cipher")
    assert capsys.readouterr() == ("encrypted_sha256=" + "a" * 64 + "\n", "")
