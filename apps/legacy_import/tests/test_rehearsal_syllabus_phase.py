"""Phase ``syllabus_migration`` (J12) testləri: köhnə sillabus → ``apps.syllabus``.

Kilidlənən müqavilələr: HTML entity açılması, təsdiqin MƏNBƏYİ (saxta insan
imzası yoxdur), dublikat → versiya nərdivanı, hədəf dosyesi üzrə birləşmə,
fail-closed hallar (fənn həll olunmur, yetim ``uniqid``, ambiqü ``uniqid``) və
idempotentlik.

Gözlənilən dəyərlərin arxasındakı canlı rəqəmlər (2026-08-30,
``emsarena-legacy-source-rehearsal``) docstring-lərdə yazılıb.
"""

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_syllabus_documents import INSTRUCTOR_UNRESOLVED, VERSION_FOLDED
from apps.legacy_import.services.rehearsal_syllabus_phase import (
    DERIVED_DIGEST_NAMESPACE,
    SYLLABUS_MIGRATION_PHASE_KEY,
    SYLLABUS_MIGRATION_PHASE_ORDER,
    SyllabusMigrationPhase,
)
from apps.legacy_import.services.rehearsal_syllabus_source import AMBIGUOUS_UNIQID, ORPHAN_UNIQID
from apps.legacy_import.services.rehearsal_syllabus_targets import (
    DOSSIER_MERGED,
    SUBJECT_UNRESOLVED,
    SYLLABUS_ENTITY_TYPE,
    SYLLABUS_VERSION_MODEL_LABEL,
)
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db

LESSON = 64
OTHER_LESSON = 65
TEACHER = 17
#: Silinmiş işçi (canlı: 956 başlıq, 112 fərqli id) — hədəfdə ``author=NULL``.
GHOST_TEACHER = 900
OTHER_GHOST_TEACHER = 901


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="syllabus_migration_actor", email="syl-actor@example.test", password="test-only"
    )


def _run_phase(
    actor,
    slug,
    *,
    headers,
    weeks=(),
    sections=None,
    lessons=(LESSON,),
    teachers=(TEACHER,),
    notes=None,
):
    """Fazanı sintetik mənbə + seed olunmuş fənn/müəllim xəritəsi ilə işlət."""

    rows = harness.tables(syllabi=list(headers), lesson_topics=list(weeks), sections=dict(sections or {}))
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    for lesson_id in lessons:
        harness.seed_syllabus_subject(org, actor, run.pk, lesson_id)
    for teacher_id in teachers:
        harness.seed_syllabus_teacher(org, actor, run.pk, teacher_id)
    report = SyllabusMigrationPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report


def _versions(org):
    from apps.syllabus.models import SyllabusVersion

    return list(SyllabusVersion.objects.filter(organization=org).order_by("major", "minor"))


def _sections(version):
    return {row.section_id: row.data for row in version.sections.all()}


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=SYLLABUS_ENTITY_TYPE)
    }


def _states(run):
    return {
        observation.entity_map.legacy_pk: observation.state
        for observation in run.entity_observations.filter(entity_map__entity_type=SYLLABUS_ENTITY_TYPE)
    }


# ── forma / qapılar ──────────────────────────────────────────────────────────


def test_the_phase_declares_a_batch_less_syllabus_keyed_shape(db):
    phase = SyllabusMigrationPhase()

    assert phase.phase_key == SYLLABUS_MIGRATION_PHASE_KEY
    # 30 — ``sar_materialisation`` (28) ilə ``journal_periods`` (32) arasında.
    assert phase.order == SYLLABUS_MIGRATION_PHASE_ORDER == 30
    # 12 sillabus cədvəlinin hamısı ``design_gated``-dir → İDDİA EDİLMİR.
    assert phase.source_tables == () and phase.entity_types == (SYLLABUS_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "syllabus_versions_written"
    assert phase.derived_state_key("quarantined") == "syllabus_unresolved"


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        SyllabusMigrationPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_requires_the_catalogue_and_the_identity_cohort():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        SyllabusMigrationPhase().run(harness.context(rows_by_table=rows, phase_keys=("syllabus_migration",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


# ── köçürmə ──────────────────────────────────────────────────────────────────


def test_a_single_syllabus_arrives_approved_without_a_fake_human_approver(actor):
    """Sahibin tələbi: təsdiqlənmiş gəlsin — amma imza UYDURULMASIN."""

    notes = []
    org, run, report = _run_phase(
        actor,
        "syl-single",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1", lesson_id=LESSON, teacher_id=TEACHER)],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-1", movzu="Birinci mövzu")],
        notes=notes,
    )

    version = _versions(org)[0]
    assert (version.status, version.approval_source) == ("approved", "migration")
    assert version.approved_by_id is None and version.locked_at is not None
    assert version.change_kind == "imported"
    assert (version.major, version.minor) == (1, 0)
    # Semestr UYDURULMUR: köhnə bazada semestr sütunu YOXDUR (spec §2).
    assert version.syllabus.period_id is None and version.applies_to_period_id is None
    assert version.syllabus.approved_version_id == version.pk
    assert version.syllabus.author_id is not None
    assert dict(report.state_counts) == {"syllabus_versions_written": 1}
    assert notes == [f"{SYLLABUS_MIGRATION_PHASE_KEY}.records.1", f"{SYLLABUS_MIGRATION_PHASE_KEY}.versions.1"]

    observation = run.entity_observations.get(entity_map__entity_type=SYLLABUS_ENTITY_TYPE)
    assert observation.target_model_label == SYLLABUS_VERSION_MODEL_LABEL
    assert observation.target_pk == str(version.pk)


def test_html_entities_are_decoded_on_the_way_into_the_sections(actor):
    """Canlı ``movzu``-nun 54,716/131,056 sətri entity daşıyır (spec §3)."""

    org, _run, _report = _run_phase(
        actor,
        "syl-entities",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1")],
        weeks=[
            harness.syllabus_week_row(
                1, uniqid="syl-1", movzu="&Ccedil;irkl&#601;nm&#601; &ouml;l&ccedil;&uuml;s&uuml;"
            )
        ],
        sections={
            "sillabus_derslikler": [harness.syllabus_section_row(1, uniqid="syl-1", name="M&uuml;hazir&#601; kursu")]
        },
    )

    data = _sections(_versions(org)[0])
    assert data["week"]["rows"][0]["topic"] == "Çirklənmə ölçüsü"
    assert data["lit"]["primary"] == ["Mühazirə kursu"]


def test_duplicates_become_a_version_ladder_with_one_approved_step(actor):
    """Canlı: 8,248 başlıq → 5,646 cüt; ən böyük ``id``-li aktiv pillə qalib."""

    org, run, report = _run_phase(
        actor,
        "syl-ladder",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-1"),
            harness.syllabus_header_row(2, uniqid="syl-2"),
        ],
        weeks=[
            harness.syllabus_week_row(1, uniqid="syl-1", movzu="Köhnə mövzu"),
            harness.syllabus_week_row(2, uniqid="syl-2", movzu="Yeni mövzu"),
        ],
    )

    versions = _versions(org)
    assert [(version.minor, version.status) for version in versions] == [(0, "archived"), (1, "approved")]
    # Bir dosye, iki versiya — model «bir APPROVED» məhdudiyyətini saxlayır.
    assert len({version.syllabus_id for version in versions}) == 1
    assert versions[1].syllabus.approved_version_id == versions[1].pk
    assert dict(report.state_counts) == {"syllabus_versions_written": 2}
    assert set(_states(run).values()) == {LegacyEntityMap.State.MIGRATED}


def test_content_identical_duplicates_fold_into_one_version(actor):
    """``lesson_id=4, teacher_id=282`` canlı halı: 7 sillabus, eyni 23 mövzu."""

    org, run, _report = _run_phase(
        actor,
        "syl-folded",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-1"),
            harness.syllabus_header_row(2, uniqid="syl-2"),
        ],
        weeks=[
            harness.syllabus_week_row(1, uniqid="syl-1", movzu="Eyni mövzu"),
            harness.syllabus_week_row(2, uniqid="syl-2", movzu="Eyni mövzu"),
        ],
    )

    assert [version.status for version in _versions(org)] == ["approved"]
    # Qatlanan mənbə sətri İTMİR: öz möhürünü alır və qeyd olunur.
    assert _states(run) == {"1": LegacyEntityMap.State.MIGRATED, "2": LegacyEntityMap.State.SKIPPED}
    assert ("2", VERSION_FOLDED) in _issues(run)


def test_an_inactive_only_dossier_gets_no_approved_version(actor):
    """Canlı: 714 başlıq ``active=0`` — «təsdiqlənmiş» yazmaq faktı dəyişərdi."""

    org, _run, _report = _run_phase(
        actor,
        "syl-inactive",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1", active=0)],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-1")],
    )

    version = _versions(org)[0]
    assert version.status == "archived"
    assert version.syllabus.approved_version_id is None


def test_a_syllabus_whose_teacher_was_deleted_is_not_written_at_all(actor):
    """Sahibin qərarı (2026-08-31, spec §9): «lazım deyil, sil getsin, dəymə heç».

    Canlı: 956 başlığın ``teacher_id``-si silinmiş işçiyə baxır.  Əvvəlki plan
    onları ``author=NULL`` ilə köçürürdü — bu test məhz həmin davranışı KİLİDLƏYİRDİ
    və qərardan sonra tərsinə çevrildi.
    """

    org, run, report = _run_phase(
        actor,
        "syl-ghost",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1", teacher_id=GHOST_TEACHER)],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-1")],
    )

    assert _versions(org) == []  # HEÇ NƏ yazılmır
    # …amma qərar İTMİR: karantin deyil, SKIP — səbəbi məlumdur.
    assert _states(run) == {"1": LegacyEntityMap.State.SKIPPED}
    assert _issues(run)[("1", INSTRUCTOR_UNRESOLVED)] == LegacyMigrationIssue.Severity.WARNING
    assert dict(report.state_counts) == {"syllabus_rows_represented": 1}


def test_a_teacherless_ladder_never_opens_a_dossier_to_merge_into(actor):
    """Canlı: 124 fənndə 2+ silinmiş müəllim vardı.

    Əvvəl onların nərdivanları hədəfdə EYNİ ``author=NULL`` dosyesinə düşür və
    ``dossier_merged`` ilə birləşirdi.  Heç biri yazılmadığına görə o birləşmə
    (canlı proqnozda 193 ədəd) ARTIQ YARANMIR — kod səs-küy də buraxmır.
    """

    org, run, _report = _run_phase(
        actor,
        "syl-merge",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-1", teacher_id=GHOST_TEACHER),
            harness.syllabus_header_row(2, uniqid="syl-2", teacher_id=OTHER_GHOST_TEACHER),
        ],
        weeks=[
            harness.syllabus_week_row(1, uniqid="syl-1", movzu="Birinci"),
            harness.syllabus_week_row(2, uniqid="syl-2", movzu="İkinci"),
        ],
    )

    assert _versions(org) == []
    codes = {(legacy_pk, rule_code) for legacy_pk, rule_code in _issues(run)}
    assert ("1", INSTRUCTOR_UNRESOLVED) in codes and ("2", INSTRUCTOR_UNRESOLVED) in codes
    assert not any(rule_code == DOSSIER_MERGED for _legacy_pk, rule_code in codes)


def test_a_live_teacher_on_the_same_subject_is_untouched_by_the_skip(actor):
    """«Sil getsin» YALNIZ müəllimsiz başlığa aiddir — qonşu nərdivan köçürülür."""

    org, run, _report = _run_phase(
        actor,
        "syl-ghost-neighbour",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-1", teacher_id=GHOST_TEACHER),
            harness.syllabus_header_row(2, uniqid="syl-2", teacher_id=TEACHER),
        ],
        weeks=[
            harness.syllabus_week_row(1, uniqid="syl-1", movzu="Kölgə"),
            harness.syllabus_week_row(2, uniqid="syl-2", movzu="Canlı"),
        ],
    )

    versions = _versions(org)
    assert [version.status for version in versions] == ["approved"]
    assert versions[0].syllabus.author_id is not None
    assert _states(run) == {"1": LegacyEntityMap.State.SKIPPED, "2": LegacyEntityMap.State.MIGRATED}


def test_two_subjects_stay_in_two_dossiers(actor):
    org, _run, _report = _run_phase(
        actor,
        "syl-two-subjects",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-1", lesson_id=LESSON),
            harness.syllabus_header_row(2, uniqid="syl-2", lesson_id=OTHER_LESSON),
        ],
        lessons=(LESSON, OTHER_LESSON),
    )

    versions = _versions(org)
    assert len({version.syllabus_id for version in versions}) == 2
    assert {version.status for version in versions} == {"approved"}


# ── fail-closed ──────────────────────────────────────────────────────────────


def test_an_unresolved_subject_is_quarantined_and_nothing_is_written(actor):
    org, run, report = _run_phase(
        actor,
        "syl-no-subject",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1", lesson_id=999)],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-1")],
    )

    assert _versions(org) == []
    assert _states(run) == {"1": LegacyEntityMap.State.QUARANTINED}
    assert _issues(run)[("1", SUBJECT_UNRESOLVED)] == LegacyMigrationIssue.Severity.WARNING
    assert dict(report.state_counts) == {"syllabus_unresolved": 1}


def test_a_quarantined_syllabus_does_not_borrow_an_instructor_complaint(actor):
    """Fənn həll olunmasa da, müəllimin HƏLL OLUNDUĞU faktı itmir."""

    _org, run, _report = _run_phase(
        actor,
        "syl-no-subject-live-teacher",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1", lesson_id=999, teacher_id=TEACHER)],
    )

    codes = {rule_code for legacy_pk, rule_code in _issues(run) if legacy_pk == "1"}
    assert SUBJECT_UNRESOLVED in codes and INSTRUCTOR_UNRESOLVED not in codes


def test_section_rows_without_a_header_are_reported_as_orphans(actor):
    """Canlı: 14 yetim ``uniqid``, 260 sətir — atılır, amma SƏSSİZ İTMİR."""

    org, run, report = _run_phase(
        actor,
        "syl-orphan",
        headers=[harness.syllabus_header_row(1, uniqid="syl-1")],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-orphan")],
    )

    assert _sections(_versions(org)[0])["week"]["rows"] == []
    assert _states(run)["orphan:syl-orphan"] == LegacyEntityMap.State.SKIPPED
    assert _issues(run)[("orphan:syl-orphan", ORPHAN_UNIQID)] == LegacyMigrationIssue.Severity.WARNING
    assert report.state_counts["syllabus_rows_represented"] == 1


def test_an_ambiguous_uniqid_attaches_its_rows_to_nobody(actor):
    """Canlı: ``htcVEP3we58POdhcgo0q`` — ``sillabus.id`` 601 VƏ 2386."""

    org, run, _report = _run_phase(
        actor,
        "syl-ambiguous",
        headers=[
            harness.syllabus_header_row(1, uniqid="syl-dup", lesson_id=LESSON),
            harness.syllabus_header_row(2, uniqid="syl-dup", lesson_id=OTHER_LESSON),
        ],
        weeks=[harness.syllabus_week_row(1, uniqid="syl-dup", movzu="Kimin mövzusu?")],
        lessons=(LESSON, OTHER_LESSON),
    )

    assert all(_sections(version)["week"]["rows"] == [] for version in _versions(org))
    issues = _issues(run)
    assert issues[("1", AMBIGUOUS_UNIQID)] == LegacyMigrationIssue.Severity.WARNING
    assert issues[("2", AMBIGUOUS_UNIQID)] == LegacyMigrationIssue.Severity.WARNING


# ── idempotentlik / determinizm ──────────────────────────────────────────────


def test_a_second_pass_writes_nothing_and_keeps_the_same_digest(actor):
    headers = [harness.syllabus_header_row(1, uniqid="syl-1")]
    weeks = [harness.syllabus_week_row(1, uniqid="syl-1")]
    rows = harness.tables(syllabi=headers, lesson_topics=weeks)
    org = harness.organization(actor, "syl-resume")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_syllabus_subject(org, actor, run.pk, LESSON)
    harness.seed_syllabus_teacher(org, actor, run.pk, TEACHER)

    first = SyllabusMigrationPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    second = SyllabusMigrationPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert first.phase_digest == second.phase_digest
    assert dict(second.state_counts) == {"syllabus_versions_written": 1}
    assert len(_versions(org)) == 1  # ikinci keçid HEÇ NƏ yazmır


def test_two_independent_runs_produce_the_same_phase_digest(actor):
    headers = [harness.syllabus_header_row(1, uniqid="syl-1"), harness.syllabus_header_row(2, uniqid="syl-2")]
    weeks = [harness.syllabus_week_row(1, uniqid="syl-1"), harness.syllabus_week_row(2, uniqid="syl-2", movzu="B")]

    _org_a, _run_a, first = _run_phase(actor, "syl-det-a", headers=headers, weeks=weeks)
    _org_b, _run_b, second = _run_phase(actor, "syl-det-b", headers=headers, weeks=weeks)

    # Digest-də heç bir hədəf UUID-si yoxdur → iki müstəqil run eyni izi verir.
    assert first.phase_digest == second.phase_digest
