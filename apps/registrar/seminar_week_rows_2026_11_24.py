"""Seminar saatı «mühazirə» kimi yazılmış həftəlik planlar — bütün sillabuslar üzrə düzəliş (sahib 2026-11-24).

Şikayət (sahib, «Ekskursiya fəaliyyətinin idarə olunması», 803/5 BT): fənn 45 saatdır (30 mühazirə + 15 seminar),
yükdə də belədir, amma sillabusda 23 mövzunun HAMISI mühazirədir (22×2 + 1 = 45 saat mühazirə, seminar 0).  Son 8
sətir əslində seminar mövzularıdır (cəmi 15 saat) — köçürmədə/yazıda seminar sütunu boş qalıb, saat mühazirəyə
düşüb.  Nəticədə jurnalda seminar dərsi üçün seminar mövzusu yoxdur.

Forma (yalnız bu dəqiq forma düzəlir, qalanı sayılır):

* versiyanın plan saatında ``B`` növünün saatı var, sətirlərdə ``B`` cəmi 0-dır;
* başqa ``A`` növünün sətir cəmi = ``plan[A] + plan[B]``;
* sətirlər yuxarıdan aşağı ``A`` üzrə toplananda cəm məhz ``plan[A]``-ya çatan bir nöqtə var, ondan sonrakı
  («quyruq») sətirlərdə yalnız ``A`` saatı var və onların cəmi ``plan[B]``-dir.

Düzəliş — quyruq sətirlərinin ``A`` saatı ``B``-yə keçir.  Mövzu, nəticə, digər bölmələr, status və təsdiq
toxunulmur.  Versiyanın plan saatı boşdursa jurnalın (dosyenin açılışının) saatı ilə yoxlanılır və uyğun gələrsə
o saat versiyaya da yazılır.  Arxivlənmiş versiyalara toxunulmur.  Hər yazının auditində ``batch`` + köhnə həftə
məlumatı + köhnə plan saatı var; ``undo`` onları qaytarır.
"""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.seminar_week_rows_20261124"
REASON = "Sahib 2026-11-24: sillabusda seminar saatı mühazirə kimi yazılmışdı — son sətirlər seminara keçirildi"
UNDO_REASON = "Sahib 2026-11-24: seminar sətirlərinin düzəlişi geri qaytarıldı"
WEEK = "week"
KINDS = ("lecture", "seminar", "lab")
IDS_PER_KEY = 60


def _model(app: str, name: str):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"semwk-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def clean_hours(value) -> dict:
    return {kind: _int((value or {}).get(kind)) for kind in KINDS if _int((value or {}).get(kind))}


def misplaced_fix(rows, plan_hours):
    """Forma uyğundursa ``(yeni sətirlər, A, B, quyruq sətir sayı)``, deyilsə ``None``."""
    planned = {kind: _int((plan_hours or {}).get(kind)) for kind in KINDS}
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    totals = {kind: sum(_int(row.get(kind)) for row in rows) for kind in KINDS}
    for missing in KINDS:
        if not planned[missing] or totals[missing]:
            continue
        for carrier in KINDS:
            if carrier == missing or not planned[carrier]:
                continue
            if totals[carrier] != planned[carrier] + planned[missing]:
                continue
            running, split = 0, None
            for index, row in enumerate(rows):
                running += _int(row.get(carrier))
                if running == planned[carrier]:
                    split = index + 1
                    break
                if running > planned[carrier]:
                    break
            if split is None:
                continue
            tail = rows[split:]
            if any(_int(row.get(kind)) for row in tail for kind in KINDS if kind != carrier):
                continue
            moved = 0
            for row in tail:
                hours = _int(row.get(carrier))
                if hours:
                    moved += 1
                row[missing] = hours
                row[carrier] = 0
            return rows, carrier, missing, moved
    return None


class _Run:
    def __init__(self, *, organization, actor, counts, batch):
        self.organization = organization
        self.actor = actor
        self.counts = counts
        self.batch = batch
        self.ids = defaultdict(list)

    def note(self, key: str, version=None) -> None:
        self.counts[key] += 1
        if version is not None and len(self.ids[key]) < IDS_PER_KEY:
            self.ids[key].append(str(version.pk))

    def offering_hours(self, syllabus) -> dict:
        from .plan_hours import plan_hours_for_offering

        if not syllabus.offering_id:
            return {}
        return clean_hours(plan_hours_for_offering(syllabus.offering))

    def run(self) -> None:
        SyllabusVersion = _model("syllabus", "SyllabusVersion")
        pks = list(
            SyllabusVersion.objects.filter(organization=self.organization)
            .exclude(status="archived")
            .order_by("created_at")
            .values_list("pk", flat=True)
        )
        self.counts["scanned"] = len(pks)
        for pk in pks:
            with transaction.atomic():
                self.process(pk)

    def process(self, pk) -> None:
        from apps.syllabus import public as syl

        SyllabusVersion = _model("syllabus", "SyllabusVersion")
        SyllabusSection = _model("syllabus", "SyllabusSection")
        version = (
            SyllabusVersion.objects.select_for_update(of=("self",))
            .select_related("syllabus", "syllabus__offering")
            .filter(pk=pk)
            .first()
        )
        if version is None:
            return
        section = SyllabusSection.objects.select_for_update().filter(version=version, section_id=WEEK).first()
        if section is None:
            return
        rows = syl.week_plan_rows(section.data or {})
        stored = clean_hours(version.plan_hours)
        plan, plan_from = stored, "version"
        found = misplaced_fix(rows, plan) if plan else None
        if found is None:
            journal = self.offering_hours(version.syllabus)
            if journal and journal != stored:
                found = misplaced_fix(rows, journal)
                plan, plan_from = journal, "journal"
        if found is None:
            return
        new_rows, carrier, missing, moved = found
        self.note(f"fix_{version.status}_{carrier}_to_{missing}", version)
        if plan_from == "journal":
            self.counts["plan_hours_from_journal"] += 1
        self.counts["rows_moved"] += moved
        old_data = dict(section.data or {})
        section.data = {**old_data, "rows": new_rows}
        section.revision += 1
        section.save(update_fields=["data", "revision", "updated_at"])
        old_hours = dict(version.plan_hours or {})
        if plan_from == "journal":
            SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours=plan)
            version.plan_hours = plan
        syl.services.recompute_completion(version)
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(version.pk),
            resource_repr="Sillabusun həftəlik planında seminar sətirləri",
            old_values={"week": old_data, "plan_hours": old_hours},
            new_values={
                "batch": self.batch,
                "syllabus": str(version.syllabus_id),
                "from": carrier,
                "to": missing,
                "rows_moved": moved,
                "plan_hours": plan,
            },
        )


def run(*, organization, actor, counts: Counter, batch: str = "") -> tuple:
    """→ ``(batch, {açar: [versiya id, …]})``.  Dry-run-ı çağıran tranzaksiyanı geri qaytarmaqla edir."""
    runner = _Run(organization=organization, actor=actor, counts=counts, batch=batch or new_batch())
    runner.run()
    return runner.batch, dict(runner.ids)


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
                resource_repr="Seminar sətirləri düzəlişinin geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["IDS_PER_KEY", "RESOURCE", "misplaced_fix", "new_batch", "run", "undo"]
