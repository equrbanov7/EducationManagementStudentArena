"""Fənn birləşdirməsi — ``registrar.Subject``-ə istinad edən BÜTÜN əlaqələrin inventarı (2026-10-19).

Hər FK/M2M burada AÇIQ strategiya ilə qeydə alınır; ``discovered_relations()`` isə Django-nun
``_meta`` qatından (gizli ``related_name="+"`` əlaqələri də daxil) canlı siyahını çıxarır.
``unhandled_relations()`` boş deyilsə — yeni FK əlavə olunub, amma birləşdirmə onu tanımır:
``apps/registrar/tests/test_subject_merge_inventory.py`` bu halda düşür (unudulmasın).

STRATEGİYALAR
* ``repoint`` — sətrin fənn sütunu hədəfə köçürülür (id-lər audit-ə yazılır, geri qaytarıla bilər);
* ``m2m`` — ``exams.StudentGroup.subjects`` əlaqə sətirləri: hədəf artıq qrupdadırsa təkrar əlaqə
  çıxarılır (audit-də saxlanır, geri qaytarmada bərpa olunur), yoxsa köçürülür;
* ``keep`` — DƏYİŞMƏZ tarixçə (append-only DB triggeri): sətir arxivlənmiş mənbə kartında QALIR
  (kart silinmir, FK etibarlıdır), önizləmədə ayrıca göstərilir.

YUMŞAQ İSTİNADLAR (FK olmayan): ``timetable.TeacherAvailability.subject_priorities`` — açarı
fənn id-si olan JSON (``{subject_id: 1..5}``); açar hədəfə köçürülür, ikisi də varsa böyük
prioritet qalır.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.utils.translation import pgettext_lazy

_CTX = "registrar.subject_merge"

REPOINT = "repoint"
M2M = "m2m"
KEEP = "keep"


@dataclass(frozen=True)
class Relation:
    label: str  # "app_label.ModelName"
    field: str  # Subject-ə baxan sahənin adı
    strategy: str
    title: object  # lazy etiket (UI + audit)

    @property
    def key(self) -> str:
        return f"{self.label}.{self.field}"

    def model(self):
        return django_apps.get_model(self.label)


RELATIONS: tuple[Relation, ...] = (
    Relation("registrar.CourseOffering", "subject", REPOINT, pgettext_lazy(_CTX, "Fənn açılışları (jurnallar)")),
    Relation("registrar.CurriculumSubject", "subject", REPOINT, pgettext_lazy(_CTX, "Tədris planı sətirləri")),
    Relation(
        "registrar.GroupElectiveChoice", "chosen_subject", REPOINT, pgettext_lazy(_CTX, "Qrupun seçmə fənn qərarları")
    ),
    Relation("registrar.RetakeApplication", "subject", REPOINT, pgettext_lazy(_CTX, "Təkrar imtahan müraciətləri")),
    Relation(
        "registrar.ExamChanceGrant", "subject", KEEP, pgettext_lazy(_CTX, "İmtahan şansı qeydləri (dəyişməz tarixçə)")
    ),
    Relation(
        "registrar.ExternalCreditRecognition",
        "subject",
        KEEP,
        pgettext_lazy(_CTX, "Xarici nəticənin tanınması qeydləri (dəyişməz tarixçə)"),
    ),
    Relation("syllabus.Syllabus", "subject", REPOINT, pgettext_lazy(_CTX, "Sillabuslar")),
    Relation("workload.TeachingTaskRow", "subject", REPOINT, pgettext_lazy(_CTX, "Tədris tapşırığı sətirləri")),
    Relation("exams.StudentGroup", "subjects", M2M, pgettext_lazy(_CTX, "İmtahan qrupları (əlaqə)")),
    Relation("exams.Exam", "subject", REPOINT, pgettext_lazy(_CTX, "İmtahanlar")),
    Relation("exams.QuestionBank", "subject_ref", REPOINT, pgettext_lazy(_CTX, "Sual bankları")),
    Relation("exams.QuestionSubmission", "subject_ref", REPOINT, pgettext_lazy(_CTX, "Sual göndərişləri")),
    Relation("surveys.SurveyResponse", "subject", REPOINT, pgettext_lazy(_CTX, "Sorğu cavabları (anonim)")),
    Relation("subject_folder.SubjectFolder", "subject", REPOINT, pgettext_lazy(_CTX, "Fənn qovluqları")),
)

#: FK olmayan, fənn id-sini daşıyan JSON sahələri: (model, sahə) — açar = fənn id-si.
SOFT_JSON_KEYS: tuple[tuple[str, str], ...] = (("timetable.TeacherAvailability", "subject_priorities"),)
SOFT_JSON_TITLE = pgettext_lazy(_CTX, "Cədvəl: müəllimin fənn prioritetləri")


def relation(key: str) -> Relation:
    for item in RELATIONS:
        if item.key == key:
            return item
    raise KeyError(key)


def discovered_relations() -> set[str]:
    """``Subject``-ə baxan bütün FK/M2M-lər (gizli əlaqələr daxil; avtomatik M2M ara cədvəli xaric)."""
    Subject = django_apps.get_model("registrar", "Subject")
    found = set()
    for item in Subject._meta.get_fields(include_hidden=True):
        if not (item.is_relation and item.auto_created and not item.concrete):
            continue
        related = item.related_model
        if related._meta.auto_created:  # M2M-in avtomatik ara cədvəli — M2M sahəsinin özü sayılır
            continue
        found.add(f"{related._meta.label}.{item.field.name}")
    return found


def unhandled_relations() -> set[str]:
    return discovered_relations() - {item.key for item in RELATIONS}


def stale_relations() -> set[str]:
    return {item.key for item in RELATIONS} - discovered_relations()


__all__ = [
    "KEEP",
    "M2M",
    "RELATIONS",
    "REPOINT",
    "SOFT_JSON_KEYS",
    "SOFT_JSON_TITLE",
    "Relation",
    "discovered_relations",
    "relation",
    "stale_relations",
    "unhandled_relations",
]
