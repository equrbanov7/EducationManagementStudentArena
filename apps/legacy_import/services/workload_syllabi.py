"""Rəsmi yük inventarında canlı yoxlanmış, hələ sillabussuz Bilal jurnalı.

Arzunun iki və Əşrəfin bir jurnalı 28Oct təsdiqli sillabusla artıq doludur;
onlar bu yazı müqaviləsinə daxil edilmir. Digər müəllif/fənn qəbul edilmir.
"""

from . import exact_syllabus_recovery as core
from .exact_syllabus_recovery import RestoreError  # noqa: F401
from .mr46_syllabus import ORG, PERIOD

OFFERING = "6467692a-edd0-4651-9b6e-246c19bbbc40"
AUTHOR = 8143
UNIQID = "WaccQbauu5QCDnYunfZL"
SPEC = core.RecoverySpec(
    organization=ORG,
    period=PERIOD,
    offering=OFFERING,
    author=AUTHOR,
    uniqid="WaccQbauu5QCDnYunfZL",
    resource="legacy_import.workload_syllabi",
    journal=14080,
    source_author=679,
    journal_lesson=771,
    source_syllabus=8430,
    source_lesson=628,
    hours=30,
    topics=8,
    selfwork=1,
    format="workload-syllabi/1",
    subject_code="QKU-771",
    allowed_owners=(AUTHOR,),
    batch_prefix="wksyl-",
    label="Workload syllabus",
    authority="User requests recovery of each teacher's own legacy syllabus. Official Fəlsəfə workbook row5: same author/group,15lecture+15seminar. All8source topics concern history philosophy; source8430 is explicitly linked to own journal14080. Live29Oct journal still missing syllabus.",
    note="Rəsmi dərs yükü yoxlaması: köhnə 14080 jurnalının öz müəllifinə aid 8430 sillabusu bərpa olunub. «Tarixin fəlsəfəsi» və «Tarix fəlsəfəsi» başlıq fərqi bütün 8 mövzu və rəsmi 15+15 saatla yoxlanılıb. Müəllimə və başqa jurnala aid məzmun köçürülməyib.",
    group_id="964edf4c-26ed-4bb3-b5e6-9afe70bf9712",
    contact_hours=(15, 15, 0, 0),
    selfwork_topics=0,
)


def load(path, expected):
    return core.load(path, expected, SPEC)


def apply(org, actor, loaded):
    return core.apply(org, actor, loaded, SPEC)


def undo(org, actor, batch):
    return core.undo(org, actor, batch, SPEC)
