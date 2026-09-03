"""Legacy uzlaşdırma hesabatının tenant və paylaşım sərhədləri."""

from __future__ import annotations

import pytest

from scripts.legacy_reconcile import target_sql
from scripts.legacy_reconcile.collect import collect_target_facts
from scripts.legacy_reconcile.render_detail import render_sample
from scripts.legacy_reconcile.sampling import collect_sample

ORGANIZATION_ID = "9f8e7d6c-1111-4222-8333-444455556666"
RUN_ID = "8a7b6c5d-2222-4333-8444-555566667777"


class _Target:
    def __init__(self, rows_by_label=None):
        self.organization_id = ORGANIZATION_ID
        self.rows_by_label = rows_by_label or {}
        self.calls = []

    def query(self, label, sql, params=None):
        self.calls.append((label, sql, params))
        return list(self.rows_by_label.get(label, []))


class _Source:
    def __init__(self):
        self.calls = []

    def query(self, label, sql):
        self.calls.append((label, sql))
        rows = {
            "nümunə hovuzu": [["7", "Məxfi Ad", "Qrup-42", "Məxfi ixtisas"]],
            "nümunə xanaları": [],
            "jurnal → fənn": [],
            "nümunə yekun": [],
        }
        return rows[label]


def _attested_run():
    return (
        "rehearsal",
        "succeeded",
        "a" * 64,
        100,
        "2026-08-29 10:00:00",
        "2026-08-29 11:00:00",
        90,
        5,
        5,
        ORGANIZATION_ID,
    )


def test_target_collection_attests_run_before_any_broad_query_and_scopes_every_call():
    target = _Target({"run attestasiyası": [_attested_run()]})

    facts = collect_target_facts(target, run_id=RUN_ID)

    assert facts["attested"] is True
    assert facts["organization_id"] == ORGANIZATION_ID
    assert target.calls[0][0] == "run attestasiyası"
    assert target.calls[0][2] == (RUN_ID, ORGANIZATION_ID)
    assert all(ORGANIZATION_ID in params for _label, _sql, params in target.calls[1:])


def test_target_collection_fails_closed_before_broad_query_when_attestation_fails():
    target = _Target()

    with pytest.raises(RuntimeError, match="legacy_reconcile_run_attestation_failed"):
        collect_target_facts(target, run_id=RUN_ID)

    assert [call[0] for call in target.calls] == ["run attestasiyası"]


def test_target_sql_counts_users_through_tenant_membership_only():
    assert "COUNT(DISTINCT user_id) FROM organizations_membership" in target_sql.ENTITY_COUNTS_SQL
    assert "SELECT 'auth_user', COUNT(*) FROM auth_user" not in target_sql.ENTITY_COUNTS_SQL
    assert "WITH scope AS (SELECT %s::uuid AS organization_id)" in target_sql.ENTITY_COUNTS_SQL
    assert "organization_id = (SELECT organization_id FROM scope)" in target_sql.QUALITY_SQL


def test_sample_target_queries_receive_attested_organization_and_report_is_pii_safe():
    target = _Target(
        {
            "nümunə şəxsiyyət": [
                (701, "Məxfi Ad", "Qrup-42", "Məxfi ixtisas", "active", True),
            ],
            "nümunə yazılışlar": [],
        }
    )
    source = _Source()
    target_facts = {
        "organization_id": ORGANIZATION_ID,
        "students": {"7": "701"},
        "enrollments": {},
    }

    students = collect_sample(source, target, target_facts, size=1, seed=20260827)
    markdown = render_sample({"sample": students, "sample_seed": 20260827})

    assert students[0]["sample_label"] == "Nümunə 01"
    assert [call[2] for call in target.calls] == [
        (ORGANIZATION_ID, [701]),
        (ORGANIZATION_ID, [701]),
    ]
    for secret in ("Məxfi Ad", "Qrup-42", "Məxfi ixtisas", "`#7`", "auth.user #701"):
        assert secret not in markdown
    assert "Nümunə 01" in markdown
