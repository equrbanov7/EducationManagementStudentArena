"""«Xarici dildə işgüzar kommunikasiya» profili — mövcud data auditi, YALNIZ OXU (sahib 2026-11-22).

Sahib: «dil fənlərində 10 bal sərbəst iş, 10 bal davamiyyət, 10 bal midterm; midterm 10, final 70 köçürülür».
Profil (:mod:`core.language_business_rule`) yeni hesab qaydasıdır — saxlanmış ballar YENİDƏN MİQYASLANMIR. Bu əmr
profilə düşən açılışları və köhnə tavanlarla yazılmış (yeni tavandan böyük) balları SAYIR, heç nəyi dəyişmir:

* ``offerings`` — profil adına uyğun açılışlar (səviyyə dövr qapısı + RİM açarı tətbiq olunanlar ayrıca);
* ``midterm`` — Midterm komponentinin tavanı > 10, xana balı > 10 (hesabda 10-a kəsilir), avtomatik (imtahandan) xanalar;
* ``final`` — ``FinalGrade.exam_score`` > 70 / ``ResitRecord.resit_score`` > 70 / İmtahan Mərkəzinin final sətri > 70;
* ``activity`` — praktiki məşğələ (seminar) dərs balları: profildə artıq toplanmır (data qalır);
* ``selfwork`` — sərbəst iş işarələri və SELF_WORK komponenti olan açılışlar;
* ``names`` — «işgüzar … kommunikasiya» sözləri olan, amma şablona düşməyən fənn adlarının sayı (ad yoxlaması).

stdout-a YALNIZ «language_business:» saylar sətirləri (ad / FİN yoxdur; açarlar hərf + alt xətt — prod-data-ops
filtri). Xəta olarsa ``CommandError: language_business_audit_failed_<sinif>``.

    manage.py audit_language_business_grading_20261122 --org qku           # həmişə dry-run (``--apply`` rədd olunur)
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.registrar import language_business_grading
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    CourseOffering,
    ExamScoreEntry,
    FinalGrade,
    LessonMark,
    ResitRecord,
    SelfWorkMark,
)
from core import language_business_rule as rule
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "language_business:"
_MIDTERM_MAX = Decimal(rule.MIDTERM_MAX)
_EXAM_MAX = Decimal(rule.EXAM_MAX)


def _line(stdout, label, counts) -> None:
    body = " ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none=0"
    stdout.write(f"{PREFIX} {label} {body}")


def failure_code(exc) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in type(exc).__name__.lower())
    return f"language_business_audit_failed_{slug}"[:120]


class Command(BaseCommand):
    help = "«Xarici dildə işgüzar kommunikasiya» profili: açılışlar və yeni tavandan böyük ballar (yalnız oxu, saylar)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--apply", action="store_true", help="QƏBUL OLUNMUR — əmr yalnız oxuyur (dry-run)")

    def handle(self, *args, **options):
        if options.get("apply"):
            raise CommandError("read_only_command_no_apply")
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("organization_not_found")
                report = self.run(organization)
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops traceback-i gizlədir — kod görünsün
            raise CommandError(failure_code(exc)) from exc
        self.stdout.write(f"{PREFIX} mode read_only=1")
        for label in ("offerings", "midterm", "final", "activity", "selfwork", "names"):
            _line(self.stdout, label, report[label])

    def run(self, organization) -> dict:
        report = {key: Counter() for key in ("offerings", "midterm", "final", "activity", "selfwork", "names")}
        candidates = (
            CourseOffering.objects.filter(organization=organization, subject__name__icontains="kommunikasiya")
            .select_related("subject", "period", "organization")
            .order_by("pk")
        )
        offerings = []
        for offering in candidates:
            name = offering.subject.name
            if not rule.is_business_name(name):
                if "isguzar" in rule.fold(name):
                    report["names"]["near_miss_offerings"] += 1
                continue
            report["offerings"]["name_match"] += 1
            if language_business_grading.is_business(offering):
                offerings.append(offering)
            else:
                report["offerings"]["not_applied"] += 1
        report["offerings"]["applied"] = len(offerings)
        report["names"]["distinct_matched"] = len({o.subject.name for o in offerings})
        if not offerings:
            return report
        ids = [o.pk for o in offerings]
        self._midterm(ids, report["midterm"])
        self._final(organization, ids, report["final"])
        lesson_scores = LessonMark.objects.filter(
            organization=organization, enrollment__offering_id__in=ids, lesson__kind="seminar", score__isnull=False
        )
        report["activity"]["seminar_scores"] = lesson_scores.count()
        report["activity"]["offerings_with_seminar_scores"] = (
            lesson_scores.values("enrollment__offering_id").distinct().count()
        )
        report["selfwork"]["marks"] = SelfWorkMark.objects.filter(
            organization=organization, enrollment__offering_id__in=ids
        ).count()
        report["selfwork"]["offerings_with_component"] = (
            AssessmentComponent.objects.filter(offering_id__in=ids, kind=ComponentKind.SELF_WORK)
            .values("offering_id")
            .distinct()
            .count()
        )
        return report

    @staticmethod
    def _midterm(ids, counts) -> None:
        components = AssessmentComponent.objects.filter(offering_id__in=ids, kind=ComponentKind.KOLLOKVIUM)
        counts["components"] = components.count()
        counts["components_max_above_ten"] = components.filter(max_score__gt=_MIDTERM_MAX).count()
        scores = ComponentScore.objects.filter(component__in=components)
        counts["scores"] = scores.count()
        counts["scores_above_ten"] = scores.filter(score__gt=_MIDTERM_MAX).count()
        counts["scores_auto"] = scores.filter(exam_source__isnull=False).count()
        counts["scores_auto_above_ten"] = scores.filter(exam_source__isnull=False, score__gt=_MIDTERM_MAX).count()

    @staticmethod
    def _final(organization, ids, counts) -> None:
        finals = FinalGrade.objects.filter(organization=organization, enrollment__offering_id__in=ids)
        counts["exam_scores"] = finals.filter(exam_score__isnull=False).count()
        counts["exam_scores_above_seventy"] = finals.filter(exam_score__gt=_EXAM_MAX).count()
        resits = ResitRecord.objects.filter(organization=organization, enrollment__offering_id__in=ids)
        counts["resit_scores"] = resits.filter(resit_score__isnull=False).count()
        counts["resit_scores_above_seventy"] = resits.filter(resit_score__gt=_EXAM_MAX).count()
        entries = ExamScoreEntry.objects.filter(
            organization=organization, enrollment__offering_id__in=ids, assessment="final"
        )
        counts["center_entries"] = entries.count()
        counts["center_entries_above_seventy"] = entries.filter(new_score__gt=_EXAM_MAX).count()
