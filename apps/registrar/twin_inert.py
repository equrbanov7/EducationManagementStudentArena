"""«Boş əkiz» açılışın və qiymətsiz qeydiyyatın tanınması (sahib 2026-11-04, K1/K2/K3).

Dublikat fənn kartları (məs. QKU-2577 / QKU-2693) eyni qrup + dövr üçün İKİ jurnal yaradıb: birində dərs və
xanalar var, digəri isə yalnız tələbə siyahısı + cədvəl slotlarıdır. Bu modul «əkiz boşdurmu?» sualına
YEGANƏ cavabdır — ``merge_twin_offerings`` (boş əkizi datalı jurnala birləşdirmə) və ``merge_subjects``
(ləğv olunmuş boş əkizi snapshot-la silmə, qiymətsiz təkrar qeydiyyatı bağlama) eyni qaydanı işlədir.

QAYDA (generik — yeni FK əlavə olunanda avtomatik «data» sayılır, unudulmur):

* **qeydiyyatın datası** — ``Enrollment``-ə istinad edən İSTƏNİLƏN sətir (xana, bal, yekun qiymət, düzəliş,
  təkrar imtahan, legacy faktı, əvəzləmə zənciri …), ``legacy_qb_fail`` işarəsi və ya ``completed`` statusu.
  YEGANƏ istisna — ``JournalShare.enrollments`` (bölünmüş jurnalın tələbə siyahısı, qiymət deyil);
* **«yalnız davamiyyət»** — datası YALNIZ balsız ``LessonMark`` (iştirak/qayıb) olan qeydiyyat. Bu da DATADIR
  (bağlı tarixi jurnalda rəsmi davamiyyətdir); yalnız açıq bayraqla (``--drop-attendance-only``) bağlanır;
* **boş açılış** — 0 dərs; bütün qeydiyyatlar datasız; açılışa istinad edən sətirlər YALNIZ
  :data:`OFFERING_CHILDREN`-dəndir (siyahı, slot, qiymətləndirmə sxemi/komponenti, sərbəst iş mövzusu,
  jurnal payı, imtahan bağlantısı) və həmin uşaq sətirlərə də heç nə istinad etmir. Sillabus, dərs yükünün
  intensiv bağı, imtahan vərəqi, təhvil, qovluq, səviyyə kohortu, cədvəl qaralaması … → boş DEYİL.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps

#: Boş açılışda ola bilən (birləşmədə köçürülən / snapshot-la silinən) uşaq sətirlər.
OFFERING_CHILDREN = (
    "registrar.Enrollment.offering",
    "registrar.ScheduleSlot.offering",
    "registrar.AssessmentScheme.offering",
    "registrar.AssessmentComponent.offering",
    "registrar.SelfWorkTopic.offering",
    "registrar.JournalShare.offering",
    "exams.Exam.journal_offerings",
)
#: Uşaq sətirlərin ÖZLƏRİNƏ istinad yoxlanılan modellər (Enrollment ayrıca — :func:`enrollment_data`).
_CONFIG_MODELS = ("AssessmentScheme", "AssessmentComponent", "SelfWorkTopic", "ScheduleSlot", "JournalShare")
SHARE_LINK = "registrar.JournalShare.enrollments"
MARK_LINK = "registrar.LessonMark.enrollment"


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def rel_key(rel) -> str:
    return f"{rel.related_model._meta.label}.{rel.field.name}"


def _referencing(rel, ids):
    """``rel`` üzrə ``ids``-ə istinad edən sətirlərin hədəf id-ləri."""

    model = rel.related_model
    column = rel.field.name if rel.many_to_many else rel.field.attname
    return model._base_manager.filter(**{f"{rel.field.name}__in": ids}).values_list(column, flat=True)


def enrollment_data(enrollment_ids) -> dict:
    """``{qeydiyyat id (str) → data növlərinin çoxluğu}`` — boş çoxluq (açar yoxdur) = datasız."""

    ids = [pk for pk in enrollment_ids if pk]
    found = defaultdict(set)
    if not ids:
        return found
    Enrollment = _model("Enrollment")
    for rel in Enrollment._meta.related_objects:
        key = rel_key(rel)
        if key == SHARE_LINK:
            continue
        for value in _referencing(rel, ids):
            found[str(value)].add(key)
    flags = Enrollment._base_manager.filter(pk__in=ids).values_list("pk", "legacy_qb_fail", "status")
    for pk, qb_fail, status in flags:
        if qb_fail:
            found[str(pk)].add("registrar.Enrollment.legacy_qb_fail")
        if status == Enrollment.Status.COMPLETED:
            found[str(pk)].add("registrar.Enrollment.status_completed")
    return found


def attendance_only(enrollment_ids, data=None) -> set:
    """Datası YALNIZ balsız xanalar (iştirak/qayıb) olan qeydiyyatlar."""

    ids = [str(pk) for pk in enrollment_ids if pk]
    data = enrollment_data(ids) if data is None else data
    candidates = [pk for pk in ids if data.get(pk) == {MARK_LINK}]
    if not candidates:
        return set()
    scored = set(
        str(pk)
        for pk in _model("LessonMark")
        ._base_manager.filter(enrollment_id__in=candidates, score__isnull=False)
        .values_list("enrollment_id", flat=True)
    )
    return {pk for pk in candidates if pk not in scored}


def _child_references(offering) -> list:
    blockers = []
    for name in _CONFIG_MODELS:
        model = _model(name)
        ids = list(model._base_manager.filter(offering=offering).values_list("pk", flat=True))
        if not ids:
            continue
        for rel in model._meta.related_objects:
            if _referencing(rel, ids).exists():
                blockers.append(rel_key(rel))
    return blockers


def offering_blockers(offering) -> list:
    """Açılışı «boş əkiz» olmaqdan saxlayan səbəblər (boş siyahı → boşdur). Aktivliyə BAXMIR."""

    CourseOffering = _model("CourseOffering")
    blockers = []
    for rel in CourseOffering._meta.related_objects:
        key = rel_key(rel)
        if key in OFFERING_CHILDREN:
            continue
        if _referencing(rel, [offering.pk]).exists():
            blockers.append(key)
    enrollment_ids = list(_model("Enrollment")._base_manager.filter(offering=offering).values_list("pk", flat=True))
    if enrollment_data(enrollment_ids):
        blockers.append("enrollment_data")
    blockers.extend(_child_references(offering))
    return sorted(set(blockers))


def is_empty_twin(offering) -> bool:
    return not offering_blockers(offering)


__all__ = [
    "MARK_LINK",
    "OFFERING_CHILDREN",
    "SHARE_LINK",
    "attendance_only",
    "enrollment_data",
    "is_empty_twin",
    "offering_blockers",
    "rel_key",
]
