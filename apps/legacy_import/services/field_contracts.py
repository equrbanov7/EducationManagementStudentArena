"""Credential-safe, default-deny field contracts for legacy source reads.

The legacy database contains authentication material that must never enter the
extract/transform/log/export pipeline.  Callers declare an audited field
allowlist and receive a fixed SQL projection; arbitrary select fragments are
deliberately not accepted.

These contracts make rows credential-safe, not PII-free.  Projected identity
fields must still stay inside the controlled migration environment.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_VERSION_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_CAMEL_BOUNDARY_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TRAILING_DIGITS_PATTERN = re.compile(r"\d+\Z")
_ROW_FACTORY_TOKEN = object()

# Exact lexical markers intentionally take precedence over every allowlist.
_CREDENTIAL_TOKENS = frozenset(
    {
        "credential",
        "credentials",
        "otp",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "pin",
        "pwd",
        "secret",
        "token",
    }
)
_CREDENTIAL_COMPOUNDS = frozenset(
    {
        "apikey",
        "apitoken",
        "clientkey",
        "clientsecret",
        "hashedpassword",
        "otptoken",
        "passwordhash",
        "passwordsalt",
        "pincode",
        "pinforlock",
        "privatekey",
        "recoverycode",
        "refreshtoken",
        "securityanswer",
        "sessiontoken",
        "showpassword",
    }
)


class LegacyFieldContractError(ValueError):
    """Sanitized contract failure containing only a stable rule code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validated_identifier(value: object) -> str:
    if type(value) is not str or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise LegacyFieldContractError("legacy_field_identifier_invalid")
    return value


def _identifier_tokens(identifier: str) -> tuple[str, ...]:
    separated = _CAMEL_BOUNDARY_PATTERN.sub("_", identifier)
    return tuple(_TRAILING_DIGITS_PATTERN.sub("", token.casefold()) for token in separated.split("_") if token)


def is_credential_field(field_name: object) -> bool:
    """Return whether a valid ASCII SQL identifier denotes auth material.

    Invalid or Unicode-confusable identifiers fail closed instead of being
    normalized into a potentially different database column.
    """

    identifier = _validated_identifier(field_name)
    tokens = _identifier_tokens(identifier)
    compact = "".join(tokens)
    return (
        bool(_CREDENTIAL_TOKENS.intersection(tokens))
        or compact in _CREDENTIAL_TOKENS
        or compact in _CREDENTIAL_COMPOUNDS
    )


def _validated_field_names(values: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise LegacyFieldContractError("legacy_field_list_invalid")

    fields = tuple(_validated_identifier(value) for value in values)
    if not fields and not allow_empty:
        raise LegacyFieldContractError("legacy_field_allowlist_empty")
    if len({value.casefold() for value in fields}) != len(fields):
        raise LegacyFieldContractError("legacy_field_duplicate")
    return fields


def _contract_fingerprint(source_table: str, version: str, fields: tuple[str, ...]) -> str:
    material = "\x1f".join((source_table, version, *fields)).encode("ascii")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, repr=False)
class LegacySourceFieldContract:
    """Versioned allowlist for one source-table projection.

    Every allowlisted field is required.  Adding/removing a field is therefore
    an explicit contract-version change rather than silent schema drift.
    """

    source_table: str
    version: str
    allowed_fields: tuple[str, ...]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        source_table = _validated_identifier(self.source_table)
        if type(self.version) is not str or not _VERSION_PATTERN.fullmatch(self.version):
            raise LegacyFieldContractError("legacy_field_contract_version_invalid")
        allowed_fields = _validated_field_names(self.allowed_fields)
        if any(is_credential_field(field_name) for field_name in allowed_fields):
            raise LegacyFieldContractError("legacy_credential_field_forbidden")

        object.__setattr__(self, "source_table", source_table)
        object.__setattr__(self, "allowed_fields", allowed_fields)
        object.__setattr__(
            self,
            "fingerprint",
            _contract_fingerprint(source_table, self.version, allowed_fields),
        )

    def __repr__(self) -> str:
        return "LegacySourceFieldContract(" f"field_count={len(self.allowed_fields)}, fingerprint={self.fingerprint!r})"


class LegacyProjectedRow(Mapping[str, Any]):
    """Immutable projected row whose repr/log metadata never include values."""

    __slots__ = ("_field_names", "_fingerprint", "_values")

    def __init__(
        self,
        *,
        field_names: tuple[str, ...],
        fingerprint: str,
        values: tuple[Any, ...],
        _factory_token: object = None,
    ) -> None:
        if _factory_token is not _ROW_FACTORY_TOKEN:
            raise LegacyFieldContractError("legacy_projected_row_factory_required")
        self._field_names = field_names
        self._fingerprint = fingerprint
        self._values = values

    def __getitem__(self, key: str) -> Any:
        if type(key) is not str:
            raise KeyError("legacy_projected_field_unavailable")
        try:
            position = self._field_names.index(key)
        except Exception:
            raise KeyError("legacy_projected_field_unavailable") from None
        return self._values[position]

    def __iter__(self) -> Iterator[str]:
        return iter(self._field_names)

    def __len__(self) -> int:
        return len(self._field_names)

    def __repr__(self) -> str:
        return "LegacyProjectedRow(" f"field_count={len(self)}, contract_fingerprint={self._fingerprint!r})"

    def to_transform_dict(self) -> dict[str, Any]:
        """Return only the already-projected, credential-safe transform fields."""

        return dict(zip(self._field_names, self._values, strict=True))

    def to_export_dict(self) -> dict[str, Any]:
        """Return the same explicit allowlist for controlled internal export."""

        return self.to_transform_dict()

    def to_safe_log_dict(self) -> dict[str, object]:
        """Return metadata only; row values and field names are intentionally absent."""

        return {
            "contract_fingerprint": self._fingerprint,
            "field_count": len(self),
            "validation_result": "passed",
        }


@dataclass(frozen=True, repr=False, init=False)
class LegacySafeProjection:
    """Compiled fixed projection built solely from an audited contract."""

    source_table: str
    field_names: tuple[str, ...]
    contract_fingerprint: str
    source_field_count: int
    excluded_field_count: int
    credential_field_count: int

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise LegacyFieldContractError("legacy_projection_factory_required")

    @classmethod
    def _from_contract(
        cls,
        *,
        contract: LegacySourceFieldContract,
        source_field_count: int,
        credential_field_count: int,
    ) -> LegacySafeProjection:
        if type(source_field_count) is not int or source_field_count < len(contract.allowed_fields):
            raise LegacyFieldContractError("legacy_source_field_count_invalid")
        excluded_field_count = source_field_count - len(contract.allowed_fields)
        if (
            type(credential_field_count) is not int
            or credential_field_count < 0
            or credential_field_count > excluded_field_count
        ):
            raise LegacyFieldContractError("legacy_credential_field_count_invalid")

        projection = object.__new__(cls)
        object.__setattr__(projection, "source_table", contract.source_table)
        object.__setattr__(projection, "field_names", contract.allowed_fields)
        object.__setattr__(projection, "contract_fingerprint", contract.fingerprint)
        object.__setattr__(projection, "source_field_count", source_field_count)
        object.__setattr__(projection, "excluded_field_count", excluded_field_count)
        object.__setattr__(projection, "credential_field_count", credential_field_count)
        return projection

    def __repr__(self) -> str:
        return (
            "LegacySafeProjection("
            f"field_count={len(self.field_names)}, source_field_count={self.source_field_count}, "
            f"excluded_field_count={self.excluded_field_count}, "
            f"credential_field_count={self.credential_field_count}, "
            f"contract_fingerprint={self.contract_fingerprint!r})"
        )

    def mysql_select_statement(self) -> str:
        """Return a fixed SELECT with validated, quoted identifiers only."""

        columns = ", ".join(f"`{field_name}`" for field_name in self.field_names)
        return f"SELECT {columns} FROM `{self.source_table}`"

    def accept_extracted_row(self, row: Mapping[str, Any]) -> LegacyProjectedRow:
        """Validate exact cursor shape before any field value is accessed."""

        if not isinstance(row, Mapping):
            raise LegacyFieldContractError("legacy_row_shape_invalid")
        try:
            row_keys = tuple(row.keys())
        except Exception:
            raise LegacyFieldContractError("legacy_row_shape_invalid") from None
        try:
            validated_row_keys = _validated_field_names(row_keys)
        except LegacyFieldContractError:
            raise LegacyFieldContractError("legacy_row_shape_mismatch") from None
        if validated_row_keys != self.field_names:
            raise LegacyFieldContractError("legacy_row_shape_mismatch")

        try:
            values = tuple(row[field_name] for field_name in self.field_names)
        except Exception:
            raise LegacyFieldContractError("legacy_row_read_failed") from None
        return LegacyProjectedRow(
            field_names=self.field_names,
            fingerprint=self.contract_fingerprint,
            values=values,
            _factory_token=_ROW_FACTORY_TOKEN,
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        """Return schema attestation metadata without source column names."""

        return {
            "contract_fingerprint": self.contract_fingerprint,
            "credential_field_count": self.credential_field_count,
            "excluded_field_count": self.excluded_field_count,
            "projected_field_count": len(self.field_names),
            "source_field_count": self.source_field_count,
            "validation_result": "passed",
        }


def compile_safe_projection(
    contract: LegacySourceFieldContract,
    *,
    discovered_fields: Sequence[str],
) -> LegacySafeProjection:
    """Compile an allowlisted projection from source schema metadata only."""

    if not isinstance(contract, LegacySourceFieldContract):
        raise LegacyFieldContractError("legacy_field_contract_invalid")
    fields = _validated_field_names(discovered_fields)
    discovered_lookup = {field_name.casefold(): field_name for field_name in fields}
    if any(field_name.casefold() not in discovered_lookup for field_name in contract.allowed_fields):
        raise LegacyFieldContractError("legacy_required_field_missing")
    if any(discovered_lookup[field_name.casefold()] != field_name for field_name in contract.allowed_fields):
        raise LegacyFieldContractError("legacy_required_field_case_drift")

    credential_field_count = sum(is_credential_field(field_name) for field_name in fields)
    return LegacySafeProjection._from_contract(
        contract=contract,
        source_field_count=len(fields),
        credential_field_count=credential_field_count,
    )


STUDENT_IDENTITY_FIELDS = LegacySourceFieldContract(
    source_table="students",
    version="identity-v1",
    allowed_fields=(
        "id",
        "first_name",
        "last_name",
        "father_name",
        "fincode",
        "sex",
        "email",
        "group_id",
        "speciality_id",
        "join_date",
        "status",
        "birthday",
        "phone",
        "education_type",
        "education_level",
        "gender",
        "entry_year",
    ),
)

WORKER_IDENTITY_FIELDS = LegacySourceFieldContract(
    source_table="workers",
    version="identity-v1",
    allowed_fields=(
        "id",
        "first_name",
        "last_name",
        "father_name",
        "birthday",
        "sex",
        "phone",
        "email",
        "department_id",
        "kollec_or_uni",
        "teacher_type",
        "inzibati",
    ),
)

# Structure contracts (academic_structure phase).  Every archive-only column of
# these tables — phone, adress, img_url, note, text, who_is_added, added_date,
# update_date — is deliberately left out: the projection is default-deny, so a
# field that is not migrated is a field that never leaves the source.
DEPARTMENT_STRUCTURE_FIELDS = LegacySourceFieldContract(
    source_table="departments",
    version="structure-v1",
    allowed_fields=(
        "id",
        "name",
        "department_id",
        "department_types_id",
        "kollec_or_uni",
    ),
)

SPECIALITY_STRUCTURE_FIELDS = LegacySourceFieldContract(
    source_table="speciality",
    version="structure-v1",
    allowed_fields=(
        "id",
        "department_id",
        "name",
        "speciality_code",
    ),
)

GROUP_STRUCTURE_FIELDS = LegacySourceFieldContract(
    source_table="groups",
    version="structure-v1",
    allowed_fields=(
        "id",
        "speciality_id",
        "department_id",
        "name",
        "sector",
        "eyani_qiyabi",
        "bak_or_mag",
        "start_year",
        "curricula_id",
        "kollec_or_uni",
    ),
)

# Catalogue contracts (academic_catalog phase).  Archive-only columns and
# ``curricula.lesson_code`` (unresolved semantics, Q8) stay out: the projection
# is default-deny, so a field that is not migrated never leaves the source.
LESSON_CATALOG_FIELDS = LegacySourceFieldContract(
    source_table="lessons",
    version="catalog-v1",
    allowed_fields=(
        "id",
        "name",
        "lesson_code",
        "type",
        "department_id",
        "only_az",
    ),
)

CURRICULUM_CATALOG_FIELDS = LegacySourceFieldContract(
    source_table="curricula",
    version="catalog-v1",
    allowed_fields=(
        "id",
        "speciality_id",
        "from_date",
        "to_date",
        "eyani_qiyabi",
        "bak_or_mag",
    ),
)

CURRICULUM_PLAN_FIELDS = LegacySourceFieldContract(
    source_table="curricula_plan",
    version="catalog-v1",
    allowed_fields=(
        "id",
        "curricula_id",
        "lesson_id",
        "lesson_code",
        "type",
        "semestr",
        "kredit",
        "lesson_before_id",
        "saat_aks",
        "saat_as",
        "saat_muh",
        "saat_sem",
        "saat_lab",
        "saat_prak",
    ),
)

# Student status contract (sar_materialisation phase, V-18).  ``students`` is
# claimed by ``identity_cohort``; this second, deliberately tiny contract exists
# because widening ``STUDENT_IDENTITY_FIELDS`` would change its fingerprint and
# therefore every identity ``source_row_hash`` ever recorded.  ``azadedildi`` is
# the only usable release flag in the live dump (``status`` is 0 for every row).
STUDENT_STATUS_FIELDS = LegacySourceFieldContract(
    source_table="students",
    version="status-v1",
    allowed_fields=(
        "id",
        "azadedildi",
    ),
)
