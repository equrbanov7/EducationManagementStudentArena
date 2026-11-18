"""Boş həftəlik planlı BAZA sillabusu müəllimin öz təsdiqlənmiş planı ilə doldurulur (sahib 2026-11-18).

Şikayət (Əşrəf Həsənov, «İdarəetmə uçotu», 2533ML/2533MU): jurnalda «Sillabusa bax» paneli təsviri göstərir,
sol tərəfdə mövzular var, amma «Sillabusu redaktə et» açanda həftəlik mövzular boşdur, saat 0-dır və 16 boş sətir
görünür.  Səbəb: bu jurnalların öz dosyesi yoxdur; həll (``syllabus_for_offering``) müəllimin semestrsiz BAZA
dosyesinə düşür — köçürmədə onun həftəlik planı boş (mövzusuz, saatsız) gəlib.  Jurnalın mövzu siyahısı isə ehtiyat
mənbədən (``journal_topic_fallback`` — müəllimin eyni fənn üzrə başqa TƏSDİQLƏNMİŞ sillabusu) gəlir.

Düzəliş (yalnız belə dosyelər):

* hədəf — semestrsiz, açılışsız, bağlı olmayan (``reused_from`` boş) aktiv dosye; cari semestrin aktiv jurnalı
  ona məhz müəllif pilləsi ilə düşür (jurnalın müəllimi = dosyenin müəllifi); qüvvədə olan versiyası
  TƏSDİQLƏNİB, açıq qaralaması yoxdur və həftəlik planında heç bir mövzu yoxdur;
* saat — ona düşən bütün jurnalların plan saatı EYNİDİR (fərqlidirsə toxunulmur — bir plan hamısına uyğun gəlmir);
* mənbə — jurnalın mövzu siyahısının ehtiyat mənbəyi ilə EYNİ sıra: eyni fənn, eyni müəllif (və ya onun jurnalının
  dosyesi), əvvəl eyni semestr, sonra ən yeni; qüvvədə olan TƏSDİQLƏNMİŞ versiyasında mövzu olan; tədris dili
  (qrupun sektoru) hədəf jurnallarla eyni;
* yazı — mənbənin sətirləri hədəfin saatına uyğunlaşdırılır (``fit_rows_to_hours``), sətir sayı plana görə
  (``ceil(saat/2)``) kəsilir — artıq boş sətir qalmır; versiyanın ``plan_hours`` sahəsi jurnalın saatı olur.
  Digər bölmələrə (təsvir, nəticələr, ədəbiyyat) toxunulmur.  Status / təsdiq dəyişmir.

Hər yazının auditində ``batch`` + köhnə həftə məlumatı + köhnə plan saatı var; ``undo`` onları qaytarır.
"""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.base_syllabus_weeks_20261118"
REASON = "Sahib 2026-11-18: boş həftəlik planlı baza sillabus müəllimin öz təsdiqlənmiş planı ilə dolduruldu"
UNDO_REASON = "Sahib 2026-11-18: baza sillabus həftəlik planının doldurulması geri qaytarıldı"
WEEK = "week"
_KINDS = ("lecture", "seminar", "lab")


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"basewk-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _clean_hours(value) -> dict:
    out = {}
    for kind in _KINDS:
        try:
            number = int((value or {}).get(kind) or 0)
        except (AttributeError, TypeError, ValueError):
            number = 0
        if number > 0:
            out[kind] = number
    return out


def _week_rows(version) -> list:
    from apps.syllabus import public as syl

    if version is None:
        return []
    row = next((row for row in version.sections.all() if row.section_id == WEEK), None)
    return syl.week_plan_rows(row.data if row is not None else {})


def _has_topics(rows) -> bool:
    return any(str(row.get("topic") or "").strip() for row in rows)


def _resolved(offering):
    from apps.syllabus import public as syl

    return syl.syllabus_for_offering(
        organization=offering.organization,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


def _targets(organization, counts) -> dict:
    """``{baza dosye pk: [jurnal, …]}`` — cari semestrin jurnalları müəllif pilləsi ilə düşdüyü baza dosyeləri."""
    CourseOffering = _model("registrar", "CourseOffering")
    offerings = CourseOffering.objects.filter(
        organization=organization, is_active=True, instructor__isnull=False, period__is_current=True
    ).select_related("organization", "group", "subject", "period")
    found = defaultdict(list)
    for offering in offerings:
        syllabus = _resolved(offering)
        if syllabus is None:
            continue
        if syllabus.offering_id or syllabus.period_id or syllabus.reused_from_id:
            continue
        if syllabus.author_id != offering.instructor_id:
            continue
        found[syllabus.pk].append(offering)
    counts["base_targets_seen"] = len(found)
    return found


def _source(syllabus, offerings, language):
    """Müəllimin eyni fənn üzrə mövzulu TƏSDİQLƏNMİŞ sillabusu (ehtiyat mənbənin sırası ilə) və ya ``None``."""
    from django.db.models import Case, IntegerField, Q, Value, When

    from .syllabus_carry import group_language

    Syllabus = _model("syllabus", "Syllabus")
    teacher = syllabus.author_id
    period_id = offerings[0].period_id
    candidates = (
        Syllabus.objects.filter(
            organization_id=syllabus.organization_id,
            subject_id=syllabus.subject_id,
            is_active=True,
            approved_version__isnull=False,
            approved_version__status="approved",
        )
        .exclude(pk=syllabus.pk)
        .filter(Q(author_id=teacher) | Q(offering__instructor_id=teacher))
        .select_related("approved_version", "offering__group")
        .annotate(_rank=Case(When(period_id=period_id, then=Value(0)), default=Value(1), output_field=IntegerField()))
        .order_by("_rank", "-updated_at", "pk")
    )
    for candidate in candidates:
        if candidate.offering_id and candidate.offering.group_id:
            if group_language(candidate.offering.group) != language:
                continue
        rows = _week_rows(candidate.approved_version)
        if _has_topics(rows):
            return candidate, rows
    return None, []


def run(*, organization, actor, counts: Counter, batch: str) -> str:
    from apps.syllabus import public as syl

    from .plan_hours import plan_hours_for_offering
    from .syllabus_carry import group_language

    batch = batch or new_batch()
    Syllabus = _model("syllabus", "Syllabus")
    SyllabusSection = _model("syllabus", "SyllabusSection")
    SyllabusVersion = _model("syllabus", "SyllabusVersion")
    for syllabus_pk, offerings in _targets(organization, counts).items():
        with transaction.atomic():
            syllabus = Syllabus.objects.select_for_update(of=("self",)).filter(pk=syllabus_pk).first()
            version = syllabus.approved_version if syllabus is not None and syllabus.approved_version_id else None
            if version is None or version.status != "approved":
                counts["skip_not_approved"] += 1
                continue
            if syl.services.open_version_for(syllabus) is not None:
                counts["skip_open_draft"] += 1
                continue
            row = SyllabusSection.objects.select_for_update().filter(version=version, section_id=WEEK).first()
            old_rows = syl.week_plan_rows(row.data if row is not None else {})
            if _has_topics(old_rows):
                counts["skip_has_topics"] += 1
                continue
            hours_set = {tuple(sorted(_clean_hours(plan_hours_for_offering(o)).items())) for o in offerings}
            if len(hours_set) != 1:
                counts["skip_hours_mixed"] += 1
                continue
            hours = dict(next(iter(hours_set)))
            if not hours:
                counts["skip_no_hours"] += 1
                continue
            languages = {group_language(o.group) for o in offerings}
            if len(languages) != 1:
                counts["skip_language_mixed"] += 1
                continue
            source, source_rows = _source(syllabus, offerings, next(iter(languages)))
            if source is None:
                counts["skip_no_source"] += 1
                continue
            fitted, _changed = syl.fit_rows_to_hours(source_rows, hours)
            fitted = fitted[: syl.expected_week_rows(hours)]
            old_data = dict(row.data or {}) if row is not None else {}
            new_data = {**old_data, "rows": fitted}
            if row is None:
                row = SyllabusSection.objects.create(
                    organization_id=version.organization_id, version=version, section_id=WEEK, data=new_data
                )
            else:
                row.data = new_data
                row.revision += 1
                row.save(update_fields=["data", "revision", "updated_at"])
            old_hours = dict(version.plan_hours or {})
            SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours=hours)
            version.plan_hours = hours
            syl.services.recompute_completion(version)
            counts["filled"] += 1
            counts["journals_covered"] += len(offerings)
            counts["rows_written"] += len(fitted)
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(version.pk),
                resource_repr="Baza sillabusun həftəlik planı müəllimin təsdiqlənmiş planından",
                old_values={"week": old_data, "plan_hours": old_hours},
                new_values={
                    "batch": batch,
                    "syllabus": str(syllabus.pk),
                    "source_syllabus": str(source.pk),
                    "offerings": [str(o.pk) for o in offerings],
                    "plan_hours": hours,
                    "rows": len(fitted),
                },
            )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from apps.syllabus import public as syl

    AuditLog = _model("audit", "AuditLog")
    SyllabusSection = _model("syllabus", "SyllabusSection")
    SyllabusVersion = _model("syllabus", "SyllabusVersion")
    for entry in AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch):
        with transaction.atomic():
            version = SyllabusVersion.objects.select_for_update(of=("self",)).filter(pk=entry.resource_id).first()
            if version is None:
                counts["undo_missing"] += 1
                continue
            old = entry.old_values or {}
            SyllabusSection.objects.filter(version=version, section_id=WEEK).update(data=old.get("week") or {})
            SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours=old.get("plan_hours") or {})
            version.refresh_from_db()
            syl.services.recompute_completion(version)
            counts["undone"] += 1
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=entry.resource_id,
                resource_repr="Baza sillabus həftəlik planının geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["RESOURCE", "new_batch", "run", "undo"]
