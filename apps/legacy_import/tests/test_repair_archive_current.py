"""P0-1 «hazırda oxuyan» süzgəci — ``legacy_repair_archive_status --active-period``.

Sahib (2026-09-25): yalnız HAZIRDA OXUYANLARIN arxivi açılsın.  Sınanan müqavilə:

1. süzgəc verilməyəndə qərar əvvəlki kimidir (2 291-lik tam əhatə);
2. ``--active-period`` verilərsə yalnız həmin dövrlərdən birində yazılışı olan
   tələbə ``restore`` alır, qalanı ``keep_archived / not_current``;
3. dövr etiketi canlı yazılışdan ``"<akademik il> <ad>"`` formasında qurulur;
4. əmr bayrağı təkrarlana bilir və dry-run heç nə yazmır;
5. ``--current-plan``: DƏQİQ siyahı yazılış planının möhürlənmiş başlığından
   (sha256 məcburi, siyahısız plan rədd olunur).
"""

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.services import repair_archive
from apps.legacy_import.services.repair_plan_file import RepairPlanError, read_plan_header, write_plan
from apps.legacy_import.tests import journal_points_harness as harness
from apps.legacy_import.tests import test_repair_commands as base

pytestmark = pytest.mark.django_db
CURRENT = "2025/2026 Yaz"
_SLUG = base._SLUG
_summary_value = base._summary_value
# P0-1 dəstinin fixture-ləri (arxiv kohortu: səhv arxiv 1970, buraxılmış 200, ledger-siz 999).
actor = base.actor
organization = base.organization
run = base.run
archived_cohort = base.archived_cohort


@pytest.fixture()
def evidence(monkeypatch, archived_cohort):
    """1970 (səhv arxiv) yalnız ``labels`` dövrlərində oxuyub."""

    state = {"labels": {CURRENT}}

    def fake(_organization, user_pks):
        user_pk = archived_cohort[1970].pk
        wanted = {int(pk) for pk in user_pks}
        return {user_pk: [3, "2022/2023", "2025/2026", set(state["labels"])]} if user_pk in wanted else {}

    monkeypatch.setattr(repair_archive, "_enrollment_evidence", fake)
    return state


def _reason_count(output, reason):
    """``  səbəb: <kod> … : N`` — açarın özündə iki nöqtə var, ona görə son ``:``-dan kəsilir."""

    for line in output.splitlines():
        left, _separator, right = line.rpartition(" : ")
        if left.strip() == f"səbəb: {reason}":
            return right.strip()
    raise AssertionError(f"xülasədə səbəb tapılmadı: {reason!r}\n{output}")


def _decisions(organization, **kwargs):
    return {item.legacy_pk: item for item in repair_archive.plan_decisions(organization, **kwargs)}


def test_without_a_period_filter_the_decision_is_unchanged(organization, evidence):
    evidence["labels"] = {"2022/2023 Payız"}
    assert _decisions(organization)["1970"].action == "restore"


def test_a_student_with_an_enrolment_in_the_active_period_is_restored(organization, evidence):
    decision = _decisions(organization, active_periods=(CURRENT,))["1970"]
    assert (decision.action, decision.reason) == ("restore", "no_admission_year_only")


def test_a_student_without_a_current_enrolment_stays_archived(organization, evidence):
    evidence["labels"] = {"2023/2024 Yaz", "2024/2025 Payız"}
    decision = _decisions(organization, active_periods=(CURRENT, "2025/2026 Payız"))["1970"]
    assert (decision.action, decision.reason) == ("keep_archived", "not_current")


def test_the_filter_never_restores_a_departed_student(organization, evidence, archived_cohort):
    decisions = _decisions(organization, active_periods=(CURRENT,))
    assert (decisions["200"].action, decisions["200"].reason) == ("keep_archived", "source_azadedildi")


def test_blank_period_labels_are_ignored(organization, evidence):
    evidence["labels"] = {"2022/2023 Payız"}
    assert _decisions(organization, active_periods=("", "  "))["1970"].action == "restore"


def test_the_period_label_is_built_from_the_live_enrolment(actor):
    org = harness.organization(actor, "archive-current-label")
    import_run = harness.running_run(org, actor, table_plan=harness.plan(harness.tables()))
    offering, enrollments, _lessons = harness.seed_journal_target(org, actor, import_run.pk, lesson_slots=())
    student_pk = next(iter(enrollments.values())).student_id

    evidence = repair_archive._enrollment_evidence(org, [student_pk])

    label = repair_archive.period_label(offering.period.academic_year, offering.period.name)
    assert label.startswith("2021/2022 ")
    count, earliest, latest, labels = evidence[int(student_pk)]
    assert count >= 1 and earliest == latest == "2021/2022" and label in labels


def test_the_command_accepts_repeated_periods_and_a_dry_run_writes_nothing(organization, evidence, capsys):
    evidence["labels"] = {"2024/2025 Yaz"}
    call_command(
        "legacy_repair_archive_status",
        "--organization",
        _SLUG,
        "--active-period",
        CURRENT,
        "--active-period",
        "2025/2026 Payız",
    )
    output = capsys.readouterr().out
    assert _summary_value(output, "bərpa namizədi (restore)") == "0"
    assert _reason_count(output, "not_current") == "1"
    assert UserProfile.objects.filter(access_state=UserProfile.AccessState.ARCHIVED).count() == 3


def test_the_current_list_restores_only_listed_students(organization, evidence):
    evidence["labels"] = {"2024/2025 Yaz"}  # hədəfdə cari yazılış YOXDUR — siyahı həlledicidir
    assert _decisions(organization, current_legacy={"1970"})["1970"].action == "restore"
    decision = _decisions(organization, current_legacy={"1971"})["1970"]
    assert (decision.action, decision.reason) == ("keep_archived", "not_current")


def _current_plan(tmp_path, listed, *, name="enroll.jsonl.gz"):
    header = {"repair": "journal_enrollments", "current_legacy_students": listed}
    return write_plan(str(tmp_path / name), header=header, records=[])


def test_the_plan_header_reader_checks_the_seal(tmp_path):
    manifest = _current_plan(tmp_path, {"1970": "E3_unknown_cohort_active_spring"})
    header = read_plan_header(manifest.path, expected_sha256=manifest.sha256, repair="journal_enrollments")
    assert header["current_legacy_students"] == {"1970": "E3_unknown_cohort_active_spring"}
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_sha256_mismatch"):
        read_plan_header(manifest.path, expected_sha256="0" * 64, repair="journal_enrollments")
    with pytest.raises(RepairPlanError, match="legacy_repair_plan_repair_mismatch"):
        read_plan_header(manifest.path, expected_sha256=manifest.sha256, repair="lesson_recovery")


def test_the_command_reads_the_current_list_from_the_sealed_plan(organization, evidence, tmp_path, capsys):
    evidence["labels"] = {"2024/2025 Yaz"}
    manifest = _current_plan(tmp_path, {"1970": "E3_unknown_cohort_active_spring"})
    base = ("legacy_repair_archive_status", "--organization", _SLUG, "--current-plan", manifest.path)
    with pytest.raises(CommandError, match="legacy_repair_plan_sha256_required"):
        call_command(*base)
    call_command(*base, "--current-plan-sha256", manifest.sha256)
    output = capsys.readouterr().out
    assert _summary_value(output, "hazırda oxuyan (plan siyahısı)") == "1"
    assert _summary_value(output, "bərpa namizədi (restore)") == "1"
    empty = _current_plan(tmp_path, {}, name="empty.jsonl.gz")
    with pytest.raises(CommandError, match="legacy_repair_current_list_missing"):
        call_command(
            "legacy_repair_archive_status",
            "--organization",
            _SLUG,
            "--current-plan",
            empty.path,
            "--current-plan-sha256",
            empty.sha256,
        )
