"""Klondakı fazalardan sonra plana YALNIZ bərpa sətirlərinin çıxarılması (2026-09-25).

Qayda (fail-closed, sahə-sahə deyil, SƏTİR-sətir):

* **bərpa yazılışı** (``restored``) və onun uşaqları — xana, komponent balı,
  yekun, təkrar imtahan, sərbəst iş işarəsi, J12 sübut faktı — plana düşür;
* **yeni açılış** (fake jurnalı üçün J1-in qurduğu) və onun sxemi, komponentləri,
  sərbəst iş mövzuları, dərsləri plana düşür;
* bərpa sətrinin ASILI olduğu yeni sətir (məs. mövcud açılışda J12-nin bərpa
  dərsi, yeni komponent, yeni sərbəst iş mövzusu) plana düşür;
* klonda qalan hər YENİ sətir («yad delta») və MÖVCUD sətrin hər YENİLƏNMƏSİ
  plana DÜŞMÜR, cədvəl-cədvəl sayılır (hesabatda görünür) — plan heç vaxt
  mövcud tələbələrin datasını dəyişmir.
"""

from __future__ import annotations

import datetime
import uuid
from collections import Counter
from decimal import Decimal

from django.apps import apps as django_apps

#: Tətbiq sırası — FK asılılığı (valideyn uşaqdan əvvəl).
MODEL_ORDER = (
    ("registrar", "CourseOffering"),
    ("registrar", "AssessmentScheme"),
    ("registrar", "AssessmentComponent"),
    ("registrar", "SelfWorkTopic"),
    ("registrar", "Enrollment"),
    ("registrar", "Lesson"),
    ("registrar", "LessonMark"),
    ("registrar", "ComponentScore"),
    ("registrar", "FinalGrade"),
    ("registrar", "ResitRecord"),
    ("registrar", "SelfWorkMark"),
    ("registrar", "LegacyGradeFact"),
)
_SKIP_FIELDS = frozenset({"id", "created_at", "updated_at", "organization"})


def label(app_label: str, model_name: str) -> str:
    return f"{app_label}.{model_name}".lower()


def json_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def record_of(instance) -> dict:
    """Modelin konkret sahələri (FK üçün ``attname``) — pk ayrıca, org/vaxt damğası YOX.

    Sahələr ``fields`` altında saxlanılır: ``Enrollment``/``Lesson``/``AssessmentComponent``
    modellərinin ÖZ ``kind`` sahəsi var, plan faylının ``kind`` açarı (model adı) ilə
    toqquşmamalıdır.
    """

    meta = instance._meta
    fields = {
        field.attname: json_value(getattr(instance, field.attname))
        for field in meta.concrete_fields
        if field.name not in _SKIP_FIELDS
    }
    return {"kind": label(meta.app_label, meta.object_name), "pk": str(instance.pk), "fields": fields}


def _new(model, organization, since):
    return model.objects.filter(organization=organization, created_at__gte=since)


def extract(organization, *, since, restored: dict, new_offerings: set):
    """``(records, report)`` — records MODEL_ORDER sırasında, report say cədvəlidir."""

    models = {name: django_apps.get_model(app, name) for app, name in MODEL_ORDER}
    enrollments = set(restored.values())
    keys = set(restored)
    offerings = {str(pk) for pk in new_offerings}
    picked: dict[str, list] = {name: [] for _app, name in MODEL_ORDER}

    picked["CourseOffering"] = list(_new(models["CourseOffering"], organization, since).filter(pk__in=offerings))
    picked["AssessmentScheme"] = list(
        _new(models["AssessmentScheme"], organization, since).filter(offering_id__in=offerings)
    )
    picked["Enrollment"] = list(_new(models["Enrollment"], organization, since).filter(pk__in=enrollments))
    if len(picked["Enrollment"]) != len(enrollments):
        raise RuntimeError("legacy_repair_extract_restored_enrollment_missing")
    for name in ("LessonMark", "ComponentScore", "FinalGrade", "ResitRecord", "SelfWorkMark"):
        picked[name] = list(_new(models[name], organization, since).filter(enrollment_id__in=enrollments))
    facts = _new(models["LegacyGradeFact"], organization, since)
    picked["LegacyGradeFact"] = [
        fact
        for fact in facts
        if (fact.enrollment_id is not None and str(fact.enrollment_id) in enrollments)
        or (fact.enrollment_id is None and fact.source_enrollment_ref in keys)
    ]
    lesson_ids = {str(mark.lesson_id) for mark in picked["LessonMark"]}
    picked["Lesson"] = [
        lesson
        for lesson in _new(models["Lesson"], organization, since)
        if str(lesson.offering_id) in offerings or str(lesson.pk) in lesson_ids
    ]
    topic_ids = {str(mark.topic_id) for mark in picked["SelfWorkMark"]}
    picked["SelfWorkTopic"] = [
        topic
        for topic in _new(models["SelfWorkTopic"], organization, since)
        if str(topic.offering_id) in offerings or str(topic.pk) in topic_ids
    ]
    component_ids = {str(score.component_id) for score in picked["ComponentScore"]}
    picked["AssessmentComponent"] = [
        component
        for component in _new(models["AssessmentComponent"], organization, since)
        if str(component.offering_id) in offerings or str(component.pk) in component_ids
    ]

    report: dict[str, dict] = {}
    for _app, name in MODEL_ORDER:
        model = models[name]
        created = _new(model, organization, since).count()
        updated = model.objects.filter(organization=organization, created_at__lt=since, updated_at__gte=since).count()
        report[name] = {
            "plan": len(picked[name]),
            "foreign_new": created - len(picked[name]),
            "updated_existing": updated,
        }

    inverse = {str(pk): key for key, pk in restored.items()}
    records = [record_of(row) for _app, name in MODEL_ORDER for row in sorted(picked[name], key=lambda r: str(r.pk))]
    for record in records:
        if record["kind"] == "registrar.enrollment":
            # Modelə yazılmır — audit/hesabat üçün legacy açarıdır.
            record["restore_key"] = inverse[record["pk"]]
    return records, report


def restored_from_run(organization, run):
    """Bitmiş plan run-undan ``(since, restored, new_offerings)`` — yenidən çıxarış üçün.

    Bərpa yazılışları run-un ÖZ yaratdığı ``journal_enrollment`` xəritələridir
    (hədəfi ``run.started_at``-dan sonra yaranıb); köçürülmüş mövcud yazılışlar
    köhnədir və buraya düşmür.
    """

    from apps.legacy_import.models import LegacyEntityMap

    since = run.started_at
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    fresh = {
        str(pk)
        for pk in enrollment_model.objects.filter(organization=organization, created_at__gte=since).values_list(
            "pk", flat=True
        )
    }
    restored = {
        legacy_pk: target_pk
        for legacy_pk, target_pk in LegacyEntityMap.objects.filter(
            organization=organization, created_run=run, entity_type="journal_enrollment"
        ).values_list("legacy_pk", "target_pk")
        if target_pk in fresh
    }
    offering_model = django_apps.get_model("registrar", "CourseOffering")
    new_offerings = {
        str(pk)
        for pk in offering_model.objects.filter(organization=organization, created_at__gte=since).values_list(
            "pk", flat=True
        )
    }
    return since, restored, new_offerings


def summarise(records) -> Counter:
    return Counter(record["kind"] for record in records)


__all__ = ["MODEL_ORDER", "extract", "json_value", "label", "record_of", "restored_from_run", "summarise"]
