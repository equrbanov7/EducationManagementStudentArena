"""Tədris şöbəsinin «Dərs yükü» faylı → kafedranın tapşırığı, müəllim bölgüsü, açılış, tələbə qeydiyyatı.

Sahib 2026-10-23: «Tədris şöbəsi yükləyəndə avtomatik tələbənin də kabinetinə düşsün, müəllimində o fənn var —
müəllim elektron jurnalı yaza bilsin. Hansı kafedrada varsa, əlavə fərqli nə isə olarsa onu götürsün, eynisi
yüklənəndə götürməsin. Bütün hərf səhvlərinə həssas olsun. Orada yazılan müəllim yoxdursa avtomatik onun
müəllim profili də açılsın.»

Yeni məntiq icad edilmir — mövcud «Forma 1» idxalçısı (:class:`.task_form1_import.Form1Importer`) üç yerdə
genişlənir:

1. **Müəllim** — ``accounts`` tərəfinin :class:`ChairTeacherResolver`-i (Forma 7 tutuşdurması: bir hərf / ə-a /
   q-g / tərs sıra / inisiallar; tapılmayan → FİN-siz müəllim hesabı bu kafedrada). Başqa kafedranın tapılmış
   müəllimi bu kafedrada ƏLAVƏ müəllim üzvlüyü alır (``join_chair_as_teacher`` — Forma 1-in sahib qaydası).
2. **Sətir** — fayl sətri tapşırığın heç bir sətrinə düşmürsə (semestr + qrup + fənn oxşarlığı ≥ 0.88) YENİ
   sətir yaradılır (``row_edit.save_row_amended``: bölünmüş sənəddə «Rəsmi sərəncam» düzəlişi ilə). Fənn
   kataloqda yoxdursa yaradılır (``Importer.resolve_subject`` — kod «QKU-N», kredit fayldan). Qrup YARADILMIR —
   tələbələr qeydiyyatdakı qrupdan gəlir; tapılmayan qrup önizləmədə görünür.
3. **Bölgü** — ``reassign`` açıqdır («fərqli nə isə olarsa götürsün»): eyni müəllim/saat → ``unchanged`` (heç nə
   yazılmır, bildiriş getmir), fərqli → düzəliş axını ilə dəyişir (bağlanmış jurnal / keçmiş semestr blokerləri
   qüvvədədir). Sonra ``_confirm_and_enroll`` → açılış (jurnal sahibi) + qrupun tələbələri.

Tədris şöbəsinin rolunda ``workload.distribute`` YOXDUR (bölgü kafedranındır). Bu əməl yalnız
``workload.load_import`` açarı ilə açılır və seçilmiş KAFEDRA ÜÇÜN bir dəfəlik genişləndirilmiş aktorla işləyir —
audit sətirlərində real istifadəçi qalır.

ÖNİZLƏMƏ = eyni axın savepoint-də işləyir və GERİ QAYTARILIR (``transaction.set_rollback``): saylar real tətbiqlə
eynidir, heç nə qalmır (``on_commit`` bildirişləri də atılır).
"""

from __future__ import annotations

import io
from collections import Counter

from django.db import transaction

from core.constants import OrgUnitType

from ..constants import PERM_DISTRIBUTE, PERM_LOAD_IMPORT, PERM_MANAGE, PERM_VIEW, AmendmentReason, TaskStatus
from .distribution import teacher_loads
from .scoping import WorkloadActor, WorkloadDenied
from .task_form1_import import Form1Importer, _RowIndex, subject_slug
from .task_workbook_choice import CHOSEN_NONE
from .tasks import get_or_create_task

ROW_NOTE = "Dərs yükü faylından əlavə olundu (Tədris şöbəsi)"
ROW_CREATED = "row_created"


def import_actor(actor_user, organization) -> WorkloadActor:
    """Seçilmiş kafedra üçün bir dəfəlik aktor: idarə + bölgü (çağıran ``workload.load_import``-u yoxlayıb)."""
    return WorkloadActor(
        user=actor_user,
        organization=organization,
        permissions=(PERM_VIEW, PERM_MANAGE, PERM_DISTRIBUTE, PERM_LOAD_IMPORT),
        is_superadmin=True,
    )


class LoadUploadImporter(Form1Importer):
    def __init__(self, *, importer, chair, teachers):
        super().__init__(importer=importer, chair=chair)
        self.teachers = teachers
        self.texts: dict = {}
        self.teacher_reports: dict = {}
        self.row_status: dict = {}  # (line, season) → yeni sətir statusu
        self.rows_created = 0
        self.confirmed = False

    # ── müəllim ───────────────────────────────────────────────────────────
    def resolve_teacher(self, words: tuple) -> tuple:
        if words in self._teacher_cache:
            return self._teacher_cache[words]
        result = self.teachers.resolve(self.texts.get(words, " ".join(words)))
        user = result.user if result.resolved else None
        if user is not None and user.pk and user.pk not in {u.pk for u in self._chair_users}:
            if not result.status.startswith("created"):
                self._join_chair(user)
            self._chair_users.append(user)
        self.counters[f"teacher_{result.status}"] += 1
        self.teacher_reports[words] = {
            "status": result.status,
            "display": result.display,
            "username": getattr(user, "username", "") or "",
            "candidates": result.candidates[:5],
        }
        self._teacher_cache[words] = (user, result.status)
        return self._teacher_cache[words]

    # ── əsas ──────────────────────────────────────────────────────────────
    def run(self, task, entries: list, skipped: list) -> None:
        self.texts = {entry.name_words: entry.teacher_text for entry in entries}
        self._create_missing_rows(task, entries)
        super().run(task, entries, skipped)

    def _apply(self, task, rows_by_pk, contributions, entry_reports, index) -> None:
        loads_before = teacher_loads(task)
        original = self.importer._confirm_and_enroll

        def tracked(*args, **kwargs):
            self.confirmed = True
            return original(*args, **kwargs)

        self.importer._confirm_and_enroll = tracked
        try:
            super()._apply(task, rows_by_pk, contributions, entry_reports, index)
        finally:
            self.importer._confirm_and_enroll = original
        if self.importer.apply and self.rows_created and not self.confirmed:
            # Bölünmüş sənədə düzəlişlə əlavə olunan yeni sətir: ``Form1Importer`` yalnız APPROVED/DISTRIBUTING
            # və ya öz açdığı düzəlişdə təsdiq edir — yeni sətrin açılışı (jurnal) qalmasın.
            task.refresh_from_db(fields=["status"])
            if task.status in (TaskStatus.APPROVED, TaskStatus.DISTRIBUTING, TaskStatus.AMENDED):
                original(task, loads_before=loads_before)
                self.confirmed = True

    # ── yeni sətir ────────────────────────────────────────────────────────
    def _create_missing_rows(self, task, entries) -> None:
        index = _RowIndex(task)
        specs: dict = {}
        for entry in entries:
            if entry.chosen_by == CHOSEN_NONE:
                continue
            if index.match(entry)[0]:
                continue
            key = (entry.season, subject_slug(entry.subject_text), entry.group_keys)
            spec = specs.setdefault(key, {"entry": entry, "hours": {}, "lines": []})
            for activity, hours in entry.hours.items():
                spec["hours"][activity] = max(spec["hours"].get(activity, 0), int(hours or 0))
            spec["lines"].append((entry.line, entry.season))
        for spec in specs.values():
            status = self._create_row(task, spec)
            self.counters[status.split(":")[0]] += 1
            for line in spec["lines"]:
                self.row_status[line] = status

    def _groups(self, entry) -> tuple[list, list]:
        from .task_form1_parsing import group_tokens

        found, missing = {}, []
        for token in group_tokens(entry.groups_text):
            units = [unit for unit, _action in self.importer.resolve_group(token, None) if unit is not None]
            if not units:
                missing.append(token)
            for unit in units:
                found[unit.pk] = unit
        return list(found.values()), missing

    def _create_row(self, task, spec) -> str:
        entry = spec["entry"]
        groups, missing = self._groups(entry)
        if not groups:
            return "group_not_found:" + ", ".join(missing)[:120]
        subject, _action, _name = self.importer.find_subject(entry.subject_text)
        if subject is None:
            subject = self.importer.resolve_subject(entry.subject_text, self.chair, entry.credits or "")[0]
        if subject is None:
            return "subject_unresolved"
        period = self.importer.periods.get(entry.season)
        hours = spec["hours"]
        data = {
            "season": entry.season,
            "subject_id": str(subject.pk),
            "subject_text": entry.subject_text[:255],
            "groups_text": entry.groups_text[:255],
            "group_ids": [str(unit.pk) for unit in groups],
            "union_count": len(groups),
            "subgroup_count": 1,
            "student_count_text": (entry.students or "")[:100],
            "credits": (entry.credits or "")[:20],
            "credits_value": _int(entry.credits),
            "note": ROW_NOTE,
        }
        if period is not None and period.pk:
            data["period_id"] = str(period.pk)
        for activity in ("lecture", "seminar", "lab"):
            if hours.get(activity):
                data[f"{activity}_plan"] = hours[activity]
                data[f"{activity}_total"] = hours[activity]
        parent = groups[0].parent if groups[0].parent_id else None
        if parent is not None and parent.unit_type == OrgUnitType.SPECIALTY:
            data["specialty_id"] = str(parent.pk)
        from .row_edit import save_row_amended

        amend = {"reason": str(AmendmentReason.OFFICIAL), "note": self.importer.applier.note}
        try:
            with transaction.atomic():
                save_row_amended(task=task, actor=self.importer.actor, data=data, amend=amend)
        except WorkloadDenied as exc:
            return f"row_blocked:{exc.code}"
        self.rows_created += 1
        task.refresh_from_db(fields=["status", "distributed_at"])
        return ROW_CREATED + (":groups_missing=" + ", ".join(missing)[:120] if missing else "")

    # ── hesabat ───────────────────────────────────────────────────────────
    def report(self) -> dict:
        lines = []
        for item in self.report_rows:
            words = tuple(item.get("teacher", "").split())
            teacher = self.teacher_reports.get(words, {})
            lines.append(
                {
                    "line": item.get("line"),
                    "season": item.get("season", ""),
                    "teacher": teacher.get("display") or item.get("teacher", ""),
                    "teacher_status": teacher.get("status", item.get("teacher_action", "")),
                    "username": teacher.get("username") or item.get("username", ""),
                    "candidates": teacher.get("candidates", []),
                    "groups": item.get("groups", ""),
                    "subject": item.get("subject", ""),
                    "hours": item.get("hours", ""),
                    "row": self.row_status.get((item.get("line"), item.get("season")), item.get("rows", "")),
                    "assignment": item.get("assignment", "") or "",
                }
            )
        counters = Counter()
        for source in (self.counters, self.applier.counters, self.importer.counters):
            counters.update(source)
        new_teachers = [
            {"username": user.username, "display": display} for user, display in getattr(self.teachers, "created", [])
        ]
        return {"lines": lines, "counters": dict(counters), "new_teachers": new_teachers}


def _int(value) -> int:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return min(int(digits[:3]), 60) if digits else 0


def run_load_upload(*, organization, chair, actor_user, entries, skipped, year: str, apply: bool) -> dict:
    """Bütün axın; ``apply=False`` — eyni axın savepoint-də, sonda GERİ QAYTARILIR (önizləmə)."""
    from django.apps import apps as django_apps

    from ..teacher_hooks import chair_teacher_resolver
    from .task_workbook_import import Importer

    with transaction.atomic():
        importer = Importer(
            organization=organization,
            year=year,
            actor_user=actor_user,
            apply=True,
            stdout=io.StringIO(),
            create_teachers=False,
            reassign=True,
        )
        actor = import_actor(actor_user, organization)
        importer.actor = actor
        importer.applier.actor = actor
        importer.applier.note = f"Dərs yükü faylı {year} (Tədris şöbəsi) — bölgü fayla uyğunlaşdırıldı"
        importer.ensure_periods()
        task, task_created = get_or_create_task(
            organization=organization, chair_id=chair.pk, academic_year=year, actor=actor
        )
        teachers = chair_teacher_resolver(
            organization, chair, actor_user=actor_user, apply=True, tag=f"{chair.name} · {year}"
        )
        load = LoadUploadImporter(importer=importer, chair=chair, teachers=teachers)
        # Qeydiyyat iki yerdən gəlir (açılış sinxronu + ``_confirm_and_enroll``) — real fərq sayılır.
        enrollments = django_apps.get_model("registrar", "Enrollment").objects.filter(organization=organization)
        enrollments_before = enrollments.count()
        load.run(task, entries, skipped)
        report = load.report()
        report["counters"]["students_enrolled"] = enrollments.count() - enrollments_before
        task.refresh_from_db(fields=["status"])
        report.update(
            {
                "task_created": bool(task_created),
                "task_status": str(task.status),
                "confirmed": load.confirmed,
                "entries": len(entries),
                "skipped": skipped,
                "applied": bool(apply),
            }
        )
        if not apply:
            transaction.set_rollback(True)
    return report


__all__ = ["PERM_LOAD_IMPORT", "LoadUploadImporter", "import_actor", "run_load_upload"]
