"""``legacy_repair_journal_enrollments`` tətbiqinin model spesifikasiyaları.

Hər plan sətri ``kind`` (``app.model``) + klondakı ``pk`` + ``fields`` (model sahələri) daşıyır.  Tətbiq
onu canlı bazaya bu qaydalarla köçürür:

* **açar** — təbii açar (DB unikal məhdudiyyəti və ya J3/J1 açarı); plan pk-sı
  canlıda varsa ``already_present`` (əvvəlki tətbiq), açar varsa:
  * ``reuse=True`` (açılış, sxem, komponent, mövzu, dərs) — canlı sətir İŞLƏDİLİR
    (J1/J3 ``get_or_create`` semantikası, C6 birləşməsi);
  * yazılış — BAŞQASININ yazılışı: sətir və bütün uşaqları ATLANIR (birləşdirilmir);
  * yarpaq sətir (xana, bal, yekun …) — dəyər eynidirsə ``already_present``,
    fərqlidirsə ``live_conflict``: ÜSTÜNDƏN YAZILMIR;
* **FK** — plan pk-sı canlı pk-ya çevrilir; valideyn atlanıbsa uşaq da atlanır;
* **istifadəçi FK-ları** — ``instructor_id`` yalnız ``grade.input``-lu aktiv
  üzvdürsə qalır, ``added_by_id`` tətbiq aktorudur, qalanı (``entered_by`` və s.)
  boşdur: import heç kimin adından yazmır.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.apps import apps as django_apps

from .repair_plan_file import RepairPlanError

CO = "registrar.courseoffering"
ENR = "registrar.enrollment"
LESSON = "registrar.lesson"


@dataclass(frozen=True)
class Spec:
    app_label: str
    model_name: str
    key: tuple
    fks: dict = field(default_factory=dict)
    reuse: bool = False
    leaf: bool = False
    compare: tuple = ()

    @property
    def model(self):
        return django_apps.get_model(self.app_label, self.model_name)


SPECS = {
    CO: Spec("registrar", "CourseOffering", ("subject_id", "period_id", "group_id"), reuse=True),
    "registrar.assessmentscheme": Spec("registrar", "AssessmentScheme", ("offering_id",), {"offering_id": CO}, True),
    "registrar.assessmentcomponent": Spec(
        "registrar", "AssessmentComponent", ("offering_id", "name"), {"offering_id": CO}, True
    ),
    "registrar.selfworktopic": Spec(
        "registrar", "SelfWorkTopic", ("offering_id", "order", "title"), {"offering_id": CO}, True
    ),
    ENR: Spec("registrar", "Enrollment", ("student_id", "offering_id"), {"offering_id": CO}),
    LESSON: Spec("registrar", "Lesson", ("offering_id", "date", "start_time"), {"offering_id": CO}, True),
    "registrar.lessonmark": Spec(
        "registrar",
        "LessonMark",
        ("lesson_id", "enrollment_id"),
        {"lesson_id": LESSON, "enrollment_id": ENR},
        leaf=True,
        compare=("status", "score"),
    ),
    "registrar.componentscore": Spec(
        "registrar",
        "ComponentScore",
        ("component_id", "enrollment_id"),
        {"component_id": "registrar.assessmentcomponent", "enrollment_id": ENR},
        leaf=True,
        compare=("score",),
    ),
    "registrar.finalgrade": Spec(
        "registrar", "FinalGrade", ("enrollment_id",), {"enrollment_id": ENR}, leaf=True, compare=("exam_score",)
    ),
    "registrar.resitrecord": Spec(
        "registrar", "ResitRecord", ("enrollment_id",), {"enrollment_id": ENR}, leaf=True, compare=("resit_score",)
    ),
    "registrar.selfworkmark": Spec(
        "registrar",
        "SelfWorkMark",
        ("topic_id", "enrollment_id"),
        {"topic_id": "registrar.selfworktopic", "enrollment_id": ENR},
        leaf=True,
        compare=("done",),
    ),
    "registrar.legacygradefact": Spec(
        "registrar",
        "LegacyGradeFact",
        ("source_system", "source_table", "source_pk"),
        {"enrollment_id": ENR},
        leaf=True,
        compare=("source_row_hash", "raw_score_text", "materialization_digest"),
    ),
}
ORDER = tuple(SPECS)
#: Plan aktorunun izi canlıda TƏTBİQ aktoru ilə əvəz olunur; qalanlar boşdur.
ACTOR_FIELDS = frozenset({"added_by_id"})
NULL_USER_FIELDS = frozenset(
    {
        "entered_by_id",
        "decided_by_id",
        "created_by_id",
        "chair_approved_by_id",
        "dean_approved_by_id",
        "submitted_by_id",
    }
)


def coerce(model, values: dict) -> dict:
    """JSON dəyərlərini model sahə tiplərinə qaytar (tarix/saat/onluq).

    Planda olmayan YENİ sahə model defoltunu alır (plan köhnə kodla qurulubsa);
    modeldə olmayan sahə isə sabit kodla rədd edilir.
    """

    by_attname = {field_obj.attname: field_obj for field_obj in model._meta.concrete_fields}
    unknown = sorted(set(values) - set(by_attname))
    if unknown:
        # Plan başqa model versiyası ilə qurulub (sahə silinib/adı dəyişib) — təxmin ETMİRİK.
        raise RepairPlanError(f"legacy_repair_plan_field_unknown:{model._meta.label_lower}.{unknown[0]}")
    result = {}
    for name, value in values.items():
        field_obj = by_attname[name]
        internal = "ForeignKey" if field_obj.is_relation else field_obj.get_internal_type()
        if value is None:
            result[name] = None
        elif internal == "DateTimeField":
            result[name] = datetime.datetime.fromisoformat(value)
        elif internal == "DateField":
            result[name] = datetime.date.fromisoformat(value)
        elif internal == "TimeField":
            result[name] = datetime.time.fromisoformat(value)
        elif internal == "DecimalField":
            result[name] = Decimal(value)
        else:
            result[name] = value
    return result


def natural_key(spec: Spec, values: dict) -> tuple:
    """Açar — plan (JSON) və canlı (Python) dəyərləri EYNİ mətn formasına salınır."""

    from .repair_enrollments_extract import json_value

    return tuple(None if values.get(name) is None else str(json_value(values.get(name))) for name in spec.key)


def same_values(spec: Spec, live: dict, planned: dict) -> bool:
    for name in spec.compare:
        stored, incoming = live.get(name), planned.get(name)
        if stored is None or incoming is None:
            if stored is not incoming and not (stored is None and incoming is None):
                return False
            continue
        if isinstance(stored, Decimal) or isinstance(incoming, Decimal):
            if Decimal(str(stored)) != Decimal(str(incoming)):
                return False
        elif stored != incoming:
            return False
    return True


__all__ = [
    "ACTOR_FIELDS",
    "CO",
    "ENR",
    "LESSON",
    "NULL_USER_FIELDS",
    "ORDER",
    "SPECS",
    "Spec",
    "coerce",
    "natural_key",
    "same_values",
]
