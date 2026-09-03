import hashlib
import io
import json

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.legacy_import.services import preflight
from apps.legacy_import.services.preflight import (
    LegacySourcePreflightError,
    inspect_legacy_source,
)


def _write_secure_source(tmp_path, content, name="legacy.sql"):
    source = tmp_path / name
    source.write_bytes(content)
    source.chmod(0o600)
    return source


def _expected(content, table_count):
    return {
        "expected_sha256": hashlib.sha256(content).hexdigest(),
        "expected_size_bytes": len(content),
        "expected_table_count": table_count,
    }


def test_preflight_passes_with_streamed_markers_and_safe_json(tmp_path):
    content = (
        b"-- schema\n"
        b"CREATE TABLE `students` (`id` int);\n"
        b"  create   table `groups` (`id` int);\n"
        b"INSERT INTO notes VALUES ('CREATE TABLE hidden');\n"
    )
    source = _write_secure_source(tmp_path, content)

    result = inspect_legacy_source(
        source=str(source),
        chunk_size=5,
        **_expected(content, table_count=2),
    )

    assert result.to_safe_dict() == {
        "basename": "legacy.sql",
        "digest": hashlib.sha256(content).hexdigest(),
        "secure_mode": "0600",
        "size": len(content),
        "table_count": 2,
        "validation_result": "passed",
    }

    stdout = io.StringIO()
    call_command(
        "legacy_import_preflight",
        source=str(source),
        stdout=stdout,
        **_expected(content, table_count=2),
    )
    payload = json.loads(stdout.getvalue())
    assert set(payload) == {
        "basename",
        "digest",
        "secure_mode",
        "size",
        "table_count",
        "validation_result",
    }
    assert str(tmp_path) not in stdout.getvalue()
    assert "INSERT INTO" not in stdout.getvalue()


def test_preflight_rejects_symlink(tmp_path):
    content = b"CREATE TABLE real_table (id int);\n"
    target = _write_secure_source(tmp_path, content, "target.sql")
    source = tmp_path / "link.sql"
    source.symlink_to(target)

    with pytest.raises(LegacySourcePreflightError, match="source_symlink"):
        inspect_legacy_source(source=str(source), **_expected(content, 1))


def test_preflight_rejects_group_or_other_permissions(tmp_path):
    content = b"CREATE TABLE unsafe_table (id int);\n"
    source = _write_secure_source(tmp_path, content)
    source.chmod(0o640)

    with pytest.raises(
        LegacySourcePreflightError,
        match="source_permissions_insecure",
    ):
        inspect_legacy_source(source=str(source), **_expected(content, 1))


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"expected_size_bytes": 1}, "source_size_mismatch"),
        ({"expected_sha256": "f" * 64}, "source_sha256_mismatch"),
        ({"expected_table_count": 2}, "source_table_count_mismatch"),
    ],
)
def test_preflight_rejects_integrity_mismatch(tmp_path, overrides, error_code):
    content = b"CREATE TABLE expected_table (id int);\n"
    source = _write_secure_source(tmp_path, content)
    expectations = _expected(content, 1)
    expectations.update(overrides)

    with pytest.raises(LegacySourcePreflightError, match=error_code):
        inspect_legacy_source(source=str(source), **expectations)


def test_preflight_detects_source_mutation_during_read(tmp_path, monkeypatch):
    content = b"CREATE TABLE stable_table (id int);\n"
    source = _write_secure_source(tmp_path, content)
    original_stream_source = preflight._stream_source

    def stream_then_mutate(file_descriptor, chunk_size):
        result = original_stream_source(file_descriptor, chunk_size)
        with source.open("ab") as source_file:
            source_file.write(b"-- changed\n")
        return result

    monkeypatch.setattr(preflight, "_stream_source", stream_then_mutate)

    with pytest.raises(LegacySourcePreflightError, match="source_changed"):
        inspect_legacy_source(source=str(source), **_expected(content, 1))


def test_command_error_does_not_leak_path_or_source_content(tmp_path):
    content = b"CREATE TABLE credential_material (password text);\n"
    source = _write_secure_source(tmp_path, content, "private-source.sql")

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "legacy_import_preflight",
            source=str(source),
            expected_sha256="0" * 64,
            expected_size_bytes=len(content),
            expected_table_count=1,
        )

    error_text = str(exc_info.value)
    assert str(tmp_path) not in error_text
    assert source.name not in error_text
    assert "credential_material" not in error_text
    assert "password" not in error_text
    assert "source_sha256_mismatch" in error_text


def test_preflight_rejects_non_regular_source_without_path_leakage(tmp_path):
    source = tmp_path / "private-directory"
    source.mkdir()
    source.chmod(0o700)

    with pytest.raises(LegacySourcePreflightError) as exc_info:
        inspect_legacy_source(
            source=str(source),
            expected_sha256="0" * 64,
            expected_size_bytes=0,
            expected_table_count=0,
        )

    assert exc_info.value.code == "source_not_regular"
    assert str(source) not in str(exc_info.value)
