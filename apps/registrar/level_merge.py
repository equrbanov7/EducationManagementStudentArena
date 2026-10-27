"""Səviyyə jurnalı birləşməsi — köhnə sistemin bir səviyyə jurnalının qruplara bölünmüş tələbələri bir «ev» jurnalına
qonaq kimi (sahib 2026-10-27; ``merge_level_journals``).

Köhnə sistemdə «Xarici dildə … -1(intermediate)» jurnalı bir neçə qrupun həmin səviyyədəki tələbələrini bir müəllimdə
birləşdirirdi; yeni sistemdə hər qrupun öz jurnalı var və eyni dərs 2–5 jurnalda təkrarlanır. Plan (lokal,
``build_journal_share_plans`` → ``levelmerge.json``, YALNIZ id-lər)::

    {"format": "level-merge/1", "period": uuid, "journals": [{"legacy_journal": int, "teacher": int, "host": uuid,
      "via": "owner" | "share", "moves": [{"enrollment": uuid, "student": int}]}]}

Mexanizm «alt qrup birləşməsi» ilə EYNİDİR (:mod:`.guest_merge`): evdə tələbəyə qonaq qeydiyyatı (fərqli qrup →
``source_group``), xanalar evin EYNİ tarix + saatdakı dərsinə YENİ sətir kimi (``created_at`` köhnəsi — redaktə
pəncərəsi açılmır), mənbə qeydiyyat ``dropped`` + ``superseded_by`` (heç nə silinmir; boşalan mənbə jurnal mövcud
«Jurnal təmizliyi» axınına qalır). Hər şey kilid altında yenidən yoxlanılır:

* ev: plan dövrü cari, aktiv, bağlı deyil, eyni fənn; ``via=owner`` → sahibi hələ də planın müəllimidir,
  ``via=share`` → müəllimin aktiv payı var (köçənlər həmin paya əlavə olunur);
* tələbə ÜZRƏ hamısı-ya-heç: rəsmi düzəlişli xana, evdə uyğun dərsi olmayan xana, eyni ev dərsinə iki xana, yekun /
  komponent balı, bağlı mənbə, evdə artıq sətir — tələbə köçürülmür və SAYILIR (münaqişə saxlanılır);
* uyğunluq: eyni tarix + başlanğıc saatı; yoxdursa həmin tarixdə hər iki tərəfdə TƏK dərs varsa — o;
* evin sahibinin (``via=owner``) sətir-məhdud aktiv payı varsa köçənlər ona əlavə olunur; müəllimin mənbə açılışdakı
  sətir-məhdud payında ``enrolled`` sətir qalmırsa pay söndürülür (açılışın SAHİBİ deyilsə — paysız sahib hamını
  görərdi);
* hər jurnal üçün BİR audit sətri (``registrar.level_merge``, ``<paket>:<legacy jurnal>``): köçən tələbələr (mənbə,
  ev qeydiyyatı, yaradılıbmı, ``[yeni xana, köhnə dərs]``), paya əlavələr, söndürülən paylar — ``--undo`` onunla
  dəqiq geri qaytarır (:mod:`.level_merge_undo`).

İdempotentdir: ikinci qaçışda mənbə artıq ``dropped`` → ``already_moved``.
"""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.http_ids import parse_uuid

from . import guest_merge
from .models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark, StudentAcademicRecord
from .twin_relocate import closed, copy_mark, corrected_mark_ids, has_scores, recompute_absences

FORMAT = "level-merge/1"
BATCH_RESOURCE = "registrar.level_merge"
REASON = (
    "Səviyyə jurnalı birləşməsi: köhnə sistemin bir səviyyə jurnalı yeni sistemdə qruplara bölünmüşdü — "
    "tələbə müəllimin ev jurnalına qonaq kimi (sahib 2026-10-27, merge_level_journals)"
)


class LevelMergeError(Exception):
    """Plan / dövr səhvi (kod — stdout-a yalnız bu çıxır)."""


def new_batch() -> str:
    return f"lvlmerge-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def check_period(organization, plan: dict):
    from django.apps import apps as django_apps

    period_model = django_apps.get_model("organizations", "AcademicPeriod")
    period_id = parse_uuid(plan.get("period"))
    period = period_model.objects.filter(organization=organization, pk=period_id).first() if period_id else None
    if period is None:
        raise LevelMergeError("period_not_found")
    if not period.is_current:
        raise LevelMergeError("period_not_current")
    return period


def _locked(offering) -> bool:
    from .gradebook import journal_is_locked

    return journal_is_locked(offering)


def _slot_index(lessons) -> tuple[dict, dict]:
    exact, by_day = {}, defaultdict(list)
    for lesson in lessons:
        exact.setdefault((lesson.date, lesson.start_time), lesson)
        by_day[lesson.date].append(lesson)
    return exact, by_day


class Merger:
    def __init__(self, *, organization, actor, batch: str, counts: Counter):
        self.organization = organization
        self.actor = actor
        self.batch = batch
        self.counts = counts

    def run(self, plan: dict) -> None:
        period = check_period(self.organization, plan)
        for item in plan.get("journals") or []:
            self.counts["journals_in_file"] += 1
            try:
                with transaction.atomic():
                    self._journal(item if isinstance(item, dict) else {}, period)
            except IntegrityError:
                self.counts["journal_integrity_error"] += 1

    # ── jurnal ───────────────────────────────────────────────────────────
    def _journal(self, item: dict, period) -> None:
        counts = self.counts
        host = (
            CourseOffering.objects.select_for_update(of=("self",))
            .filter(organization=self.organization, pk=parse_uuid(item.get("host")), period=period)
            .first()
        )
        teacher_id = item.get("teacher")
        if host is None or not host.is_active:
            counts["host_missing"] += 1
            return
        if closed([host.pk]) or _locked(host):
            counts["host_closed"] += 1
            return
        share = None
        if item.get("via") == "share":
            share = JournalShare.objects.filter(offering=host, teacher_id=teacher_id, is_active=True).first()
            if share is None:
                counts["host_teacher_no_share"] += 1
                return
        elif host.instructor_id != teacher_id:
            counts["host_owner_changed"] += 1
            return
        else:
            share = JournalShare.objects.filter(offering=host, teacher_id=teacher_id, is_active=True).first()
        exact, by_day = _slot_index(Lesson.objects.filter(offering=host))
        manifest = {"journal": item.get("legacy_journal"), "host": str(host.pk), "students": [], "share_added": {}}
        manifest["shares_deactivated"] = []
        moved_sources = defaultdict(list)
        for move in item.get("moves") or []:
            self.counts["moves_in_file"] += 1
            try:
                with transaction.atomic():
                    row = self._student(move if isinstance(move, dict) else {}, host, exact, by_day)
            except (ValidationError, IntegrityError):
                self.counts["kept_validation_error"] += 1
                row = None
            if row is not None:
                manifest["students"].append(row)
                moved_sources[row["source_offering"]].append(row["source"])
        if not manifest["students"]:
            counts["journals_nothing_moved"] += 1
            return
        self._extend_share(share, manifest)
        self._retire_source_shares(teacher_id, moved_sources, manifest)
        counts["journals_merged"] += 1
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            obj=host,
            new_values=manifest,
            reason=f"merge_level_journals {self.batch} — {REASON}",
            resource_type=BATCH_RESOURCE,
            resource_id=f"{self.batch}:{item.get('legacy_journal')}",
            resource_repr=self.batch,
        )

    def _extend_share(self, share, manifest) -> None:
        """Müəllimin evdəki sətir-məhdud payına köçənləri əlavə et (boş siyahı = hamısı — toxunulmur)."""
        if share is None or not share.enrollments.exists():
            return
        added = [row["host_enrollment"] for row in manifest["students"]]
        share.enrollments.add(*added)
        manifest["share_added"] = {str(share.pk): added}
        self.counts["share_rows_added"] += len(added)

    def _retire_source_shares(self, teacher_id, moved_sources: dict, manifest) -> None:
        """Mənbə açılışda müəllimin sətir-məhdud payında aktiv sətir qalmırsa — pay söndürülür.

        Açılışın SAHİBİNİN payı söndürülmür: paysız sahib TAM görür — başqa müəllimlərin orada qalan tələbələri ona
        açılardı (yerli sınaq 2026-10-27: 18 açılış / 163 sətir). Boşalmış siyahılı pay sahibə yalnız heç bir payın
        örtmədiyi sətirləri göstərir."""
        for share in (
            JournalShare.objects.filter(offering_id__in=list(moved_sources), teacher_id=teacher_id, is_active=True)
            .exclude(offering__instructor_id=teacher_id)
            .prefetch_related("enrollments")
        ):
            rows = list(share.enrollments.all())
            if not rows or any(row.status == Enrollment.Status.ENROLLED for row in rows):
                continue
            share.is_active = False
            share.save(update_fields=["is_active", "updated_at"])
            manifest["shares_deactivated"].append(str(share.pk))
            self.counts["source_shares_deactivated"] += 1

    # ── tələbə (hamısı-ya-heç) ───────────────────────────────────────────
    def _student(self, move: dict, host, exact, by_day):
        counts = self.counts
        source = (
            Enrollment.objects.select_for_update(of=("self",))
            .select_related("offering")
            .filter(organization=self.organization, pk=parse_uuid(move.get("enrollment")))
            .first()
        )
        if source is None or source.student_id != move.get("student"):
            counts["source_missing"] += 1
            return None
        if source.status != Enrollment.Status.ENROLLED:
            target = source.superseded_by
            counts[
                "already_moved" if target is not None and target.offering_id == host.pk else "source_not_enrolled"
            ] += 1
            return None
        offering = source.offering
        if offering.pk == host.pk:
            counts["source_is_host"] += 1
            return None
        if offering.subject_id != host.subject_id or offering.period_id != host.period_id:
            counts["subject_mismatch"] += 1
            return None
        if closed([offering.pk]) or _locked(offering):
            counts["kept_source_closed"] += 1
            return None
        if has_scores([source.pk]):
            counts["kept_has_scores"] += 1
            return None
        if Enrollment.objects.filter(student_id=source.student_id, offering=host).exists():
            counts["kept_host_row_exists"] += 1
            return None
        pairs = self._pairs(source, exact, by_day)
        if pairs is None:
            return None
        enrollment = self._guest(source, host)
        if enrollment is None:
            return None
        marks = []
        for mark, lesson in pairs:
            created = copy_mark(mark, lesson=lesson, enrollment=enrollment)
            marks.append([str(created.pk), str(mark.lesson_id)])
            mark.delete()
        guest_merge.release_source(source=source, target=enrollment, by_user=self.actor, reason=REASON)
        recompute_absences([enrollment, source])
        counts["students_moved"] += 1
        counts["marks_moved"] += len(marks)
        return {
            "source": str(source.pk),
            "source_offering": str(offering.pk),
            "host_enrollment": str(enrollment.pk),
            "marks": marks,
        }

    def _pairs(self, source, exact, by_day):
        """``[(xana, ev dərsi)]`` və ya ``None`` (tələbə saxlanılır — səbəb sayılır)."""
        counts = self.counts
        marks = list(
            LessonMark.objects.select_for_update(of=("self",)).select_related("lesson").filter(enrollment=source)
        )
        if corrected_mark_ids([mark.pk for mark in marks]):
            counts["kept_corrected_mark"] += 1
            return None
        source_days = Counter(mark.lesson.date for mark in marks)
        pairs, by_date, missing = [], 0, 0
        for mark in marks:
            lesson = exact.get((mark.lesson.date, mark.lesson.start_time))
            if lesson is None and source_days[mark.lesson.date] == 1 and len(by_day.get(mark.lesson.date, ())) == 1:
                lesson = by_day[mark.lesson.date][0]
                by_date += 1
            if lesson is None:
                missing += 1
            else:
                pairs.append((mark, lesson))
        if missing:
            counts["kept_no_host_lesson"] += 1
            counts["kept_marks_no_host_lesson"] += missing
            return None
        if len({lesson.pk for _mark, lesson in pairs}) != len(pairs):
            counts["kept_host_lesson_clash"] += 1
            return None
        counts["marks_matched_by_date"] += by_date
        return pairs

    def _guest(self, source, host):
        group_id = (
            StudentAcademicRecord.objects.filter(
                organization=self.organization, student_id=source.student_id, is_active=True
            )
            .values_list("group_id", flat=True)
            .first()
        )
        guest = group_id is not None and group_id != host.group_id
        try:
            with transaction.atomic():
                created = Enrollment.objects.create(
                    organization=self.organization,
                    student_id=source.student_id,
                    offering=host,
                    kind=source.kind,
                    status=Enrollment.Status.ENROLLED,
                    source_group_id=group_id if guest else None,
                    added_by=self.actor if guest else None,
                    added_at=timezone.now() if guest else None,
                )
        except IntegrityError:
            self.counts["kept_host_row_blocked"] += 1
            return None
        self.counts["guest_rows_created"] += 1
        return created


__all__ = ["BATCH_RESOURCE", "FORMAT", "LevelMergeError", "Merger", "REASON", "check_period", "new_batch"]
