"""Boş həftəlik planlı sillabuslar — bütün cari jurnallar üzrə audit + təhlükəsiz düzəliş (sahib 2026-11-19).

Şikayət (Əşrəf Həsənov, 2026-11-18 düzəlişindən sonra): «bu versiyanı yoxla ki, başqa kimdəsə varmı belə hal, varsa
düzəlt». Simptom: jurnalın «Sillabusa bax» panelində mövzular var (ehtiyat mənbədən), «Sillabusu redaktə et» isə
mövzusuz, «0 saat» və 16 boş sətirli həftəlik plan açır.  2026-11-18 əmri
(:mod:`apps.registrar.base_syllabus_weeks_2026_11_18`) yalnız BAZA pilləsini düzəltdi; bu modul jurnalın HƏLL
olunduğu istənilən dosyeyə baxır.

Formalar (dosye üzrə sayılır, açarlar ``found_<forma>``):

* ``a_own`` — açılışa bağlı dosye (öz / təhvil / dil kohortu mənbəyi), qüvvədə olan TƏSDİQLƏNMİŞ versiyanın həftəlik
  planında mövzu yoxdur;
* ``b_semester`` — fənn + semestr dosyesi (açılışsız), eyni simptom — o semestrdə həmin fənnin BÜTÜN müəllimlərinə
  ortaqdır: yalnız ona düşən hər jurnal EYNİ müəllimin və EYNİ saatın olanda doldurulur;
* ``base`` — semestrsiz baza dosyesi (2026-11-18 əmrinin hədəfi, sonradan yaranan hallar üçün);
* ``c_no_plan_hours`` — mövzular var, amma ``plan_hours`` boşdur (redaktor «0 saat» + 16 sətir göstərir): yalnız
  plan saatı jurnalın saatı olur, mövzulara toxunulmur; sətirlərin saat cəmi plana zidddirsə — keçilir;
* ``d`` — jurnalın saatı tapılmır (``d_no_hours`` + səbəb açarı): bölünmüş yarım qrupun (``settings.parent_group``)
  saatı ana qrupun yük sətrindən götürülür (``d_hours_from_parent_load``), qalanı yalnız sayılır;
* ``e_shared`` — paylaşılan dosye (``SyllabusShare``): YALNIZ hesabat.

Qaydalar (2026-11-18 əmri ilə eyni): mənbə — jurnalın mövzu siyahısının ARTIQ göstərdiyi ehtiyat mənbə
(``journal_topic_fallback`` sırası: LMS kursu → dosyenin son versiyası → eyni fənnin təsdiqlənmiş sillabusu), eyni
müəllim, eyni tədris dili; sətirlər jurnalın saatına uyğunlaşdırılır (``fit_rows_to_hours``) və plan sətir sayına
(``expected_week_rows``) kəsilir; ``plan_hours`` jurnalın saatı olur; YALNIZ ``week`` bölməsi + ``plan_hours``
dəyişir; mövzulu plan üzərinə yazılmır; açıq qaralamaya toxunulmur; qarışıq saat / müəllim — keçilir və sayılır.
Hər yazının auditində ``batch`` + köhnə həftə + köhnə plan saatı var; ``undo`` onları qaytarır.
"""

from __future__ import annotations

import secrets
from collections import defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .base_syllabus_weeks_2026_11_18 import _clean_hours, _has_topics, _resolved, _week_rows

RESOURCE = "registrar.empty_syllabus_weeks_20261119"
REASON = "Sahib 2026-11-19: boş həftəlik planlı sillabus jurnalın göstərdiyi mənbə və jurnalın saatı ilə dolduruldu"
UNDO_REASON = "Sahib 2026-11-19: boş həftəlik planın doldurulması geri qaytarıldı"
WEEK = "week"
_KINDS = ("lecture", "seminar", "lab")
_TIER_SHAPE = {"own": "a_own", "semester": "b_semester", "base": "base"}
#: Hər açar üzrə çap olunan versiya id-lərinin həddi (log qısa qalsın).
IDS_PER_KEY = 40


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"emptywk-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _tier(syllabus) -> str:
    if syllabus.offering_id:
        return "own"
    return "semester" if syllabus.period_id else "base"


class _Run:
    def __init__(self, *, organization, actor, counts, batch):
        self.organization = organization
        self.actor = actor
        self.counts = counts
        self.batch = batch
        self.ids = defaultdict(list)

    # ---- yardımçılar ------------------------------------------------------------------------------------------
    def note(self, key: str, version=None) -> None:
        self.counts[key] += 1
        if version is not None and len(self.ids[key]) < IDS_PER_KEY:
            self.ids[key].append(str(version.pk))

    def targets(self) -> dict:
        """``{dosye pk: [jurnal, …]}`` — cari semestrin aktiv jurnalları həll olunduqları dosyeyə görə."""
        CourseOffering = _model("registrar", "CourseOffering")
        offerings = CourseOffering.objects.filter(
            organization=self.organization, is_active=True, instructor__isnull=False, period__is_current=True
        ).select_related("organization", "group", "subject", "period")
        found = defaultdict(list)
        for offering in offerings.order_by("pk"):
            self.counts["journals_seen"] += 1
            syllabus = _resolved(offering)
            if syllabus is None:
                self.counts["journals_without_syllabus"] += 1
                continue
            found[syllabus.pk].append(offering)
        self.counts["dossiers_seen"] = len(found)
        return found

    # ---- saat -------------------------------------------------------------------------------------------------
    def journal_hours(self, syllabus, offering) -> tuple[dict, str]:
        """Jurnalın rəsmi saatı → ``(saat, mənbə)``; tapılmasa ``({}, d_<səbəb>)``."""
        from apps.syllabus import public as syl

        from .plan_hours import plan_hours_for_offering

        override = _clean_hours(syl.clean_override_hours(getattr(syllabus, "plan_hours_override", None)))
        if override:
            return override, "override"
        hours = _clean_hours(plan_hours_for_offering(offering))
        if hours:
            return hours, "plan"
        hours = self.parent_load_hours(offering)
        if hours:
            return hours, "parent_load"
        return {}, self.no_hours_reason(offering)

    def _task_rows(self, offering):
        try:
            TaskRow = _model("workload", "TeachingTaskRow")
        except LookupError:
            return None
        return TaskRow.objects.filter(organization_id=offering.organization_id, period_id=offering.period_id).exclude(
            task__status="cancelled"
        )

    def parent_load_hours(self, offering) -> dict:
        """Bölünmüş yarım qrup (``settings.parent_group`` — açıq bağ): ana qrupun DƏQİQ yük sətrindən bir qrupun payı."""
        import uuid

        from .plan_hours_load import merge_group_hours, row_group_hours

        group = offering.group if offering.group_id else None
        settings = group.settings if group is not None and isinstance(group.settings, dict) else {}
        try:
            parent = uuid.UUID(str(settings.get("parent_group") or ""))
        except ValueError:
            return {}
        rows = self._task_rows(offering)
        if rows is None:
            return {}
        rows = rows.filter(subject_id=offering.subject_id, groups=parent).order_by("-updated_at")
        return _clean_hours(merge_group_hours(row_group_hours(row, group_count=row.groups.count) for row in rows))

    def no_hours_reason(self, offering) -> str:
        if not offering.group_id:
            return "d_no_group"
        rows = self._task_rows(offering)
        if rows is None:
            return "d_no_load_row"
        if rows.filter(subject_id=offering.subject_id, groups=offering.group_id).exists():
            return "d_load_row_without_hours"
        if rows.filter(subject__name__iexact=offering.subject.name, groups=offering.group_id).exists():
            return "d_load_row_twin_subject"
        if rows.filter(subject_id=offering.subject_id).exists():
            return "d_load_row_other_group"
        return "d_no_load_row"

    # ---- mənbə ------------------------------------------------------------------------------------------------
    def journal_source(self, syllabus, offering) -> tuple:
        """Jurnalın mövzu siyahısının ARTIQ göstərdiyi ehtiyat mənbə → ``(növ, dosye, sətirlər)``."""
        from .journal_topic_fallback import peer_approved_source
        from .journal_topics import _course_topic_titles

        if _course_topic_titles(offering):
            return "lms", None, []
        current = syllabus.current_version
        rows = _week_rows(current)
        if _has_topics(rows):
            return "own_version", syllabus, rows
        source, rows = peer_approved_source(offering)
        if source is None:
            return "none", None, []
        return "peer", source, rows

    def pick_source(self, syllabus, offerings, teacher_id, language) -> tuple:
        """``(dosye, sətirlər, None)`` və ya ``(None, [], keçmə açarı)``."""
        from .syllabus_carry import group_language

        found = {}
        for offering in offerings:
            kind, source, rows = self.journal_source(syllabus, offering)
            found[(kind, getattr(source, "pk", None))] = (kind, source, rows)
        if len(found) != 1:
            return None, [], "skip_source_mixed"
        kind, source, rows = next(iter(found.values()))
        if kind == "lms":
            return None, [], "skip_source_lms"
        if kind == "none":
            return None, [], "skip_no_source"
        if kind == "peer":
            owner_ids = {
                source.author_id,
                getattr(source.offering, "instructor_id", None) if source.offering_id else None,
            }
            if teacher_id not in owner_ids:
                return None, [], "skip_source_other_teacher"
            if source.offering_id and source.offering.group_id and group_language(source.offering.group) != language:
                return None, [], "skip_source_language"
        return source, rows, None

    # ---- əsas axın --------------------------------------------------------------------------------------------
    def run(self) -> None:
        for syllabus_pk, offerings in self.targets().items():
            with transaction.atomic():
                self.process(syllabus_pk, offerings)

    def process(self, syllabus_pk, offerings) -> None:
        from apps.syllabus import public as syl

        Syllabus = _model("syllabus", "Syllabus")
        SyllabusShare = _model("syllabus", "SyllabusShare")
        syllabus = (
            Syllabus.objects.select_for_update(of=("self",))
            .select_related("current_version", "approved_version", "offering")
            .filter(pk=syllabus_pk)
            .first()
        )
        if syllabus is None:
            return
        open_version = syl.services.open_version_for(syllabus)
        if open_version is not None:
            if not _has_topics(_week_rows(open_version)) or not _clean_hours(open_version.plan_hours):
                self.note("skip_open_draft", open_version)
            return
        version = syl.approved_version_for(syllabus)
        if version is None:
            if not _has_topics(_week_rows(syllabus.current_version)):
                self.note("skip_not_approved", syllabus.current_version)
            return
        rows = _week_rows(version)
        has_topics = _has_topics(rows)
        if has_topics and _clean_hours(version.plan_hours):
            self.counts["healthy"] += 1
            return
        shape = "c_no_plan_hours" if has_topics else _TIER_SHAPE[_tier(syllabus)]
        if SyllabusShare.objects.filter(organization=self.organization, syllabus=syllabus).exists():
            shape = "e_shared"
        self.note(f"found_{shape}", version)
        if shape == "e_shared":
            return
        if syllabus.reused_from_id:
            self.note("skip_reused", version)
            return
        teachers = {offering.instructor_id for offering in offerings}
        if len(teachers) != 1:
            self.note("skip_teachers_mixed", version)
            return
        hours, origin = self.hours_for(syllabus, offerings, version)
        if hours is None:
            return
        if shape == "c_no_plan_hours":
            self.fix_hours_only(syllabus, version, rows, hours, offerings, origin)
        else:
            self.fill(syllabus, version, hours, offerings, next(iter(teachers)), shape, origin)

    def hours_for(self, syllabus, offerings, version) -> tuple:
        found, origins, missing = set(), set(), ""
        for offering in offerings:
            hours, origin = self.journal_hours(syllabus, offering)
            if not hours:
                missing = origin
                continue
            found.add(tuple(sorted(hours.items())))
            origins.add(origin)
        if missing:
            self.note("d_no_hours", version)
            self.counts[missing] += 1
            return None, ""
        if len(found) != 1:
            self.note("skip_hours_mixed", version)
            return None, ""
        return dict(next(iter(found))), "parent_load" if "parent_load" in origins else "plan"

    def fill(self, syllabus, version, hours, offerings, teacher_id, shape, origin) -> None:
        from apps.syllabus import public as syl

        from .syllabus_carry import group_language

        languages = {group_language(offering.group) for offering in offerings}
        if len(languages) != 1:
            self.note("skip_language_mixed", version)
            return
        source, source_rows, skip = self.pick_source(syllabus, offerings, teacher_id, next(iter(languages)))
        if skip:
            self.note(skip, version)
            return
        fitted, _changed = syl.fit_rows_to_hours(source_rows, hours)
        fitted, _changed = syl.fit_rows_to_hours(fitted[: syl.expected_week_rows(hours)], hours)
        self.write(syllabus, version, fitted, hours, offerings, shape=shape, source=source)
        self.note(f"filled_{shape}", version)
        self.counts["rows_written"] += len(fitted)
        if origin == "parent_load":
            self.counts["d_hours_from_parent_load"] += 1

    def fix_hours_only(self, syllabus, version, rows, hours, offerings, origin) -> None:
        """Forma c: mövzular qalır; sətirlərin saat cəmi plana zidd deyilsə (0 və ya bərabər) plan saatı yazılır."""
        from apps.syllabus import public as syl

        for kind in _KINDS:
            total = sum(_clean_hours({kind: row.get(kind)}).get(kind, 0) for row in rows)
            if total and total != hours.get(kind, 0):
                self.note("skip_c_hours_differ", version)
                return
        fitted, changed = syl.fit_rows_to_hours(rows, hours)
        self.write(
            syllabus, version, fitted if changed else None, hours, offerings, shape="c_no_plan_hours", source=None
        )
        self.note("fixed_c_no_plan_hours", version)
        if origin == "parent_load":
            self.counts["d_hours_from_parent_load"] += 1

    def write(self, syllabus, version, rows, hours, offerings, *, shape, source) -> None:
        from apps.syllabus import public as syl

        SyllabusSection = _model("syllabus", "SyllabusSection")
        SyllabusVersion = _model("syllabus", "SyllabusVersion")
        row = SyllabusSection.objects.select_for_update().filter(version=version, section_id=WEEK).first()
        old_data = dict(row.data or {}) if row is not None else {}
        new_data = old_data if rows is None else {**old_data, "rows": rows}
        if rows is None:
            pass  # forma c: həftə bölməsi dəyişmir
        elif row is None:
            SyllabusSection.objects.create(
                organization_id=version.organization_id, version=version, section_id=WEEK, data=new_data
            )
        elif new_data != old_data:
            row.data = new_data
            row.revision += 1
            row.save(update_fields=["data", "revision", "updated_at"])
        old_hours = dict(version.plan_hours or {})
        SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours=hours)
        version.plan_hours = hours
        syl.services.recompute_completion(version)
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(version.pk),
            resource_repr="Sillabusun həftəlik planı / plan saatı jurnalın mənbəyi və saatı ilə",
            old_values={"week": old_data, "plan_hours": old_hours},
            new_values={
                "batch": self.batch,
                "shape": shape,
                "syllabus": str(syllabus.pk),
                "source_syllabus": str(source.pk) if source is not None else "",
                "offerings": [str(offering.pk) for offering in offerings],
                "plan_hours": hours,
                "rows": len(rows) if rows is not None else 0,
                "week_changed": rows is not None,
            },
        )


def run(*, organization, actor, counts, batch: str = "") -> tuple[str, dict]:
    """→ ``(batch, {açar: [versiya id, …]})``."""
    runner = _Run(organization=organization, actor=actor, counts=counts, batch=batch or new_batch())
    runner.run()
    return runner.batch, dict(runner.ids)


def undo(*, organization, actor, counts, batch: str) -> None:
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
                resource_repr="Boş həftəlik planın doldurulmasının geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["IDS_PER_KEY", "RESOURCE", "new_batch", "run", "undo"]
