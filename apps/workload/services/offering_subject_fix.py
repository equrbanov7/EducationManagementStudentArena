"""Səhv fənnə bağlanmış jurnalın fənnini YERİNDƏ düzəltmək (2026-11-03).

Hal: jurnal (``CourseOffering``) və onun yük sətri «X-2» (Yaz) fənninə bağlanıb, həqiqətdə Payız «X-1» olmalıdır;
jurnalda dərslər və xanalar var. Veb ilə sətrin fənnini dəyişmək offering sinxronunda YENİ BOŞ jurnal yaradır,
köhnəsi tarixçəyə düşür; ``registrar.twin_merge`` isə köhnə (səhv fənnin) sillabusunu daşıyır. Bu xidmət:

1. ``offering.subject``-i YERİNDƏ dəyişir (``registrar.subject_merge_apply`` icazəsi — DB trigger-i yalnız fənn
   sütununun, eyni dövr/qrup/təşkilatda dəyişməsinə bu tranzaksiyada icazə verir). Dərslər, xanalar, qeydiyyatlar
   toxunulmur — əvvəl/sonra barmaq izi ilə yoxlanılır.
2. ``detach_syllabus`` — köhnə səhv sillabus bağı: paylaşım (``SyllabusShare``) silinir; jurnalın ÖZ dosyesidirsə
   dosye jurnaldan ayrılır (``offering=NULL`` + passiv — məzmun/versiyalar qalır, jurnalda görünmür).
3. ``attach_syllabus`` — düzgün sillabus PAYLAŞMA ilə bağlanır (``syllabus.link_legacy_share`` qaydaları: eyni
   fənn + semestr, kök dosye, eyni müəllim, jurnalın başqa sillabusu yoxdur).
4. ``row`` — yük sətrinin fənni düzəliş axını ilə (``save_row_amended``, ``sync_offerings=True``) dəyişir. Jurnal
   artıq hədəf fənndədir, ona görə sinxron MÖVCUD jurnalı tapır — yeni jurnal yaranmır (yoxlanılır: qrup + dövr
   üzrə açılış sayı dəyişməməlidir).

Dayandırır (heç nə yazılmır): hədəf fənn + dövr + qrup üçün BAŞQA açılış (toqquşma), köhnə fənndə başqa yük sətri
(sinxron köhnə fənnin jurnalını yenidən yaradardı), hədəf fənndə başqa yük sətri, çox qruplu sətir (axın), jurnala
bağlı başqa fənnin imtahanı, qrupun köhnə fənn üçün seçmə qərarı. İdempotent: ikinci qaçış ``*_already`` sayır.
Audit: ``registrar.offering_subject_fix`` sətri (köhnə/yeni bağlar + qorunan datanın hash-i).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from django.apps import apps
from django.db import connection, transaction
from django.utils import timezone

from apps.registrar.public import subject_merge_apply
from apps.syllabus.public import link_legacy_share
from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason
from .row_edit import save_row_amended
from .scoping import WorkloadDenied, resolve_actor

RESOURCE = "registrar.offering_subject_fix"
REASON = "Jurnalın səhv fənn bağı yerində düzəldildi (dərslər, xanalar, tələbələr toxunulmadı)"


class OfferingSubjectFixError(ValueError):
    pass


def model(name):
    return apps.get_model(name)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _rows(query) -> list:
    return list(query.order_by("pk").values())


def protected_hash(offering_id) -> str:
    """Jurnalın akademik datası — dərslər, xanalar, qeydiyyatlar (fənn düzəlişi bunlara TOXUNMAMALIDIR)."""
    lessons = model("registrar.Lesson").objects.filter(offering_id=offering_id)
    return _digest(
        {
            "lessons": _rows(lessons),
            "marks": _rows(model("registrar.LessonMark").objects.filter(lesson__in=lessons)),
            "enrollments": _rows(model("registrar.Enrollment").objects.filter(offering_id=offering_id)),
        }
    )


def _fail(code):
    raise OfferingSubjectFixError(code)


def _receipt(organization, offering_id):
    return (
        model("audit.AuditLog")
        .objects.filter(organization=organization, resource_type=RESOURCE, resource_id=str(offering_id))
        .order_by("-created_at")
        .first()
    )


class _Fix:
    def __init__(self, organization, user, offering_id, subject_id):
        self.org = organization
        self.user = user
        self.counts = Counter()
        Offering = model("registrar.CourseOffering")
        self.offering = (
            Offering.objects.select_for_update(of=("self",)).filter(pk=offering_id, organization=organization).first()
        ) or _fail("offering_not_found")
        if self.offering.group_id is None:
            _fail("offering_without_group")
        self.target = (
            model("registrar.Subject").objects.filter(pk=subject_id, organization=organization).first()
        ) or _fail("subject_not_found")
        receipt = _receipt(organization, self.offering.pk)
        self.receipt = dict(receipt.new_values or {}) if receipt else {}
        if self.offering.subject_id != self.target.pk:
            self.original = str(self.offering.subject_id)
        else:
            self.original = self.receipt.get("old_subject") or ""  # təkrar qaçış: əvvəlki düzəlişin mənbə fənni

    # ── yoxlamalar (heç nə yazılmır) ────────────────────────────────────────
    def check_scope(self):
        o = self.offering
        if (
            model("registrar.CourseOffering")
            .objects.filter(organization=self.org, subject=self.target, period_id=o.period_id, group_id=o.group_id)
            .exclude(pk=o.pk)
            .exists()
        ):
            _fail("target_offering_exists")
        if model("exams.Exam").objects.filter(journal_offerings=o).exclude(subject_id=self.target.pk).exists():
            _fail("exam_link_requires_review")
        if (
            self.original
            and model("registrar.GroupElectiveChoice")
            .objects.filter(
                organization=self.org, group_id=o.group_id, period_id=o.period_id, chosen_subject_id=self.original
            )
            .exists()
        ):
            _fail("elective_choice_requires_review")

    def check_rows(self, row_id):
        o = self.offering
        Row = model("workload.TeachingTaskRow")
        self.row = None
        if row_id:
            self.row = (
                Row.objects.select_for_update(of=("self",))
                .select_related("task")
                .filter(pk=row_id, organization=self.org)
                .first()
            ) or _fail("row_not_found")
            groups = set(self.row.groups.values_list("pk", flat=True))
            if self.row.period_id != o.period_id or o.group_id not in groups:
                _fail("row_scope_mismatch")
            if groups != {o.group_id}:
                _fail("row_has_other_groups")
            if self.row.subject_id is None or str(self.row.subject_id) not in {self.original, str(self.target.pk)}:
                _fail("row_subject_mismatch")
        # Sinxron ləğv edilmiş sənədlərin sətirlərini oxumur (``offering_sync._foreign_rows``) — burada da.
        scope = Row.objects.filter(organization=self.org, period_id=o.period_id, groups=o.group_id).exclude(
            task__status="cancelled"
        )
        if self.row is not None:
            scope = scope.exclude(pk=self.row.pk)
        if self.original and scope.filter(subject_id=self.original).exists():
            # Köhnə fənndə qalan sətir növbəti sinxronda köhnə fənnin jurnalını YENİDƏN yaradardı.
            _fail("other_load_rows_on_old_subject" if self.row is not None else "load_row_required")
        if scope.filter(subject=self.target).exists():
            _fail("target_load_row_exists")

    def check_detach(self, syllabus_id):
        self.detach = None
        if not syllabus_id:
            return
        Syllabus, Share = model("syllabus.Syllabus"), model("syllabus.SyllabusShare")
        syllabus = (
            Syllabus.objects.select_for_update(of=("self",)).filter(pk=syllabus_id, organization=self.org).first()
        ) or _fail("detach_syllabus_not_found")
        share = Share.objects.filter(offering_id=self.offering.pk, syllabus=syllabus).first()
        if share is not None:
            self.detach = ("share", syllabus, share)
            return
        if syllabus.offering_id == self.offering.pk:
            if (
                Share.objects.filter(syllabus=syllabus).exists()
                or Syllabus.objects.filter(reused_from=syllabus).exists()
            ):
                _fail("detach_syllabus_in_use")
            if (
                syllabus.period_id
                and Syllabus.objects.filter(
                    organization=self.org, subject_id=syllabus.subject_id, period_id=syllabus.period_id
                )
                .filter(offering__isnull=True)
                .exclude(pk=syllabus.pk)
                .exists()
            ):
                _fail("detach_period_slot_taken")
            self.detach = ("own", syllabus, None)
            return
        if self.receipt.get("detached_syllabus") == str(syllabus.pk):
            self.counts["detach_already"] += 1
            return
        _fail("detach_syllabus_not_linked")

    def check_attach(self, syllabus_id):
        self.attach = None
        if not syllabus_id:
            return
        Syllabus, Share = model("syllabus.Syllabus"), model("syllabus.SyllabusShare")
        source = (
            Syllabus.objects.select_for_update(of=("self",))
            .select_related("offering")
            .filter(pk=syllabus_id, organization=self.org)
            .first()
        ) or _fail("attach_syllabus_not_found")
        if source.subject_id != self.target.pk:
            _fail("attach_syllabus_wrong_subject")
        if source.period_id != self.offering.period_id:
            _fail("attach_syllabus_wrong_period")
        if self.detach is not None and self.detach[1].pk == source.pk:
            _fail("attach_equals_detach")
        detaching = self.detach[1].pk if self.detach is not None else None
        current = Share.objects.filter(offering_id=self.offering.pk).values_list("syllabus_id", flat=True).first()
        if current is not None and current not in (source.pk, detaching):
            _fail("attach_offering_has_other_share")
        own = (
            Syllabus.objects.filter(organization=self.org, offering_id=self.offering.pk, is_active=True)
            .exclude(pk=detaching)
            .exists()
        )
        if own:
            _fail("attach_offering_has_own_syllabus")
        self.attach = source

    # ── yazı ──────────────────────────────────────────────────────────────
    def change_offering_subject(self):
        o = self.offering
        if o.subject_id == self.target.pk:
            self.counts["offering_already"] += 1
            return
        subject_merge_apply.allow_offering_subject_change([o.subject_id], self.target.pk)
        try:
            changed = (
                model("registrar.CourseOffering")
                .objects.filter(pk=o.pk, subject_id=o.subject_id)
                .update(subject_id=self.target.pk, updated_at=timezone.now())
            )
        finally:
            if not connection.needs_rollback:
                subject_merge_apply.clear_offering_subject_change()
        if changed != 1:
            _fail("offering_changed_concurrently")
        o.refresh_from_db()
        self.counts["offering_subject_changed"] += 1

    def apply_detach(self):
        if self.detach is None:
            return
        kind, syllabus, share = self.detach
        if kind == "share":
            log_action(
                AuditAction.DELETE,
                user=self.user,
                organization=self.org,
                resource_type="syllabus.share",
                resource_id=str(share.pk),
                resource_repr=f"{share.syllabus_id} → {share.offering_id}",
                old_values={
                    "syllabus": str(share.syllabus_id),
                    "offering": str(share.offering_id),
                    "source": share.source,
                },
                reason=REASON,
            )
            share.delete()
            self.counts["share_detached"] += 1
            return
        model("syllabus.Syllabus").objects.filter(pk=syllabus.pk).update(
            offering=None, is_active=False, updated_at=timezone.now()
        )
        self.counts["own_syllabus_detached"] += 1

    def apply_attach(self):
        if self.attach is None:
            return
        result = link_legacy_share(syllabus=self.attach, offering=self.offering, user=self.user)
        if result not in ("linked", "already"):
            _fail("attach_" + result)
        self.counts["share_attached" if result == "linked" else "attach_already"] += 1

    def apply_row(self):
        row = self.row
        if row is None:
            return None
        if row.subject_id == self.target.pk:
            self.counts["row_already"] += 1
            return None
        old = row.subject_id
        try:
            save_row_amended(
                task=row.task,
                row=row,
                actor=resolve_actor(self.user, self.org),
                data={"subject_id": str(self.target.pk), "subject_text": self.target.name},
                amend={
                    "reason": AmendmentReason.CORRECTION,
                    "note": "Jurnalın səhv fənn bağının düzəlişi — mövcud jurnal saxlanılır (fix_offering_subject)",
                },
                sync_offerings=True,
            )
        except WorkloadDenied as exc:
            _fail("row_edit_denied_" + str(exc.code).replace("workload.", "").replace(".", "_"))
        self.counts["row_subject_changed"] += 1
        return old


def _group_offering_ids(offering) -> list:
    return sorted(
        str(pk)
        for pk in model("registrar.CourseOffering")
        .objects.filter(
            organization_id=offering.organization_id, period_id=offering.period_id, group_id=offering.group_id
        )
        .values_list("pk", flat=True)
    )


@transaction.atomic
def fix_offering_subject(
    *,
    organization,
    user,
    offering_id,
    subject_id,
    detach_syllabus_id="",
    attach_syllabus_id="",
    row_id="",
    apply=False,
) -> dict:
    """Bax modul şərhi. ``apply=False`` — eyni yazılar icra olunur və GERİ QAYTARILIR (dəqiq dry-run)."""
    if not (user and user.is_active and user.is_superuser):
        _fail("active_superadmin_required")
    fix = _Fix(organization, user, offering_id, subject_id)
    fix.check_scope()
    fix.check_rows(row_id)
    fix.check_detach(detach_syllabus_id)
    fix.check_attach(attach_syllabus_id)
    offering = fix.offering
    before_protected = protected_hash(offering.pk)
    before_group = _group_offering_ids(offering)
    old_subject = offering.subject_id

    fix.change_offering_subject()
    fix.apply_detach()
    fix.apply_attach()
    old_row_subject = fix.apply_row()

    if protected_hash(offering.pk) != before_protected:
        _fail("academic_data_changed")
    if _group_offering_ids(offering) != before_group:
        _fail("sync_created_offering")  # sinxron yeni (boş) jurnal yaratdı — hamısı geri qaytarılır
    changed = sum(
        fix.counts[key]
        for key in (
            "offering_subject_changed",
            "share_detached",
            "own_syllabus_detached",
            "share_attached",
            "row_subject_changed",
        )
    )
    if changed:
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=organization,
            resource_type=RESOURCE,
            resource_id=str(offering.pk),
            resource_repr="Jurnalın fənn bağı (yerində düzəliş)",
            reason=REASON,
            old_values={
                "subject": str(old_subject),
                "row_subject": str(old_row_subject) if old_row_subject else None,
                "syllabus_link": (
                    {"kind": fix.detach[0], "syllabus": str(fix.detach[1].pk)} if fix.detach is not None else None
                ),
            },
            new_values={
                "offering": str(offering.pk),
                "old_subject": fix.original or None,
                "new_subject": str(fix.target.pk),
                "row": str(fix.row.pk) if fix.row is not None else None,
                "detached_syllabus": str(fix.detach[1].pk) if fix.detach is not None else None,
                "attached_syllabus": str(fix.attach.pk) if fix.attach is not None else None,
                "protected_hash": before_protected,
                "counts": dict(fix.counts),
            },
        )
    if not apply:
        transaction.set_rollback(True)
    return {**{key: int(value) for key, value in fix.counts.items()}, "changes": changed}


__all__ = ["OfferingSubjectFixError", "RESOURCE", "fix_offering_subject", "protected_hash"]
