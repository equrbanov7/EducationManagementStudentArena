"""Fənn birləşdirməsi — «YALNIZ CARİ VƏ GƏLƏCƏK» rejimi (sahib 2026-11-11).

Sahib: «Köhnə illərin jurnalını ciddiyə alma, boşver — əsas indi və bundan sonra olandır.» Kataloq birləşməsinin 12 qrupu
keçmiş semestrin toqquşması ilə bloklanırdı («2022/2023 Payız · 232 M rus: hər iki fənn üzrə açılış var») — nəticədə
imtahan bir kartda, qrupun cari jurnalı əkiz kartda qalırdı və nəticə jurnala düşmürdü.

Bu rejimdə (``current_only=True``) mənbə kartın KEÇMİŞ dövrə aid sətirləri ARXİVLƏNƏN MƏNBƏ KARTDA olduğu kimi QALIR
(toxunulmur), qalan hər şey (cari + gələcək açılışlar, tədris planı sətirləri, cari tapşırıq sətirləri, sillabuslar …)
adi birləşmə kimi saxlanılan karta köçür. Keçmiş dövrdəki toqquşmalar ona görə də BLOKLAMIR — həmin sətirlər yerindən
tərpənmir; cari / gələcək dövrdəki toqquşma isə əvvəlki kimi (jurnal birləşməsi və ya blok) qalır.

KEÇMİŞ dövr: ``is_current=False`` VƏ ``end_date < bu gün``. Dövrsüz sətir cari sayılır (köçür).

Sətrin dövrü (:data:`PERIOD_PATHS`): açılış, tapşırıq sətri, fənn qovluğu — öz ``period``-u; sillabus — öz ``period``-u
və ya açılışının dövrü; təkrar imtahan müraciəti — öz dövrü və ya qeydiyyatının açılışının dövrü (hansı biri keçmişdirsə
qalır). İmtahanın dövr sahəsi yoxdur: ``start_datetime`` cari dövrün başlanğıcından əvvəldirsə keçmişdir.

Sillabusun ``reused_from`` zənciri (``syllabus_reuse_same_org_subject`` — kompozit FK, eyni fənn): köçən sillabus keçmiş
sillabusdan təkrar istifadə edirsə (və ya əksinə) bütün zəncir BİRLİKDƏ köçür — yoxsa DB qaydası pozulardı.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils import timezone

from .subject_merge_inventory import RELATIONS, REPOINT

OFFERING_KEY = "registrar.CourseOffering.subject"
SYLLABUS_KEY = "syllabus.Syllabus.subject"
TASK_ROW_KEY = "workload.TeachingTaskRow.subject"
FOLDER_KEY = "subject_folder.SubjectFolder.subject"
RETAKE_KEY = "registrar.RetakeApplication.subject"
EXAM_KEY = "exams.Exam.subject"

#: Relyasiya → dövrə gedən yol(lar). Yollardan BİRİ keçmiş dövrə baxırsa sətir mənbə kartda qalır.
PERIOD_PATHS: dict[str, tuple[str, ...]] = {
    OFFERING_KEY: ("period",),
    SYLLABUS_KEY: ("period", "offering__period"),
    TASK_ROW_KEY: ("period",),
    FOLDER_KEY: ("period",),
    RETAKE_KEY: ("period", "enrollment__offering__period"),
}


def current_period(organization):
    from .exam_bridge import _current_period

    return _current_period(organization)


def past_period_ids(organization) -> set:
    """Keçmiş dövrlərin id-ləri (bax modulun sənədi)."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    rows = AcademicPeriod.objects.filter(organization=organization, is_current=False, end_date__lt=timezone.localdate())
    return set(rows.values_list("pk", flat=True))


def _relation(key):
    return next(item for item in RELATIONS if item.key == key)


def _past_rows(organization, key, source_ids, past_ids, period) -> set:
    rel = _relation(key)
    model = rel.model()
    attname = model._meta.get_field(rel.field).attname
    rows = model._base_manager.filter(**{f"{attname}__in": source_ids})
    if key == EXAM_KEY:
        if period is None:
            return set()
        rows = rows.filter(start_datetime__date__lt=period.start_date)
    else:
        if not past_ids:
            return set()
        query = Q()
        for path in PERIOD_PATHS[key]:
            query |= Q(**{f"{path}_id__in": past_ids})
        rows = rows.filter(query)
    return {str(pk) for pk in rows.values_list("pk", flat=True)}


def _reuse_closure(source_ids, staying: set) -> set:
    """Köçən sillabusla ``reused_from`` zəncirində olan keçmiş sillabuslar da köçür → qalanların yeni dəsti."""
    if not staying:
        return staying
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    links = list(
        Syllabus._base_manager.filter(subject_id__in=source_ids, reused_from__isnull=False).values_list(
            "pk", "reused_from_id"
        )
    )
    neighbours: dict[str, set] = {}
    for pk, parent in links:
        neighbours.setdefault(str(pk), set()).add(str(parent))
        neighbours.setdefault(str(parent), set()).add(str(pk))
    staying = set(staying)
    changed = True
    while changed:
        changed = False
        for pk in sorted(staying):
            if any(other not in staying for other in neighbours.get(pk, ())):
                staying.discard(pk)
                changed = True
    return staying


def staying_rows(organization, sources) -> dict:
    """``{relyasiya açarı: [id, …]}`` — mənbə kartlarda (keçmiş dövr) QALAN sətirlər (sabit sıra)."""
    source_ids = [source.pk for source in sources]
    past_ids = past_period_ids(organization)
    period = current_period(organization)
    keys = [key for key in (*PERIOD_PATHS, EXAM_KEY) if _relation(key).strategy == REPOINT]
    out = {key: _past_rows(organization, key, source_ids, past_ids, period) for key in keys}
    out[SYLLABUS_KEY] = _reuse_closure(source_ids, out.get(SYLLABUS_KEY, set()))
    return {key: sorted(ids) for key, ids in out.items() if ids}


__all__ = [
    "EXAM_KEY",
    "FOLDER_KEY",
    "OFFERING_KEY",
    "PERIOD_PATHS",
    "RETAKE_KEY",
    "SYLLABUS_KEY",
    "TASK_ROW_KEY",
    "current_period",
    "past_period_ids",
    "staying_rows",
]
