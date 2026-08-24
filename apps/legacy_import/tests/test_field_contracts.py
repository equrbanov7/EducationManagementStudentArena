from collections.abc import Mapping
from dataclasses import replace

import pytest

from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacyFieldContractError,
    LegacyProjectedRow,
    LegacySafeProjection,
    LegacySourceFieldContract,
    compile_safe_projection,
    is_credential_field,
)

STUDENT_SOURCE_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "father_name",
    "fincode",
    "sex",
    "image",
    "email",
    "password",
    "show_password",
    "group_id",
    "speciality_id",
    "join_date",
    "who_is_added",
    "added_date",
    "update_date",
    "status",
    "last_ip",
    "telegram",
    "birthday",
    "phone",
    "card_number",
    "azadedildi",
    "order_no",
    "order_date",
    "freeze_from",
    "freeze_to",
    "yekun_yoxla",
    "tg_chat_id",
    "payment_amount",
    "payment_type",
    "education_type",
    "education_level",
    "gender",
    "entry_year",
    "entry_score",
)

WORKER_SOURCE_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "father_name",
    "birthday",
    "sex",
    "image",
    "phone",
    "email",
    "password",
    "pin_for_lock",
    "department_id",
    "added_date",
    "update_date",
    "last_ip",
    "who_is_added",
    "kollec_or_uni",
    "teacher_type",
    "inzibati",
    "last_login_time",
)


@pytest.mark.parametrize(
    "field_name",
    [
        "password",
        "PASSWORD",
        "password2",
        "passwd",
        "pwd",
        "show_password",
        "showPassword",
        "PIN",
        "pin_for_lock",
        "pinForLock",
        "PINForLock",
        "pincode",
        "secret",
        "client_secret",
        "clientSecret",
        "token",
        "refreshToken",
        "otp",
        "api_key",
        "apiKey",
        "APIKEY",
        "credential",
        "credential_blob",
        "PassWord",
        "PASSWORDHASH",
    ],
)
def test_credential_aliases_are_detected_case_and_style_independently(field_name):
    assert is_credential_field(field_name) is True


@pytest.mark.parametrize("field_name", ["fincode", "discipline_id", "secretary_id", "tokenization_rule"])
def test_safe_identifiers_are_not_rejected_by_substring(field_name):
    assert is_credential_field(field_name) is False


@pytest.mark.parametrize(
    "field_name",
    [
        "api-key",
        "id, password",
        "pаssword",  # Cyrillic small a, not ASCII a.
        "passｗord",  # Full-width w.
        "show_password\u200b",  # Zero-width space.
    ],
)
def test_invalid_or_unicode_confusable_identifiers_fail_closed_without_echo(field_name):
    with pytest.raises(LegacyFieldContractError) as exc_info:
        is_credential_field(field_name)

    assert exc_info.value.code == "legacy_field_identifier_invalid"
    assert field_name not in str(exc_info.value)


@pytest.mark.parametrize(
    "forbidden_field",
    ["password", "PASSWORD", "showPassword", "passwd", "pwd", "pinForLock", "clientSecret", "apiKey"],
)
def test_denylist_overrides_an_explicit_allowlist(forbidden_field):
    with pytest.raises(LegacyFieldContractError) as exc_info:
        LegacySourceFieldContract(
            source_table="students",
            version="test-v1",
            allowed_fields=("id", forbidden_field),
        )

    assert exc_info.value.code == "legacy_credential_field_forbidden"
    assert forbidden_field not in str(exc_info.value)


@pytest.mark.parametrize(
    ("contract", "source_fields", "credential_count"),
    [
        (STUDENT_IDENTITY_FIELDS, STUDENT_SOURCE_FIELDS, 2),
        (WORKER_IDENTITY_FIELDS, WORKER_SOURCE_FIELDS, 2),
    ],
)
def test_audited_identity_contracts_select_no_credential_columns(
    contract,
    source_fields,
    credential_count,
):
    projection = compile_safe_projection(contract, discovered_fields=source_fields)
    sql = projection.mysql_select_statement()

    assert projection.field_names == contract.allowed_fields
    assert projection.credential_field_count == credential_count
    assert projection.source_field_count == len(source_fields)
    assert projection.excluded_field_count == len(source_fields) - len(contract.allowed_fields)
    assert sql.startswith("SELECT `id`, ")
    assert sql.endswith(f" FROM `{contract.source_table}`")
    assert "password" not in sql.casefold()
    assert "pin_for_lock" not in sql.casefold()
    assert set(projection.to_safe_log_dict()) == {
        "contract_fingerprint",
        "credential_field_count",
        "excluded_field_count",
        "projected_field_count",
        "source_field_count",
        "validation_result",
    }


def test_projection_requires_every_allowlisted_column_and_rejects_case_drift():
    with pytest.raises(LegacyFieldContractError, match="legacy_required_field_missing"):
        compile_safe_projection(
            STUDENT_IDENTITY_FIELDS,
            discovered_fields=tuple(field_name for field_name in STUDENT_SOURCE_FIELDS if field_name != "entry_year"),
        )

    case_drift = tuple(
        "First_Name" if field_name == "first_name" else field_name for field_name in STUDENT_SOURCE_FIELDS
    )
    with pytest.raises(LegacyFieldContractError, match="legacy_required_field_case_drift"):
        compile_safe_projection(STUDENT_IDENTITY_FIELDS, discovered_fields=case_drift)


def test_unknown_source_columns_remain_default_denied():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=(*STUDENT_SOURCE_FIELDS, "future_profile_note", "apiKey"),
    )

    assert "future_profile_note" not in projection.field_names
    assert "future_profile_note" not in projection.mysql_select_statement()
    assert "apiKey" not in projection.mysql_select_statement()
    assert projection.credential_field_count == 3
    assert projection.excluded_field_count == len(STUDENT_SOURCE_FIELDS) + 2 - len(projection.field_names)


def test_projected_row_rejects_select_star_shape_before_reading_any_value():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_SOURCE_FIELDS,
    )
    raw_value = "never-echo-this-plaintext"
    unsafe_row = {
        **{field_name: f"safe-{position}" for position, field_name in enumerate(projection.field_names)},
        "show_password": raw_value,
    }

    with pytest.raises(LegacyFieldContractError) as exc_info:
        projection.accept_extracted_row(unsafe_row)

    assert exc_info.value.code == "legacy_row_shape_mismatch"
    assert raw_value not in str(exc_info.value)
    assert "show_password" not in str(exc_info.value)


class _ExplodingMapping(Mapping):
    def __iter__(self):
        return iter(STUDENT_IDENTITY_FIELDS.allowed_fields)

    def __len__(self):
        return len(STUDENT_IDENTITY_FIELDS.allowed_fields)

    def __getitem__(self, _key):
        raise RuntimeError("never-echo-this-secret")

    def keys(self):
        return STUDENT_IDENTITY_FIELDS.allowed_fields


class _MaliciousKey:
    def __eq__(self, _other):
        raise RuntimeError("never-echo-this-key-value")


class _UnexpectedKeyMapping(Mapping):
    def __init__(self):
        self.value_reads = 0

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        return len(STUDENT_IDENTITY_FIELDS.allowed_fields)

    def __getitem__(self, _key):
        self.value_reads += 1
        return "never-read-this-value"

    def keys(self):
        return (*STUDENT_IDENTITY_FIELDS.allowed_fields[:-1], _MaliciousKey())


def test_row_read_failure_is_sanitized():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_SOURCE_FIELDS,
    )

    with pytest.raises(LegacyFieldContractError) as exc_info:
        projection.accept_extracted_row(_ExplodingMapping())

    assert exc_info.value.code == "legacy_row_read_failed"
    assert "never-echo-this-secret" not in str(exc_info.value)


def test_untrusted_row_key_fails_before_comparison_or_value_access():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_SOURCE_FIELDS,
    )
    row = _UnexpectedKeyMapping()

    with pytest.raises(LegacyFieldContractError) as exc_info:
        projection.accept_extracted_row(row)

    assert exc_info.value.code == "legacy_row_shape_mismatch"
    assert row.value_reads == 0
    assert "never-echo-this-key-value" not in str(exc_info.value)
    assert "never-read-this-value" not in str(exc_info.value)


def test_projected_row_transform_export_and_repr_contain_allowlisted_values_only():
    projection = compile_safe_projection(
        WORKER_IDENTITY_FIELDS,
        discovered_fields=WORKER_SOURCE_FIELDS,
    )
    row = {field_name: f"allowed-{position}" for position, field_name in enumerate(projection.field_names)}
    projected = projection.accept_extracted_row(row)

    assert projected.to_transform_dict() == row
    assert projected.to_export_dict() == row
    assert set(projected.to_transform_dict()).isdisjoint({"password", "pin_for_lock"})
    assert set(projected.to_export_dict()).isdisjoint({"password", "pin_for_lock"})
    assert set(projected.to_safe_log_dict()) == {
        "contract_fingerprint",
        "field_count",
        "validation_result",
    }
    assert all(value not in repr(projected) for value in row.values())
    assert all(value not in str(projected.to_safe_log_dict()) for value in row.values())


def test_contract_and_projection_reprs_expose_no_field_names():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_SOURCE_FIELDS,
    )

    assert "fincode" not in repr(STUDENT_IDENTITY_FIELDS)
    assert "fincode" not in repr(projection)
    assert "password" not in repr(projection)


@pytest.mark.parametrize(
    ("source_table", "allowed_fields", "code"),
    [
        ("students JOIN workers", ("id",), "legacy_field_identifier_invalid"),
        ("students", ("id", "ID"), "legacy_field_duplicate"),
        ("students", (), "legacy_field_allowlist_empty"),
    ],
)
def test_contract_rejects_raw_sql_duplicate_and_empty_allowlist(source_table, allowed_fields, code):
    with pytest.raises(LegacyFieldContractError) as exc_info:
        LegacySourceFieldContract(
            source_table=source_table,
            version="test-v1",
            allowed_fields=allowed_fields,
        )

    assert exc_info.value.code == code


def test_projection_and_row_cannot_be_constructed_around_the_contract_factory():
    raw_value = "never-echo-this-credential"

    with pytest.raises(LegacyFieldContractError) as projection_error:
        LegacySafeProjection(
            source_table="students",
            field_names=("id`, `password",),
            contract_fingerprint="f" * 64,
            source_field_count=1,
            excluded_field_count=0,
            credential_field_count=0,
        )
    with pytest.raises(LegacyFieldContractError) as row_error:
        LegacyProjectedRow(
            field_names=("password",),
            fingerprint="f" * 64,
            values=(raw_value,),
        )

    assert projection_error.value.code == "legacy_projection_factory_required"
    assert row_error.value.code == "legacy_projected_row_factory_required"
    assert "password" not in str(projection_error.value)
    assert raw_value not in str(row_error.value)


def test_compiled_projection_cannot_be_replaced_with_a_raw_select_fragment():
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_SOURCE_FIELDS,
    )

    with pytest.raises(LegacyFieldContractError) as exc_info:
        replace(projection, field_names=("id`, `password",))

    assert exc_info.value.code == "legacy_projection_factory_required"
    assert "password" not in str(exc_info.value)
