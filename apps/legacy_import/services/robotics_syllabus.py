"""233 CM ing: müəllimin öz7715 sillabusu, fresh30M+30S yükü ilə bağlıdır."""

from django.apps import apps

from . import exact_syllabus_recovery as core
from .exact_syllabus_recovery import RestoreError  # noqa: F401
from .mr46_syllabus import ORG, PERIOD

AUTHOR = 8204
OFFERING = "824f715c-3157-4013-9b61-b72ae22465f8"
GROUP = "46dd0490-a127-47ba-b296-15bd03935b32"
ROW = "08434a06-31f0-4007-bc0c-938f5caa4bca"
UNIQID = "UwzKsR5VoEIrdXA9o2PV"
SPEC = core.RecoverySpec(
    organization=ORG,
    period=PERIOD,
    offering=OFFERING,
    author=AUTHOR,
    uniqid=UNIQID,
    resource="legacy_import.workload_robotics_syllabus",
    journal=14155,
    source_author=760,
    journal_lesson=2043,
    source_syllabus=7715,
    source_lesson=2040,
    hours=60,
    topics=15,
    selfwork=4,
    format="workload-robotics-syllabus/1",
    subject_code="QKU-2040",
    allowed_owners=(AUTHOR,),
    batch_prefix="wksyl-",
    label="Workload robotics syllabus",
    authority="User requests each teacher's own syllabus recovery. Own legacy7715 is explicitly linked to own2026/27 journal14155; exact author760->8204 and subject2040->QKU2040. Fresh30Oct load08434a06 is233CMing,30lecture+30seminar; same15source topics total60hours.",
    note="233 CM ing — müəllimin öz köhnə14155 jurnalına bağlı7715 sillabusu bərpa edilib;15mövzu,30mühazirə və30seminar saatı,4sərbəst iş mənbədən saxlanılıb.",
    group_id=GROUP,
    contact_hours=(30, 30, 0, 0),
    optional_empty_sections=("sillabus_imtahan_suallari",),
)


def load(path, expected):
    loaded = core.load(path, expected, SPEC)
    if loaded[0]["source"].get("language") != "en":
        raise RestoreError("source_language_scope")
    return loaded


def apply(org, actor, loaded):
    offering = core.scope(org, actor, SPEC)
    row = (
        apps.get_model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(pk=ROW, organization=org, task__academic_year="2026/2027")
        .first()
    )
    if (
        row is None
        or str(row.subject_id) != str(offering.subject_id)
        or str(row.period_id) != PERIOD
        or row.season != "fall"
        or row.union_count != 1
        or row.subgroup_count != 1
        or (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total) != (30, 30, 30, 30)
        or row.lab_plan
        or row.lab_total
        or row.total_hours != 60
        or any(
            getattr(row, field)
            for field in (
                "consult_hours",
                "exam_hours",
                "thesis_hours",
                "postgrad_hours",
                "practice_research_hours",
                "practice_production_hours",
            )
        )
        or offering.lesson_hours != 60
        or {str(pk) for pk in row.groups.values_list("pk", flat=True)} != {GROUP}
        or sorted(row.assignments.values_list("teacher_id", "activity", "hours"))
        != [(AUTHOR, "lecture", 30), (AUTHOR, "seminar", 30)]
    ):
        raise RestoreError("live_workload_scope")
    return core.apply(org, actor, loaded, SPEC)


def undo(org, actor, batch):
    return core.undo(org, actor, batch, SPEC)
