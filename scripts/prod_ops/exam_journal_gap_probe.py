"""İmtahan qruplarının «jurnalı yoxdur» boşluğu — YALNIZ-OXU prob (sahib 2026-10-27).

`manage.py shell`-ə STDIN ilə ötürülür (bax prod-exam-ops.yml). Heç nə YAZMIR və şəxs adı çap etmir — yalnız
imtahan id-si, fənn kodu, reyestr qrupunun kodu və saylar.

Sehrbazın qrup yoxlaması (``registrar.exam_journal_link.group_subject_coverage``) cari dövrdə balı jurnala yazılan
(final / midterm) fənnli HƏR imtahanın HƏR qrupu üçün yenidən hesablanır. Deploy olunmuş image-də
``registrar.exam_journal_gaps`` varsa əhatəsiz tələbələr səbəbə görə də ayrılır (``fix_exam_journal_gaps`` əmrinin
EYNİ təsnifatı); yoxdursa yalnız saylar. ``new=1`` — prod nüsxəsindən (2026-10-27 01:10 Bakı) SONRA yaradılmış.
"""

import os
from collections import Counter
from datetime import datetime
from datetime import timezone as dt_timezone

from apps.exams.models import Exam
from apps.organizations.models import Organization
from apps.registrar.public import exam_journal_link
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

try:
    from apps.registrar.public import exam_journal_gaps
except ImportError:  # köhnə image — təsnifatsız
    exam_journal_gaps = None

SNAPSHOT_UTC = datetime(2026, 10, 26, 21, 10, tzinfo=dt_timezone.utc)
ORG_SLUG = (os.environ.get("PROBE_ORG") or "qku").strip()
if ORG_SLUG == "qerbi-kaspi-universiteti":  # workflow-un köhnə defoltu
    ORG_SLUG = "qku"

with rls_worker_atomic(), bypass_rls():
    org = Organization.objects.filter(slug=ORG_SLUG).first() or Organization.objects.order_by("created_at").first()
    period = exam_journal_link.current_period(org)
    print(f"org_found: {int(org is not None)} period_found: {int(period is not None)}")
    print(f"classifier: {'yes' if exam_journal_gaps is not None else 'no (deploy lazımdır)'}")
    exams = (
        Exam.objects.filter(
            organization=org,
            is_deleted=False,
            subject__isnull=False,
            exam_type_extended__in=["final", "midterm"],
            created_at__date__gte=getattr(period, "start_date", None) or datetime(2026, 9, 1).date(),
        )
        .select_related("subject")
        .order_by("pk")
    )
    totals = Counter()
    reasons = Counter()
    for exam in exams:
        units = {unit.pk: unit.name for unit in exam.allowed_units.all()}
        if not units:
            continue
        totals["exams"] += 1
        new = int(exam.created_at > SNAPSHOT_UTC)
        if exam_journal_gaps is not None:
            rows = exam_journal_gaps.classify(org, exam.subject_id, list(units), period=period)
            view = {
                pk: (gap.students, gap.uncovered, gap.has_journal, gap.reasons, sorted(gap.variant_codes))
                for pk, gap in rows.items()
            }
        else:
            rows = exam_journal_link.group_subject_coverage(org, exam.subject_id, list(units), period=period)
            view = {
                pk: (len(row["students"]), len(row["uncovered"]), row["has_journal"], Counter(), [])
                for pk, row in rows.items()
            }
        gaps = {pk: item for pk, item in view.items() if item[1] or not item[2]}  # boş + jurnalsız qrup da
        linked = exam.journal_offerings.count()
        attempts = exam.attempts.filter(is_trial=False, finished_at__isnull=False).count()
        print(
            f"exam={exam.pk} new={new} category={exam.exam_type_extended} type={exam.exam_type} "
            f"subject={exam.subject.code} units={len(units)} linked_journals={linked} finished_attempts={attempts} "
            f"units_with_gap={len(gaps)}"
        )
        totals["units"] += len(units)
        totals["units_with_gap"] += len(gaps)
        for pk, (students, uncovered, has_journal, why, variants) in sorted(gaps.items(), key=lambda i: units[i[0]]):
            reasons.update(why)
            parts = " ".join(f"{key}={value}" for key, value in sorted(why.items()))
            extra = f" variant_codes={','.join(variants)}" if variants else ""
            print(
                f"  unit={units[pk]} students={students} uncovered={uncovered} has_journal={int(has_journal)} "
                f"{parts}{extra}"
            )
    print("totals: " + " ".join(f"{key}={value}" for key, value in sorted(totals.items())))
    print("students_by_reason: " + (" ".join(f"{key}={value}" for key, value in sorted(reasons.items())) or "-"))
