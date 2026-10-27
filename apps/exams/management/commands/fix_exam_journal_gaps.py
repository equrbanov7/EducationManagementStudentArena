"""İmtahan qruplarının «jurnalı yoxdur» boşluğu — səbəb hesabatı + YALNIZ-DOLDURMA düzəlişi (sahib 2026-10-27).

Sahib: «Bu imtahan təyin etdiklərim var … bəzilərini deyir ki jurnalı yoxdur — o qrupların o hissəsini həll et».
Hər balı jurnala yazılan (final / midterm) fənnli imtahanın HƏR reyestr qrupu üçün sehrbazın yoxlaması
(``registrar.exam_journal_link.group_subject_coverage``) yenidən hesablanır və əhatəsiz tələbələr səbəbə görə
ayrılır (``registrar.exam_journal_gaps``). Bu əmr YALNIZ ``roster_gap``-i düzəldir — qrupun bu fəndən jurnalı
var, tələbə qrupa jurnal dolduqdan SONRA gəlib: tələbə açılışın yaradılmasındakı EYNİ yolla
(``registrar.services.enroll_group_students``) jurnala yazılır. Sonra imtahanın jurnal bağlantısı yenilənir və
bitmiş rəsmi midterm cəhdləri yeni jurnallara yazılır (``exam_journal_link.resync_exam_journal`` — canlı
körpünün eyni qaydaları, bildiriş GETMİR). Qalan səbəblər üçün mövcud əmr göstərilir (heç nə yazılmır).

Təhlükəsizlik (nəzarətsiz prod icrası üçün):

* DEFOLT DRY-RUN — eyni kod tranzaksiyada işləyir və sonda geri qaytarılır (saylar dəqiqdir);
* yalnız ƏLAVƏ: heç bir qeydiyyat silinmir / dəyişmir, ``dropped`` sətri bərpa olunmur, bağlı jurnal və siyahıya
  bağlı dövr toxunulmur, başqa jurnalda aktiv qeydiyyatı olan tələbə ötürülür;
* idempotent: ikinci qaçış ``roster_gap 0`` / ``enroll_created 0`` verir;
* stdout-a YALNIZ saylar və id / kodlar (imtahan id-si, fənn kodu, qrup kodu) — şəxs adı YOX.

    manage.py fix_exam_journal_gaps --org qku --actor <superadmin>                 # DRY-RUN
    manage.py fix_exam_journal_gaps --org qku --actor <superadmin> --exam 62 --apply
    manage.py fix_exam_journal_gaps --org qku --actor <superadmin> --since 2026-10-24 --apply
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.models import Exam
from apps.exams.services import exam_journal_link
from apps.exams.services.exam_journal_coverage import JOURNAL_CATEGORIES
from apps.organizations.models import Organization
from apps.registrar.public import exam_journal_gaps
from apps.registrar.public import exam_journal_link as registrar_link
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "exam_journal_gaps:"
#: Səbəb → onu həll edən mövcud yol (bu əmr yazmır).
HINTS = {
    exam_journal_gaps.DROPPED: "qəsdən çıxarılıb (səviyyə / köçürmə) — dəyişmir",
    exam_journal_gaps.SUBGROUP_UNPLACED: "place_parent_group_students",
    exam_journal_gaps.OTHER_JOURNAL: "əl ilə qərar (jurnal ailənin başqa qrupundadır)",
    exam_journal_gaps.TASK_ROW: "resync_task_offerings",
    exam_journal_gaps.VARIANT_SUBJECT: "imtahanı həmin kartla yaradın və ya merge_subjects / merge_twin_offerings",
    exam_journal_gaps.NO_JOURNAL: "qrupun bu fəndən yükü yoxdur — tədris şöbəsi",
}


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


def _exam_filter(values) -> Q:
    query = Q()
    for value in values:
        value = str(value).strip()
        query |= Q(slug=value)
        if value.isdigit():
            query |= Q(pk=int(value))
    return query


def _since(value):
    try:
        day = datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise CommandError("bad_since (YYYY-MM-DD)") from exc
    return timezone.make_aware(datetime.combine(day, time.min))


class Command(BaseCommand):
    help = "İmtahan qruplarının jurnal boşluğu: səbəb hesabatı + qrupa sonradan gəlmiş tələbəni jurnala yaz (dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--exam", action="append", default=[], help="yalnız bu imtahan (id / slug); təkrar")
        parser.add_argument("--since", default="", help="yalnız bu tarixdən (YYYY-MM-DD) yaradılmış imtahanlar")
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        self.totals: Counter = Counter()
        self.reasons: Counter = Counter()
        self.reason_groups: Counter = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("organization_not_found")
            actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
            if actor is None or not actor.is_superuser:
                raise CommandError("actor_must_be_active_superuser")
            period = registrar_link.current_period(organization)
            if period is None:
                raise CommandError("current_period_missing")
            try:
                with transaction.atomic():
                    for exam in self._exams(organization, period, options):
                        self._exam(organization, period, exam, actor)
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
        mode = "APPLY" if apply else "DRY-RUN (heç nə yazılmadı — yazmaq üçün --apply)"
        reasons = " ".join(f"{key}={self.reasons[key]}" for key in exam_journal_gaps.REASONS)
        groups = " ".join(f"{key}={self.reason_groups[key]}" for key in exam_journal_gaps.REASONS)
        totals = " ".join(f"{key}={value}" for key, value in sorted(self.totals.items()))
        self.stdout.write(f"{PREFIX} {mode}")
        self.stdout.write(f"{PREFIX} students_by_reason {reasons}")
        self.stdout.write(f"{PREFIX} groups_by_reason {groups}")
        self.stdout.write(f"{PREFIX} totals {totals}")

    def _exams(self, organization, period, options) -> list:
        exams = Exam.objects.filter(
            organization=organization,
            is_deleted=False,
            subject__isnull=False,
            exam_type_extended__in=sorted(JOURNAL_CATEGORIES),
            allowed_units__isnull=False,
        ).distinct()
        if options["exam"]:
            exams = exams.filter(_exam_filter(options["exam"]))
        elif options["since"]:
            exams = exams.filter(created_at__gte=_since(options["since"]))
        else:
            exams = exams.filter(created_at__date__gte=period.start_date)
        found = list(exams.select_related("organization", "subject", "journal_teacher").order_by("pk"))
        if options["exam"] and not found:
            raise CommandError("exam_not_found")
        return found

    def _exam(self, organization, period, exam, actor) -> None:
        self.totals["exams"] += 1
        units = {unit.pk: unit.name for unit in exam.allowed_units.all()}
        gaps = exam_journal_gaps.classify(organization, exam.subject_id, list(units), period=period)
        fill: set = set()
        gap_units = 0
        for unit_id, gap in sorted(gaps.items(), key=lambda item: units.get(item[0], "")):
            self.totals["units"] += 1
            if not gap.uncovered:
                continue
            gap_units += 1
            self.reasons.update(gap.reasons)
            self.reason_groups[gap.reason] += 1
            fill |= gap.fill_offering_ids
            parts = " ".join(f"{key}={gap.reasons[key]}" for key in exam_journal_gaps.REASONS if gap.reasons[key])
            hint = HINTS.get(gap.reason, "fill_rosters")
            variants = f" variant_codes={','.join(sorted(gap.variant_codes))}" if gap.variant_codes else ""
            self.stdout.write(
                f"{PREFIX}   exam={exam.pk} unit={units.get(unit_id, unit_id)} students={gap.students} "
                f"uncovered={gap.uncovered} has_journal={int(gap.has_journal)} {parts}{variants} → {hint}"
            )
        self.totals["units_with_gap"] += gap_units
        filled: Counter = exam_journal_gaps.fill_rosters(fill, by_user=actor) if fill else Counter()
        self.totals.update(filled)
        old_ids, new_ids = exam_journal_link.refresh_links(exam)
        relinked = old_ids != new_ids
        self.totals["exams_relinked"] += int(relinked)
        written = int(filled.get("enroll_created", 0)) + int(filled.get("enroll_guest_added", 0))
        finished = exam.attempts.filter(status__in=ATTEMPT_FINISHED_STATUSES, is_trial=False).exists()
        resync: Counter = Counter()
        if finished and (written or relinked):
            with transaction.atomic():
                resync = exam_journal_link.resync_exam_journal(exam, notify=False, by_user=actor)
            self.totals["exams_resynced"] += 1
            self.totals.update({f"midterm_{key}": int(value) for key, value in resync.items()})
        self.stdout.write(
            f"{PREFIX} exam={exam.pk} category={exam.exam_type_extended} subject={exam.subject.code} "
            f"units={len(units)} units_with_gap={gap_units} enrolled={written} relinked={int(relinked)} "
            f"resync={dict(sorted(resync.items())) or '-'}"
        )
