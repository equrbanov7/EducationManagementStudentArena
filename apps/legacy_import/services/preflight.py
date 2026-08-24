"""Read-only custody and integrity checks for a legacy SQL snapshot."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
_CREATE_TABLE_PATTERN = re.compile(rb"(?im)^[ \t]*CREATE[ \t]+TABLE\b")
_MARKER_OVERLAP = 256
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")


class LegacySourcePreflightError(Exception):
    """A sanitized preflight failure that never carries source details."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LegacySourcePreflightResult:
    basename: str
    size: int
    digest: str
    table_count: int
    secure_mode: str
    validation_result: str = "passed"

    def to_safe_dict(self) -> dict[str, object]:
        """Return the deliberately small, non-sensitive command payload."""

        return {
            "basename": self.basename,
            "digest": self.digest,
            "secure_mode": self.secure_mode,
            "size": self.size,
            "table_count": self.table_count,
            "validation_result": self.validation_result,
        }


@dataclass(frozen=True)
class _SourceSnapshot:
    device: int
    inode: int
    size: int
    mtime_ns: int
    owner_uid: int
    mode: int


def _snapshot_from_stat(source_stat: os.stat_result) -> _SourceSnapshot:
    return _SourceSnapshot(
        device=source_stat.st_dev,
        inode=source_stat.st_ino,
        size=source_stat.st_size,
        mtime_ns=getattr(
            source_stat,
            "st_mtime_ns",
            int(source_stat.st_mtime * 1_000_000_000),
        ),
        owner_uid=source_stat.st_uid,
        mode=stat.S_IMODE(source_stat.st_mode),
    )


def _validate_expectations(
    expected_sha256: str,
    expected_size_bytes: int,
    expected_table_count: int,
) -> str:
    if not isinstance(expected_sha256, str) or not _SHA256_PATTERN.fullmatch(expected_sha256):
        raise LegacySourcePreflightError("invalid_expected_sha256")
    if not isinstance(expected_size_bytes, int) or expected_size_bytes < 0:
        raise LegacySourcePreflightError("invalid_expected_size")
    if not isinstance(expected_table_count, int) or expected_table_count < 0:
        raise LegacySourcePreflightError("invalid_expected_table_count")
    return expected_sha256.lower()


def _validate_file_type(source_stat: os.stat_result) -> None:
    if stat.S_ISLNK(source_stat.st_mode):
        raise LegacySourcePreflightError("source_symlink")
    if not stat.S_ISREG(source_stat.st_mode):
        raise LegacySourcePreflightError("source_not_regular")


def _validate_custody(source_stat: os.stat_result) -> None:
    if source_stat.st_uid != os.getuid():
        raise LegacySourcePreflightError("source_owner_mismatch")
    if stat.S_IMODE(source_stat.st_mode) & 0o077:
        raise LegacySourcePreflightError("source_permissions_insecure")


def _count_new_markers(data: bytes, carry_length: int) -> int:
    return sum(match.end() > carry_length for match in _CREATE_TABLE_PATTERN.finditer(data))


def _stream_source(file_descriptor: int, chunk_size: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    table_count = 0
    carry = b""

    while True:
        chunk = os.read(file_descriptor, chunk_size)
        if not chunk:
            break
        digest.update(chunk)
        marker_window = carry + chunk
        table_count += _count_new_markers(marker_window, len(carry))
        carry = marker_window[-_MARKER_OVERLAP:]

    return digest.hexdigest(), table_count


def _safe_lstat(source: str) -> os.stat_result:
    try:
        return os.lstat(source)
    except OSError:
        raise LegacySourcePreflightError("source_unavailable") from None


def _safe_open(source: str) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(source, flags)
    except OSError:
        raise LegacySourcePreflightError("source_open_failed") from None


def _safe_fstat(file_descriptor: int) -> os.stat_result:
    try:
        return os.fstat(file_descriptor)
    except OSError:
        raise LegacySourcePreflightError("source_stat_failed") from None


def _assert_snapshot_unchanged(
    expected: _SourceSnapshot,
    actual_stat: os.stat_result,
) -> None:
    _validate_file_type(actual_stat)
    if _snapshot_from_stat(actual_stat) != expected:
        raise LegacySourcePreflightError("source_changed")


def inspect_legacy_source(
    *,
    source: str,
    expected_sha256: str,
    expected_size_bytes: int,
    expected_table_count: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> LegacySourcePreflightResult:
    """Validate a SQL snapshot without loading it into memory or writing to a DB."""

    normalized_sha256 = _validate_expectations(
        expected_sha256,
        expected_size_bytes,
        expected_table_count,
    )
    if not isinstance(chunk_size, int) or chunk_size <= 0:
        raise LegacySourcePreflightError("invalid_chunk_size")

    path_stat = _safe_lstat(source)
    _validate_file_type(path_stat)
    _validate_custody(path_stat)
    expected_snapshot = _snapshot_from_stat(path_stat)

    file_descriptor = _safe_open(source)
    try:
        opened_stat = _safe_fstat(file_descriptor)
        _assert_snapshot_unchanged(expected_snapshot, opened_stat)
        _validate_custody(opened_stat)

        if opened_stat.st_size != expected_size_bytes:
            raise LegacySourcePreflightError("source_size_mismatch")

        try:
            actual_sha256, actual_table_count = _stream_source(
                file_descriptor,
                chunk_size,
            )
        except OSError:
            raise LegacySourcePreflightError("source_read_failed") from None

        final_descriptor_stat = _safe_fstat(file_descriptor)
        _assert_snapshot_unchanged(expected_snapshot, final_descriptor_stat)
        final_path_stat = _safe_lstat(source)
        _assert_snapshot_unchanged(expected_snapshot, final_path_stat)

        if not hmac.compare_digest(actual_sha256, normalized_sha256):
            raise LegacySourcePreflightError("source_sha256_mismatch")
        if actual_table_count != expected_table_count:
            raise LegacySourcePreflightError("source_table_count_mismatch")

        return LegacySourcePreflightResult(
            basename=os.path.basename(source),
            size=opened_stat.st_size,
            digest=actual_sha256,
            table_count=actual_table_count,
            secure_mode=f"{stat.S_IMODE(opened_stat.st_mode):04o}",
        )
    finally:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
