"""Delta paketinin hədəfə tətbiqi — orkestrator (``legacy_delta_apply`` əmri çağırır).

Bütün fazalar BİR tranzaksiyadadır: ya hamısı yazılır, ya heç nə. Dry-run eyni kodu işlədir və sonda
tranzaksiyanı GERİ QAYTARIR — hesabatdakı saylar «tətbiq etsək nə olardı»nın dəqiq sayıdır (təxmin yox).

Fazalar: tələbələr (iki keçid: tutuşdur, sonra yarat) → açılış (fənn/qrup/müəllim) → qeydiyyat → dərs + xana →
yekun/təkrar imtahan → sillabus → dərs yükü (rəsmi «Dərs yükü faylı» axını) → eyni fənnin ikinci (boş) öz-qrup qeydiyyatı «alt qrup
birləşməsi» ilə tarixçəyə → legacy alt qrup tələbələrinə rəsmi işarə (ana qrup izi + «Alt qrupa
yerləşdirildi» sətri, ``subgroups``) → tələbə profilində boş sahələr → (yalnız açıq seçiləndə) aktiv reyestrin
köhnə sistemlə rəsmi köçürmə/xaric əmrləri ilə nizamlanması (``registry_sync``) → (yalnız açıq seçiləndə) cari
semestr jurnallarında olmayan, proqram müddəti bitmiş tələbələrin rəsmi «Məzun etmə» əmri (``graduation``); (yalnız açıq seçiləndə,
HAMISINDAN ƏVVƏL) fənn kodu toqquşması ilə yanlış karta düşmüş delta açılışlarının düzəlişi (``subject_collisions``); (yalnız
açıq seçiləndə) cari semestr jurnalı olan müəllimin köhnə sillabusu semestrsiz baza dosye kimi (``syllabi_backfill``). Sonda bir audit sətri (manifest:
saylar + yaradılmış kiçik obyektlərin id-ləri) — ``resource_type=legacy_import.delta_batch``.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from .collisions import fix_subject_collisions
from .dedupe import dedupe_enrollments
from .finals import apply_finals
from .graduation import sync_graduation
from .history import HISTORY_PHASES, HistoryPhaseMismatch, apply_history, apply_history_topics
from .journals import build_enrollments, build_offerings
from .lessons import build_lessons_and_marks
from .people import StudentMapper, TeacherMapper, student_gender
from .registry_sync import sync_registry
from .resolve import Catalog, lesson_date, text
from .subgroups import mark_subgroups
from .syllabi import import_syllabi
from .syllabi_backfill import backfill_teacher_syllabi, check_phases
from .topics import apply_topics
from .workload import build_workload

BATCH_RESOURCE = "legacy_import.delta_batch"
BULK_CHUNK = 2000
#: Manifestdə id-ləri saxlanılan (az saylı) növlər; qalanı yalnız say.
MANIFEST_KINDS = (
    "groups",
    "subjects",
    "offerings",
    "teachers",
    "students",
    "syllabus_versions",
    "workload_chairs",
    "history_enrollments",
    "history_offerings",
)
PHASES = (
    "students",
    "offerings",
    "enrollments",
    "lessons",
    "topics",
    "finals",
    "syllabi",
    "workload",
    "dedupe",
    "subgroups",
    "profiles",
    "registry_sync",
    "graduation",
    "history",
    "history_topics",
    "subject_collisions",
    "syllabi_backfill",
)
#: Yalnız AÇIQ seçiləndə (``--phase`` və ya paketin ``snapshot.phases``-i) işləyən fazalar — reyestr əmrləri yazır
#: (``registry_sync``, ``graduation``); ``history*`` tarixi (bağlı) jurnallara əlavə edir (``delta/history.py``);
#: ``subject_collisions`` yanlış fənn kartına düşmüş açılışları düzgün karta keçirir (``delta/collisions.py``);
#: ``syllabi_backfill`` cari semestr jurnalı olan müəllimə köhnə sillabusunu baza dosye kimi gətirir
#: (``delta/syllabi_backfill.py``, paket ``legacy_delta_extract --teacher-syllabi``).
OPT_IN_PHASES = ("registry_sync", "graduation", "history", "history_topics", "subject_collisions", "syllabi_backfill")
DEFAULT_PHASES = tuple(phase for phase in PHASES if phase not in OPT_IN_PHASES)


def new_tag() -> str:
    import secrets

    return f"delta-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


class DeltaRun:
    """Bir tətbiq qaçışının vəziyyəti: indekslər, mapper-lər, saylar, manifest."""

    def __init__(self, *, organization, actor, bundle: dict, tag: str, until: datetime.date):
        self.organization = organization
        self.actor = actor
        self.bundle = bundle
        self.tag = tag
        self.until = until
        self.counters: Counter = Counter()
        self.name_rows: list = []
        self.manifest: dict = defaultdict(list)
        self.legacy_periods = {row["id"]: row for row in bundle["periods"]}
        self.legacy_groups = {row["id"]: row for row in bundle["groups"]}
        self.legacy_subjects = {row["id"]: row for row in bundle["subjects"]}
        self.catalog = Catalog(organization)
        self.teachers = TeacherMapper(self, {row["id"]: row for row in bundle["workers"]})
        self.students = StudentMapper(self, {row["id"]: row for row in bundle["students"]})
        self._periods: dict = {}
        self._offering_period: dict = {}

    # ── hesabat ───────────────────────────────────────────────────────────
    def count(self, key: str, amount: int = 1) -> None:
        if amount:
            self.counters[key] += amount

    def names(self, kind: str, display: str, detail: str = "") -> None:
        self.name_rows.append((kind, display, detail))

    def created(self, kind: str, pk) -> None:
        self.manifest[kind].append(str(pk))

    def touched(self, kind: str, pk, fields) -> None:
        self.count(f"touched.{kind}")

    def bulk_create(self, model, objects, kind: str) -> None:
        for start in range(0, len(objects), BULK_CHUNK):
            model.objects.bulk_create(objects[start : start + BULK_CHUNK], batch_size=BULK_CHUNK)
        self.count(f"written.{kind}", len(objects))

    # ── köməkçi indekslər ─────────────────────────────────────────────────
    def period_of(self, semestr):
        if semestr not in self._periods:
            legacy = self.legacy_periods.get(semestr)
            self._periods[semestr] = self.catalog.period_for(legacy) if legacy else None
        return self._periods[semestr]

    def period_of_offering(self, offering_id):
        if offering_id not in self._offering_period:
            CourseOffering = django_apps.get_model("registrar", "CourseOffering")
            offering = CourseOffering.objects.select_related("period").filter(pk=offering_id).first()
            self._offering_period[offering_id] = offering.period if offering else None
        return self._offering_period[offering_id]

    def ledger_enrollments(self, keys) -> dict:
        """Köhnə semestrlər: ``(uniqid, legacy tələbə)`` → cutover-in ``Enrollment``-i (ledger)."""

        from .resolve import ledger_map

        if not keys:
            return {}
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        mapping = ledger_map(self.organization, "journal_enrollment", {f"{uq}:{sid}" for uq, sid in keys})
        objects = Enrollment.objects.in_bulk([value for value in mapping.values()])
        out = {}
        for uq, sid in keys:
            target = mapping.get(f"{uq}:{sid}")
            enrollment = objects.get(_as_uuid(target)) if target else None
            if enrollment is not None:
                out[(uq, sid)] = enrollment
        return out

    def writable_offerings(self, offering_ids) -> set:
        from apps.registrar.public import handover

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        ids = list(offering_ids)
        active = set(CourseOffering.objects.filter(pk__in=ids, is_active=True).values_list("pk", flat=True))
        return active - handover.closed_offering_ids(list(active))

    def excuse_index(self):
        windows: dict = defaultdict(list)
        for row in self.bundle["excuse_windows"]:
            start, end = _date(row.get("allowed_date_start")), _date(row.get("allowed_date_end"))
            if start and end:
                windows[row["student_id"]].append((start, end))

        def excused(legacy_student_id, date) -> bool:
            return any(start <= date <= end for start, end in windows.get(legacy_student_id, ()))

        return excused

    # ── fazalar ───────────────────────────────────────────────────────────
    def run(self, phases=DEFAULT_PHASES) -> None:
        if "subject_collisions" in phases:
            # Əvvəl: düzəliş xəritəsi yazılır, eyni qaçışdakı sonrakı fazalar onu görür.
            fix_subject_collisions(self)
        if "enrollments" in phases or "students" in phases:
            self.students.prepare()
        slices = build_offerings(self) if "offerings" in phases else {}
        enrollments = build_enrollments(self, slices) if "enrollments" in phases else {}
        if "lessons" in phases:
            build_lessons_and_marks(self, slices, enrollments, until=self.until)
        if "topics" in phases:
            apply_topics(self, slices)
        if "finals" in phases:
            apply_finals(self, enrollments)
        if "syllabi" in phases:
            import_syllabi(self, slices)
        if "workload" in phases:
            build_workload(self, slices)
        full = (self.bundle.get("snapshot") or {}).get("full_semesters") or []
        if "dedupe" in phases:
            dedupe_enrollments(self, [getattr(self.period_of(semestr), "pk", None) for semestr in full])
        if "subgroups" in phases:
            mark_subgroups(self, [getattr(self.period_of(semestr), "pk", None) for semestr in full])
        if "profiles" in phases:
            self._profiles()
        if "registry_sync" in phases:
            sync_registry(self)
        if "graduation" in phases:
            sync_graduation(self)
        if "history" in phases:
            apply_history(self)
        if "history_topics" in phases:
            apply_history_topics(self)
        if "syllabi_backfill" in phases:
            backfill_teacher_syllabi(self)
        for _legacy_id, user_pk in self.teachers.created:
            self.created("teachers", user_pk)
        for _legacy_id, user_pk in self.students.created:
            self.created("students", user_pk)

    def _profiles(self) -> None:
        """Tapılmış tələbələrdə BOŞ ata adı / doğum tarixi / cins doldurulur; qrup/azad fərqi yalnız sayılır."""

        from ..legacy_demographics import legacy_birth_date

        UserProfile = django_apps.get_model("accounts", "UserProfile")
        resolved = {
            legacy_id: user_id for legacy_id, (user_id, _outcome) in self.students._cache.items() if user_id is not None
        }
        profiles = {p.user_id: p for p in UserProfile.objects.filter(user_id__in=list(resolved.values()))}
        rows = {row["id"]: row for row in self.bundle["students"]}
        for legacy_id, user_id in resolved.items():
            row, profile = rows.get(legacy_id), profiles.get(user_id)
            if row is None or profile is None:
                continue
            fields = []
            patronymic = text(row.get("father_name"), limit=150)
            if not (profile.patronymic or "").strip() and patronymic:
                profile.patronymic = patronymic
                fields.append("patronymic")
            birth = legacy_birth_date(row.get("birthday") or None)
            if profile.birth_date is None and birth is not None:
                profile.birth_date = birth
                fields.append("birth_date")
            gender = student_gender(row)
            if (profile.gender or "unspecified") == "unspecified" and gender != "unspecified":
                profile.gender = gender
                fields.append("gender")
            if fields:
                profile.save(update_fields=fields + ["updated_at"])
                self.count("profile.filled")
            baseline = row.get("baseline") or {}
            if baseline.get("group_id") not in (None, row.get("group_id")):
                self.count("profile.legacy_group_changed_report_only")
                self.names(
                    "student_group_changed", _display(row), f"{baseline.get('group_id')} → {row.get('group_id')}"
                )
            if int(row.get("azadedildi") or 0) == 1 and int(baseline.get("azadedildi") or 0) == 0 and baseline:
                self.count("profile.legacy_expelled_report_only")
                self.names("student_expelled", _display(row), "")

    def audit(self) -> None:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        snapshot = self.bundle.get("snapshot") or {}
        log_action(
            action=AuditAction.CREATE,
            user=self.actor,
            organization=self.organization,
            obj=self.organization,
            new_values={
                "counters": dict(sorted(self.counters.items())),
                "created": {kind: self.manifest.get(kind, []) for kind in MANIFEST_KINDS},
                "snapshot_sha256": snapshot.get("sha256", ""),
                "full_semesters": snapshot.get("full_semesters", []),
            },
            reason=f"legacy_delta_apply {self.tag}",
            resource_type=BATCH_RESOURCE,
            resource_id=self.tag,
            resource_repr=self.tag,
        )

    def summary(self) -> dict:
        return {
            "tag": self.tag,
            "counters": dict(sorted(self.counters.items())),
            "created": {kind: len(values) for kind, values in sorted(self.manifest.items())},
        }


def execute(*, organization, actor, bundle: dict, apply: bool, until, tag: str = "", phases=DEFAULT_PHASES) -> DeltaRun:
    """Bir tranzaksiyada bütün fazalar; ``apply=False`` → sonda geri qaytarılır."""

    from core.rls import apply_rls_request_context

    from ..repair_support import disable_parallel_query

    if bundle.get("history") and set(phases) - set(HISTORY_PHASES):
        # Tarixi paketin tələbə bölməsi boşluq tələbələridir — adi fazalar onlar üçün hesab YARADARDI.
        raise HistoryPhaseMismatch("legacy_delta_history_bundle_phase_mismatch")
    check_phases(bundle, phases)
    with transaction.atomic():
        apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
        disable_parallel_query(local=True)
        run = DeltaRun(organization=organization, actor=actor, bundle=bundle, tag=tag or new_tag(), until=until)
        run.run(phases)
        if apply:
            run.audit()
        else:
            transaction.set_rollback(True)
    return run


def _date(value):
    text_value = str(value or "")[:10]
    try:
        return datetime.date.fromisoformat(text_value)
    except ValueError:
        return None


def _as_uuid(value):
    import uuid

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


def _display(row: dict) -> str:
    return " ".join(part for part in (text(row.get("last_name")), text(row.get("first_name"))) if part)


__all__ = ["BATCH_RESOURCE", "DEFAULT_PHASES", "PHASES", "DeltaRun", "execute", "lesson_date", "new_tag"]
