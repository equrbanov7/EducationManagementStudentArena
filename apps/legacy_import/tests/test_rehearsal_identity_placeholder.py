"""P0-2: e-poçt qüsuru olan sətir hesabsız qalmır — yer-tutucu qaydası."""

from types import MappingProxyType, SimpleNamespace

import pytest

from apps.legacy_import.services.account_cutover import (
    AccountCutoverOutcome,
    ProjectedAccountIdentity,
    TargetIdentitySnapshot,
    classify_projected_account_cutover,
    deny_all_email_trust,
)
from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    compile_safe_projection,
)
from apps.legacy_import.services.rehearsal_identity_placeholder import (
    EMAIL_SHAPE_RULES,
    PLACEHOLDER_EMAIL_DOMAIN,
    apply_email_placeholders,
    is_placeholder_email,
    needs_placeholder,
    placeholder_email,
    substituted_identity,
)

_EMPTY_SNAPSHOT = TargetIdentitySnapshot(usernames=MappingProxyType({}), emails=MappingProxyType({}), row_count=0)


def _identity(contract, legacy_pk, *, email, entity_type):
    projection = compile_safe_projection(contract, discovered_fields=contract.allowed_fields)
    values = {field_name: None for field_name in contract.allowed_fields}
    values["id"] = legacy_pk
    values["email"] = email
    return ProjectedAccountIdentity(
        projected_row=projection.accept_extracted_row(values),
        proposed_username=f"myedu.{entity_type}.{legacy_pk}",
    )


def _cohort_row(entity_type, legacy_pk, identity):
    from apps.legacy_import.services.rehearsal_identity_phase import _CohortRow

    return _CohortRow(
        source_table="students" if entity_type == "student" else "workers",
        entity_type=entity_type,
        legacy_pk=legacy_pk,
        source_row_hash="a" * 64,
        identity=identity,
    )


def _context():
    return SimpleNamespace(
        authoritative_email_policy=deny_all_email_trust,
        target_identity_snapshot=_EMPTY_SNAPSHOT,
    )


def test_the_placeholder_follows_the_username_convention():
    assert placeholder_email("student", 1285) == f"myedu.student.1285@{PLACEHOLDER_EMAIL_DOMAIN}"
    assert placeholder_email("worker", 381) == f"myedu.worker.381@{PLACEHOLDER_EMAIL_DOMAIN}"
    assert is_placeholder_email(placeholder_email("student", 7)) is True
    assert is_placeholder_email("real@wcu.edu.az") is False


@pytest.mark.parametrize("rule_code", sorted(EMAIL_SHAPE_RULES))
def test_every_email_shape_rule_requests_a_placeholder(rule_code):
    assert needs_placeholder((rule_code,)) is True
    assert needs_placeholder((rule_code, "legacy_account_email_untrusted")) is True


def test_a_username_side_problem_never_requests_a_placeholder():
    """Kimlik açarı e-poçt DEYİL — username qüsuru karantində qalmalıdır."""

    assert needs_placeholder(("legacy_account_email_invalid", "legacy_account_username_collision")) is False
    assert needs_placeholder(("legacy_account_username_duplicate_source",)) is False
    assert needs_placeholder(()) is False
    assert needs_placeholder(("legacy_account_email_untrusted",)) is False


def test_the_substituted_row_keeps_the_contract_shape():
    identity = _identity(STUDENT_IDENTITY_FIELDS, 1285, email="broken@", entity_type="student")
    patched = substituted_identity(identity, entity_type="student", legacy_pk=1285)

    assert patched.source_kind == "student"
    assert tuple(patched.projected_row.keys()) == STUDENT_IDENTITY_FIELDS.allowed_fields
    assert patched.projected_row["email"] == placeholder_email("student", 1285)
    assert patched.proposed_username == identity.proposed_username
    # Mənbə sətri DƏYİŞMİR — orijinal obyekt toxunulmazdır.
    assert identity.projected_row["email"] == "broken@"


def test_a_duplicate_email_pair_becomes_two_stageable_rows():
    """14 toqquşma klasterinin nüvəsi: HƏR İKİ tərəf hesab almalıdır."""

    rows = [
        _cohort_row(
            "student", 1285, _identity(STUDENT_IDENTITY_FIELDS, 1285, email="x@wcu.edu.az", entity_type="student")
        ),
        _cohort_row("worker", 381, _identity(WORKER_IDENTITY_FIELDS, 381, email="x@wcu.edu.az", entity_type="worker")),
    ]
    first = classify_projected_account_cutover(
        [row.identity for row in rows],
        authoritative_email_policy=deny_all_email_trust,
        target_identity_snapshot=_EMPTY_SNAPSHOT,
    )
    assert all(item.outcome is AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED for item in first)

    patched, reclassified, count = apply_email_placeholders(_context(), rows, first)

    assert count == 2
    assert [row.identity.projected_row["email"] for row in patched] == [
        placeholder_email("student", 1285),
        placeholder_email("worker", 381),
    ]
    # Yeganə qalan qayda «etibarlı deyil»dir → contact-pending zolağı (staged edilə bilər).
    assert all(item.outcome is AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED for item in reclassified)
    assert all(item.rule_codes == ("legacy_account_email_untrusted",) for item in reclassified)
    # Toqquşma faktı İTMİR: orijinal kodlar sətirdə saxlanılır.
    assert all("legacy_account_email_duplicate_source" in row.placeholder_rules for row in patched)
    # Mənbə sübutu (row hash) toxunulmur.
    assert [row.source_row_hash for row in patched] == ["a" * 64, "a" * 64]


def test_an_invalid_email_row_is_substituted_and_a_clean_row_is_untouched():
    rows = [
        _cohort_row("student", 10, _identity(STUDENT_IDENTITY_FIELDS, 10, email="sohretaga", entity_type="student")),
        _cohort_row(
            "student", 11, _identity(STUDENT_IDENTITY_FIELDS, 11, email="ok@wcu.edu.az", entity_type="student")
        ),
    ]
    first = classify_projected_account_cutover(
        [row.identity for row in rows],
        authoritative_email_policy=deny_all_email_trust,
        target_identity_snapshot=_EMPTY_SNAPSHOT,
    )

    patched, _reclassified, count = apply_email_placeholders(_context(), rows, first)

    assert count == 1
    assert patched[0].identity.projected_row["email"] == placeholder_email("student", 10)
    assert patched[1].identity.projected_row["email"] == "ok@wcu.edu.az"
    assert patched[1].placeholder_rules == ()


def test_a_cohort_without_email_problems_is_returned_unchanged():
    rows = [_cohort_row("student", 1, _identity(STUDENT_IDENTITY_FIELDS, 1, email="a@b.test", entity_type="student"))]
    first = classify_projected_account_cutover(
        [row.identity for row in rows],
        authoritative_email_policy=deny_all_email_trust,
        target_identity_snapshot=_EMPTY_SNAPSHOT,
    )

    patched, reclassified, count = apply_email_placeholders(_context(), rows, first)

    assert count == 0
    assert patched is rows and reclassified is first
