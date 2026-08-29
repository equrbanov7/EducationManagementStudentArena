"""Köhnə bal-vərəqi export arxivinin itkisizlik testləri."""

import hashlib
import zlib

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalEvidenceError
from apps.legacy_import.services.rehearsal_legacy_grade_artifacts import MAX_ARTIFACT_BYTES
from apps.legacy_import.services.rehearsal_legacy_grade_artifacts_phase import (
    DERIVED_DIGEST_NAMESPACE,
    LEGACY_GRADE_ARTIFACTS_PHASE_KEY,
    LegacyGradeArtifactsPhase,
)
from apps.legacy_import.services.rehearsal_legacy_grade_facts_phase import LEGACY_GRADE_FACTS_PHASE_KEY
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

PHASE_KEYS = (LEGACY_GRADE_FACTS_PHASE_KEY, LEGACY_GRADE_ARTIFACTS_PHASE_KEY)


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="legacy_grade_artifact_actor",
        email="legacy-grade-artifact@example.test",
        password="test-only",
    )


def _run(actor, slug, rows):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    context = harness.context(
        rows_by_table=rows,
        run=run,
        organization=org,
        actor=actor,
        phase_keys=PHASE_KEYS,
    )
    report = LegacyGradeArtifactsPhase().run(context)
    return org, run, context, report


def _artifacts(org):
    return django_apps.get_model("registrar", "LegacyGradeArtifact").objects.filter(organization=org)


def test_phase_preserves_every_export_payload_hash_size_and_bytes(actor):
    payloads = (
        "<table><tr><td>tələbə-1</td><td>45</td></tr></table>",
        "<table><tr><td>tələbə-2</td><td>0</td></tr></table>",
    )
    rows = harness.tables(
        score_sheet_exports=[
            harness.score_sheet_export_row(11, data=payloads[0]),
            harness.score_sheet_export_row(12, data=payloads[1]),
        ]
    )

    org, run, _context, report = _run(actor, "grade-artifacts-complete", rows)

    artifacts = list(_artifacts(org).order_by("source_pk"))
    assert [item.source_pk for item in artifacts] == [11, 12]
    for artifact, text in zip(artifacts, payloads):
        raw = text.encode("utf-8")
        assert artifact.payload_size_bytes == len(raw)
        assert artifact.payload_sha256 == hashlib.sha256(raw).hexdigest()
        assert zlib.decompress(bytes(artifact.payload_zlib)) == raw
        assert artifact.requires_exam_center_review is True
    assert dict(report.state_counts) == {"legacy_grade_artifacts_materialised": 2}
    assert (
        LegacyEntityMap.objects.filter(
            created_run=run,
            entity_type="legacy_grade_artifact",
            state=LegacyEntityMap.State.MIGRATED,
        ).count()
        == 2
    )


def test_artifact_phase_replay_and_ledger_rebuild_are_deterministic(actor):
    rows = harness.tables(score_sheet_exports=[harness.score_sheet_export_row(21, data="<table>sealed</table>")])
    org, run, context, first = _run(actor, "grade-artifacts-replay", rows)

    second = LegacyGradeArtifactsPhase().run(context)
    rebuilt = phase_report_from_ledger(run, phase=LegacyGradeArtifactsPhase(), plan=harness.plan(rows))

    assert _artifacts(org).count() == 1
    assert first.phase_digest == second.phase_digest == rebuilt.phase_digest
    assert LegacyGradeArtifactsPhase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE


def test_artifact_phase_rejects_empty_and_oversized_payloads(actor):
    for suffix, payload in (("empty", ""), ("large", "x" * (MAX_ARTIFACT_BYTES + 1))):
        rows = harness.tables(score_sheet_exports=[harness.score_sheet_export_row(31, data=payload)])
        org = harness.organization(actor, f"grade-artifacts-{suffix}")
        run = harness.running_run(org, actor, table_plan=harness.plan(rows))
        context = harness.context(
            rows_by_table=rows,
            run=run,
            organization=org,
            actor=actor,
            phase_keys=PHASE_KEYS,
        )
        with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
            LegacyGradeArtifactsPhase().run(context)
        assert exc_info.value.code == "legacy_grade_artifact_payload_size_invalid"
