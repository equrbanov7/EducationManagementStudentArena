"""Köhnə sistemin İNTENSİV / təkrar («fake») jurnalında keçilmiş fənnin RƏSMİ nəticəsini yeni sistemə yazmaq (2026-11-12).

Səbəb (MR-000288): köhnə sistemdə intensiv / təkrar tədris jurnalları ``journals.fake = 1`` idi — cutover onları
atdı (J-V6), 2026-09-25 bərpası (``legacy_repair_journal_enrollments``, «fake» kateqoriyası) isə YALNIZ o vaxt
«hazırda oxuyan» sayılan tələbələri geri gətirdi. Uzadılmış təhsildəki (qəbul ili köhnə) tələbə intensivdə fənni
keçsə də, yeni sistemdə yalnız əvvəlki «F» cəhdi qalıb — kabinetdə keçdiyi fənn kəsr görünür.

Plan (``intensive-results/1``, şifrəli release ilə gəlir; YALNIZ legacy id-ləri + rəqəmlər, ad/FİN yoxdur) lokal
qurulur: köhnə sistemin RƏSMİ bal vərəqləri (``balvereqi_logs``) SYS-1 tutuşdurucusu ilə (``official_entry_extract``)
— fake ailələr indeksdə saxlanılaraq — jurnal ailəsinə bağlanır; yalnız Yekun-u olan sətir, kollec yox, eyni
semestrdə eyni fənnin REAL jurnalında imtahanı olan tələbə yox (köhnə sistemin öz əkiz qaydası).

Sətir başına (hər biri öz savepoint-i; yarımçıq yazı qalmır):

1. tələbə — cutover ledger-i (``student``); aktiv üzvlüyü olmalıdır;
2. dövr / fənn — ledger (``academic_period`` / ``lesson_subject``), yoxdursa dövr adı / ``QKU-<id>`` kodu;
3. açılış — ledger (``course_offering``, ``uniqid:…``) və ya HƏMİN legacy jurnalın digər (artıq köçmüş)
   tələbələrinin həmin dövr + fənn üzrə yazılışı olan TƏK açılış (intensiv formatlı üstündür). Açılış YARADILMIR;
4. tələbənin həmin açılışda yazılışı varsa — toxunulmur (``skip_existing``); eyni dövrdə eyni fənnin BAŞQA
   açılışında yazılışı varsa — əkiz, toxunulmur; fənni hansısa dövrdə artıq KEÇİBSƏ — toxunulmur (kredit iki dəfə
   sayılmasın);
5. yazılış (``retake`` — əvvəl eyni fəndə cəhdi varsa, yoxsa ``mandatory``; açılışın qrupu tələbənin qrupu deyilsə
   ``source_group`` = öz qrupu, bağlı jurnala YALNIZ ƏLAVƏ), kollokvium xanaları (K1–K3, varsa), imtahan /
   25 % balı və giriş balı SYS-1-in öz yolu ilə (:func:`legacy_entry_alignment.align_archive_entries` — arxiv
   xanası, yaddaşda yoxlama, audit);
6. sonda yekun yenidən hesablanır: rəsmi Yekun-a (tam ədədə yuvarlaq) bərabər deyilsə və ya nəticə KEÇİD deyilsə
   sətir GERİ alınır (məqsəd: kabinetdə keçilmiş fənnin «F» görünməsi; kəsr cəhdi yeni sətir yaratmır).

Hər qaçışın ``batch`` id-si var (audit ``registrar.intensive_results_restore``); ``undo`` yalnız həmin qaçışın
yaratdığı yazılışları (dəyişməyibsə) silir — xanaları / yekunu ilə birlikdə.
"""

from __future__ import annotations

import secrets
import uuid
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

FORMAT = "intensive-results/1"
RESOURCE = "registrar.intensive_results_restore"
REASON = "Köhnə sistemin intensiv/təkrar jurnalının rəsmi bal vərəqi (MR-000288, 2026-11-12)"
UNDO_REASON = "Geri qaytarma: intensiv nəticələrinin bərpası (2026-11-12)"
ARCHIVE_NAME = "Davamiyyət və sərbəst iş (arxiv)"
LEDGER_SOURCES = ("myedu_mariadb", "myedu-repair")
SUBJECT_CODE_PREFIX = "QKU-"
MAX_ITEMS = 20000
SEASONS = ("Payız", "Yaz", "Yay")


def new_batch() -> str:
    return f"intensive-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        return None


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def validate_plan(data) -> list:
    """Planın forması; səhv olsa ``ValueError`` (kod)."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("intensive_results_format_unknown")
    items = data.get("items")
    if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
        raise ValueError("intensive_results_items_out_of_range")
    for item in items:
        if not isinstance(item, dict) or not item.get("journals") or not str(item.get("student") or "").isdigit():
            raise ValueError("intensive_results_item_invalid")
        if _decimal(item.get("total")) is None:
            raise ValueError("intensive_results_item_without_total")
    return items


class Ledger:
    """Cutover ledger-i (``legacy_import.LegacyEntityMap``, yalnız ``migrated``) — legacy id → hədəf pk."""

    def __init__(self, organization):
        self.organization = organization
        self.model = _model("LegacyEntityMap", "legacy_import")

    def _rows(self, entity_type, keys=None):
        queryset = self.model.objects.filter(
            organization=self.organization,
            source_system__in=LEDGER_SOURCES,
            entity_type=entity_type,
            state="migrated",
        )
        if keys is not None:
            keys = sorted({str(key) for key in keys})
            out = {}
            for start in range(0, len(keys), 5000):
                out.update(
                    queryset.filter(legacy_pk__in=keys[start : start + 5000]).values_list("legacy_pk", "target_pk")
                )
            return out
        return dict(queryset.values_list("legacy_pk", "target_pk"))

    def students(self, legacy_ids) -> dict:
        return {int(k): _uuid(v) or v for k, v in self._rows("student", legacy_ids).items() if str(k).isdigit()}

    def offerings_by_journal(self, uniqids) -> dict:
        wanted = set(uniqids)
        out: dict = defaultdict(set)
        for key, target in self._rows("course_offering").items():
            uniqid = str(key).partition(":")[0]
            if uniqid in wanted and _uuid(target):
                out[uniqid].add(_uuid(target))
        return out


class Resolver:
    """Dövr, fənn, açılış və tələbənin yeni sistemdəki qarşılığı (yalnız oxu)."""

    def __init__(self, organization, plan: dict, items: list):
        self.organization = organization
        self.ledger = Ledger(organization)
        self.legacy_periods = {int(row["id"]): row for row in plan.get("periods") or []}
        self.legacy_subjects = {int(row["id"]): row for row in plan.get("subjects") or []}
        legacy_students = {int(item["student"]) for item in items}
        legacy_students |= {int(s) for item in items for s in item.get("siblings") or [] if str(s).isdigit()}
        self.users = self.ledger.students(legacy_students)
        self.by_journal = self.ledger.offerings_by_journal({uq for item in items for uq in item["journals"]})
        led_period = self.ledger._rows("academic_period", self.legacy_periods)
        led_subject = self.ledger._rows("lesson_subject", self.legacy_subjects)
        AcademicPeriod = _model("AcademicPeriod", "organizations")
        Subject = _model("Subject")
        self.periods = {}
        for legacy_id, row in self.legacy_periods.items():
            period = None
            target = _uuid(led_period.get(str(legacy_id)))
            if target:
                period = AcademicPeriod.objects.filter(organization=organization, pk=target).first()
            if period is None:
                name = str(row.get("name") or "")
                year = name.split()[0] if name else ""
                season = next((s for s in SEASONS if s in name), "")
                period = (
                    AcademicPeriod.objects.filter(organization=organization, name=season, academic_year=year).first()
                    if season and year
                    else None
                )
            self.periods[legacy_id] = period
        self.subjects = {}
        for legacy_id in self.legacy_subjects:
            subject = None
            target = _uuid(led_subject.get(str(legacy_id)))
            if target:
                subject = Subject.objects.filter(organization=organization, pk=target).first()
            if subject is None:
                subject = Subject.objects.filter(
                    organization=organization, code__iexact=f"{SUBJECT_CODE_PREFIX}{legacy_id}"
                ).first()
            self.subjects[legacy_id] = subject

    def offering_for(self, item, period, subject):
        """``(açılış, kod)`` — ledger → bacı tələbələr; açılış YARADILMIR."""
        CourseOffering = _model("CourseOffering")
        Enrollment = _model("Enrollment")
        base = CourseOffering.objects.filter(
            organization=self.organization, period=period, subject=subject, is_active=True
        )
        ledger_ids = set()
        for uniqid in item["journals"]:
            ledger_ids |= self.by_journal.get(uniqid, set())
        if ledger_ids:
            found = list(base.filter(pk__in=ledger_ids))
            if len(found) == 1:
                return found[0], "ledger"
            if len(found) > 1:
                return None, "offering_ambiguous"
        siblings = [self.users[int(s)] for s in item.get("siblings") or [] if int(s) in self.users]
        if not siblings:
            return None, "offering_no_sibling"
        counts = Counter(
            Enrollment.objects.filter(
                organization=self.organization,
                student_id__in=siblings,
                offering__in=base,
            )
            .exclude(status="dropped")
            .values_list("offering_id", flat=True)
        )
        if not counts:
            return None, "offering_unresolved"
        offerings = {o.pk: o for o in base.filter(pk__in=list(counts))}
        intensive = [pk for pk in counts if getattr(offerings[pk], "course_format", "") == "intensive"]
        pool = intensive or list(counts)
        best = max(counts[pk] for pk in pool)
        top = [pk for pk in pool if counts[pk] == best]
        if len(top) != 1:
            return None, "offering_ambiguous"
        return offerings[top[0]], "siblings"


def _active_member(organization, user_id) -> bool:
    Membership = _model("Membership", "organizations")
    return Membership.objects.filter(
        organization=organization, user_id=user_id, is_active=True, role__is_active=True, user__is_active=True
    ).exists()


def _home_group(organization, user_id):
    Record = _model("StudentAcademicRecord")
    record = (
        Record.objects.filter(organization=organization, student_id=user_id, group__isnull=False)
        .order_by("-is_active", "-updated_at")
        .first()
    )
    return record.group_id if record else None


def _kollokvium(enrollment, values: dict) -> int:
    from .models import AssessmentComponent, ComponentKind, ComponentScore

    written = 0
    components = list(
        AssessmentComponent.objects.filter(offering_id=enrollment.offering_id, kind=ComponentKind.KOLLOKVIUM)
    )
    for component in components:
        digit = next((ch for ch in reversed(component.name) if ch.isdigit()), "")
        score = _decimal((values or {}).get(f"k{digit}")) if digit else None
        if score is None or not Decimal("0") <= score <= Decimal(component.max_score):
            continue
        ComponentScore.objects.create(
            organization=enrollment.organization, component=component, enrollment=enrollment, score=score
        )
        written += 1
    return written


def _restore_one(*, organization, actor, item, offering, user_id, kind, counts):
    """Bir sətir (çağıranın savepoint-ində). Uğursuzluqda ``RuntimeError(kod)`` — savepoint geri alınır."""
    from . import finals, gradebook
    from .legacy_entry_alignment import EntryTarget, align_archive_entries
    from .models import Enrollment

    home = _home_group(organization, user_id)
    guest = home is not None and home != offering.group_id
    enrollment = Enrollment.objects.create(
        organization=organization,
        student_id=user_id,
        offering=offering,
        kind=kind,
        status=Enrollment.Status.ENROLLED,
        source_group_id=home if guest else None,
        added_by=actor if guest else None,
        added_at=timezone.now() if guest else None,
    )
    if _kollokvium(enrollment, item.get("k")):
        counts["kollokvium_rows"] += 1
    exam, resit, total = _decimal(item.get("exam")), _decimal(item.get("resit")), _decimal(item.get("total"))
    if resit is not None and resit == 0:
        resit = None  # köhnə vərəqdə «T.imtahan = 0» = təkrar imtahan yoxdur
    qb_fail = bool(item.get("attendance_fail")) and exam is None and resit is None
    target = EntryTarget(entry=_decimal(item.get("entry")), total=total, exam=exam, resit=resit, qb_fail=qb_fail)
    rows = align_archive_entries(
        organization=organization,
        actor=actor,
        targets={enrollment.pk: target},
        archive_name=ARCHIVE_NAME,
        reason=REASON,
    )
    outcome = rows[0].outcome if rows else "no_row"
    if outcome not in ("written", "same", "no_entry"):
        raise RuntimeError(outcome)
    enrollment = Enrollment.objects.select_related("offering", "student").get(pk=enrollment.pk)
    result = finals.compute_final_result(enrollment=enrollment, organization=organization)
    if result["total"] is None or Decimal(result["total"]) != gradebook.round_score(total):
        raise RuntimeError("total_mismatch")
    if not result["passed"]:
        raise RuntimeError("official_not_passed")  # yalnız keçid bərpa olunur — kəsr cəhdi sətir artırmır
    return {
        "enrollment": str(enrollment.pk),
        "offering": str(offering.pk),
        "student": str(user_id),
        "total": str(result["total"]),
        "export": item.get("export"),
    }


def _name_key(text) -> str:
    return " ".join(str(text or "").casefold().split())


def _already_passed(organization, user_id, subject) -> bool:
    """Tələbə bu fənni (eyni kart və ya eyni ad) hansısa dövrdə artıq KEÇİB — yazı lazım deyil (kredit iki dəfə
    sayılmasın; köhnə intensiv nəticəsi əvvəlki bərpa ilə başqa sətrə düşmüş ola bilər)."""
    from . import finals

    Enrollment = _model("Enrollment")
    key = _name_key(subject.name)
    for enrollment in (
        Enrollment.objects.filter(organization=organization, student_id=user_id)
        .exclude(status="dropped")
        .select_related("offering__subject", "offering__period", "student")
    ):
        if enrollment.offering.subject_id != subject.pk and _name_key(enrollment.offering.subject.name) != key:
            continue
        if finals.compute_final_result(enrollment=enrollment, organization=organization)["passed"]:
            return True
    return False


def _prior_attempt(organization, user_id, subject, period) -> bool:
    Enrollment = _model("Enrollment")
    return (
        Enrollment.objects.filter(organization=organization, student_id=user_id, offering__subject=subject)
        .exclude(offering__period=period)
        .filter(offering__period__start_date__lt=period.start_date)
        .exists()
    )


def run(*, organization, actor, plan, counts, batch=None, only_students=None) -> str:
    """Planı tətbiq et (çağıranın tranzaksiyasında; dry-run onu geri qaytarır). ``batch`` id-sini qaytarır."""
    from .models import Enrollment, EnrollmentKind

    batch = batch or new_batch()
    items = validate_plan(plan)
    if only_students:
        items = [item for item in items if int(item["student"]) in only_students]
    resolver = Resolver(organization, plan, items)
    counts["items"] += len(items)
    manifest = []
    seen = set()
    for item in items:
        period = resolver.periods.get(int(item.get("semestr") or 0))
        subject = resolver.subjects.get(int(item.get("lesson_id") or 0))
        if period is None or subject is None:
            counts["skip_reference_unresolved"] += 1
            continue
        user_id = resolver.users.get(int(item["student"]))
        if user_id is None:
            counts["skip_student_unresolved"] += 1
            continue
        offering, how = resolver.offering_for(item, period, subject)
        if offering is None:
            counts[f"skip_{how}"] += 1
            continue
        counts[f"offering_by_{how}"] += 1
        if (offering.pk, user_id) in seen:
            counts["skip_duplicate_item"] += 1
            continue
        seen.add((offering.pk, user_id))
        same = Enrollment.objects.filter(organization=organization, student_id=user_id, offering__period=period)
        if same.filter(offering=offering).exists():
            counts["skip_existing"] += 1
            continue
        if same.exclude(status="dropped").filter(offering__subject=subject).exists():
            counts["skip_twin_same_period"] += 1
            continue
        if not _active_member(organization, user_id):
            counts["skip_student_not_enrollable"] += 1
            continue
        if _already_passed(organization, user_id, subject):
            counts["skip_already_passed"] += 1
            continue
        kind = (
            EnrollmentKind.RETAKE
            if _prior_attempt(organization, user_id, subject, period)
            else EnrollmentKind.MANDATORY
        )
        try:
            with transaction.atomic():
                manifest.append(
                    _restore_one(
                        organization=organization,
                        actor=actor,
                        item=item,
                        offering=offering,
                        user_id=user_id,
                        kind=kind,
                        counts=counts,
                    )
                )
        except RuntimeError as exc:
            counts["skip_" + str(exc).removeprefix("skip_")] += 1
            continue
        counts["restored"] += 1
        counts[f"restored_{kind}"] += 1
    counts["offerings_touched"] += len({row["offering"] for row in manifest})
    if manifest:
        log_action(
            AuditAction.CREATE,
            user=actor,
            organization=organization,
            new_values={"enrollments": len(manifest)},
            changes={"created": manifest},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=batch,
        )
    return batch


def undo(*, organization, actor, counts, batch) -> None:
    """Yalnız ``batch`` qaçışının yaratdığı yazılışları sil (sonradan dəyişməyibsə)."""
    from core.rls import journal_unlock

    from . import finals

    AuditLog, Enrollment = _model("AuditLog", "audit"), _model("Enrollment")
    rows = list(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON, resource_id=batch)
    )
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        for item in (row.changes or {}).get("created") or []:
            enrollment = (
                Enrollment.objects.select_related("offering", "student").filter(pk=_uuid(item["enrollment"])).first()
            )
            if enrollment is None:
                counts["undo_missing"] += 1
                continue
            result = finals.compute_final_result(enrollment=enrollment, organization=organization)
            if str(result["total"]) != str(item["total"]) or enrollment.status != Enrollment.Status.ENROLLED:
                counts["undo_changed_kept"] += 1
                continue
            with journal_unlock(local=True):
                enrollment.delete()
            counts["undo_enrollment_deleted"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"undo": True},
        reason=UNDO_REASON,
        resource_type=RESOURCE,
        resource_id=batch,
    )


__all__ = ["FORMAT", "REASON", "RESOURCE", "new_batch", "run", "undo", "validate_plan"]
