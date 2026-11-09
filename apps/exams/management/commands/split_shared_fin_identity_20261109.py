"""``split_shared_fin_identity_20261109`` — köhnə sistemdə BİR FİN iki ayrı tələbədə olduğu üçün bir hesaba
birləşmiş şəxsi ayırır (sahib 2026-11-09, «çox ciddi məsələ»: Məryəm Əliyeva Qabil qızının 536 T yazılışları və
Midterm nəticəsi Ramal Süleymanovun hesabında idi).

Plan (``legacy-identity-split/1``, şifrəli release, YALNIZ id-lər)::

    {"format": "legacy-identity-split/1",
     "cases": [{"key": "a", "holder": <FİN sahibi hesab id>, "person": <adamın ÖZ hesab id (əvvəlcədən RİM-də yaradılır)>,
                "enrollments": ["<holder-un adama aid yazılış uuid-i>", ...],
                "attempts": [{"subject": "Turizmə giriş", "finished_on": "2026-11-03"}]}]}

Hər hal üçün, bir tranzaksiyada:

* **yazılışlar** — ``holder``-un göstərilən yazılışlarının (alt qrupdan gəlmiş / azad edilmiş) xanaları
  (``LessonMark``) və komponent balları adamın həmin açılışda YENİ öz yazılışına keçir (adam qrupun ÖZ tələbəsidir,
  ``source_group`` yoxdur); holder-un yazılışı ``dropped`` tarixçə kimi qalır (``source_group`` DB-də write-once-dur).
  Qayıb saatı yenidən hesablanır. Adamın həmin açılışda artıq yazılışı varsa sətir ATLANIR (``skip_person_has_enrollment``);
* **Midterm cəhdi** — ``holder``-un fənn adı + bitmə tarixi ilə TƏK tapılan rəsmi cəhdi adama keçir (``user``),
  ``holder``-un bu cəhddən avtomatik düşmüş Midterm balı silinir, cəhd yenidən jurnala sinxronlanır
  (:func:`apps.exams.services.midterm_journal_sync.sync_midterm_attempt`) — bal adamın öz jurnalına düşür.

Defolt dry-run (eyni kod, geri qaytarılır); stdout-a YALNIZ saylar (``legacy_split: açar=say``). Hər dəyişiklik
``registrar.legacy_identity_split`` audit sətri ilə izlənir.
"""

from __future__ import annotations

import datetime
import json
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction
from core.rls import apply_rls_request_context, bypass_rls, journal_unlock
from core.rls_pooling import rls_worker_atomic

FORMAT = "legacy-identity-split/1"
PREFIX = "legacy_split:"
RESOURCE = "registrar.legacy_identity_split"
REASON = "Sahib 2026-11-09: köhnə sistemdə eyni FİN iki tələbədə — qarışmış hesabın ayrılması"
MAX_CASES = 50


def load_plan(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise CommandError("legacy_split_file_unreadable") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("cases"), list):
        raise CommandError("legacy_split_format_unknown")
    cases = data["cases"]
    if not cases or len(cases) > MAX_CASES:
        raise CommandError("legacy_split_cases_out_of_range")
    for case in cases:
        if not isinstance(case, dict) or not case.get("holder") or not case.get("person"):
            raise CommandError("legacy_split_case_invalid")
        if str(case["holder"]) == str(case["person"]):
            raise CommandError("legacy_split_case_invalid")
        if not isinstance(case.get("enrollments", []), list) or not isinstance(case.get("attempts", []), list):
            raise CommandError("legacy_split_case_invalid")
        for spec in case.get("attempts", []):
            if not isinstance(spec, dict) or not str(spec.get("subject") or "").strip():
                raise CommandError("legacy_split_case_invalid")
            try:
                datetime.date.fromisoformat(str(spec.get("finished_on")))
            except (TypeError, ValueError):
                raise CommandError("legacy_split_case_invalid") from None
    return cases


def _student(organization, user_id):
    User = get_user_model()
    return (
        User.objects.filter(
            pk=user_id,
            is_active=True,
            memberships__organization=organization,
            memberships__role__name="student",
            memberships__is_active=True,
        )
        .distinct()
        .first()
    )


def move_enrollments(*, organization, actor, holder, person, ids, counts) -> list:
    """Holder-un yazılışındakı xanalar/komponent balları adamın YENİ öz yazılışına keçir; köhnə yazılış ``dropped`` qalır.

    ``source_group`` DB-də write-once olduğu üçün (``registrar_guard_enrollment_source_group``) yazılışın özü
    köçürülmür — adam qrupun öz tələbəsi kimi təmiz yazılış alır, tarixçə holder-da saxlanır.
    """
    from apps.registrar.public import recompute_absence_hours_many

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    LessonMark = django_apps.get_model("registrar", "LessonMark")
    ComponentScore = django_apps.get_model("registrar", "ComponentScore")

    created = []
    for raw in ids:
        source = (
            Enrollment.objects.select_related("offering__subject", "offering__group")
            .filter(organization=organization, pk=str(raw).strip())
            .first()
        )
        if source is None or source.student_id != holder.pk:
            counts["skip_enrollment_not_holder"] += 1
            continue
        if Enrollment.objects.filter(organization=organization, offering=source.offering, student=person).exists():
            counts["skip_person_has_enrollment"] += 1
            continue
        target = Enrollment.objects.create(
            organization=organization,
            student=person,
            offering=source.offering,
            kind=source.kind,
            status=Enrollment.Status.ENROLLED,
            lab_group=source.lab_group,
            seminar_group=source.seminar_group,
            legacy_qb_fail=source.legacy_qb_fail,
        )
        # ``LessonMark.enrollment`` / ``ComponentScore.enrollment`` DB-də dəyişməz identikdir — xana KÖÇÜRÜLMÜR,
        # eyni məzmunla yeni sətir yaranır (``created_at`` köhnəsi kimi), köhnə sətir silinir (twin_relocate qaydası).
        marks = 0
        for mark in LessonMark.objects.filter(organization=organization, enrollment=source).select_related("lesson"):
            copied = LessonMark.objects.create(
                organization=organization,
                lesson=mark.lesson,
                enrollment=target,
                status=mark.status,
                score=mark.score,
                entered_by_id=mark.entered_by_id,
            )
            # ``created_at`` köhnəsi kimi (redaktə pəncərəsi yenidən açılmır) — INSERT-dən dərhal sonra UPDATE keçir.
            LessonMark.objects.filter(pk=copied.pk).update(created_at=mark.created_at)
            mark.delete()
            marks += 1
        scores = 0
        for row in ComponentScore.objects.filter(organization=organization, enrollment=source):
            created = ComponentScore.objects.create(
                organization=organization,
                component_id=row.component_id,
                enrollment=target,
                score=row.score,
                entered_by_id=row.entered_by_id,
                exam_source=row.exam_source,
            )
            ComponentScore.objects.filter(pk=created.pk).update(created_at=row.created_at)
            row.delete()
            scores += 1
        previous = source.status
        if source.status != Enrollment.Status.DROPPED:
            source.status = Enrollment.Status.DROPPED
            source.save(update_fields=["status", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=target,
            old_values={"holder_enrollment": str(source.pk), "holder_status": previous, "student": holder.pk},
            new_values={"student": person.pk, "marks_moved": marks, "scores_moved": scores},
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(target.pk),
        )
        counts["enrollments_moved"] += 1
        counts["marks_moved"] += marks
        counts["scores_moved"] += scores
        if previous != Enrollment.Status.DROPPED:
            counts["holder_enrollments_dropped"] += 1
        created.append(target)
        created.append(source)
    if created:
        recompute_absence_hours_many(created)
    return created


def move_attempt(*, organization, actor, holder, person, spec, counts) -> None:
    from apps.exams.models import ExamAttempt
    from apps.exams.services.midterm_journal_sync import sync_midterm_attempt

    ComponentScore = django_apps.get_model("registrar", "ComponentScore")

    finished_on = datetime.date.fromisoformat(str(spec["finished_on"]))
    attempts = list(
        ExamAttempt.objects.select_related("exam", "exam__subject")
        .filter(
            user=holder,
            exam__organization=organization,
            exam__subject__name__istartswith=str(spec["subject"]).strip(),
            finished_at__date=finished_on,
            is_trial=False,
        )
        .order_by("finished_at")
    )
    if len(attempts) != 1:
        counts["skip_attempt_missing" if not attempts else "skip_attempt_ambiguous"] += 1
        return
    attempt = attempts[0]
    removed = 0
    for row in ComponentScore.objects.filter(organization=organization, enrollment__student=holder).exclude(
        exam_source=None
    ):
        source = row.exam_source if isinstance(row.exam_source, dict) else {}
        if str(source.get("attempt_id")) == str(attempt.pk):
            log_action(
                AuditAction.DELETE,
                user=actor,
                organization=organization,
                obj=row,
                old_values={"enrollment": str(row.enrollment_id), "score": str(row.score), "attempt": attempt.pk},
                reason=REASON,
                resource_type=RESOURCE,
                resource_id=str(row.pk),
            )
            row.delete()
            removed += 1
    counts["holder_scores_removed"] += removed
    attempt.user = person
    fields = ["user"]
    taken = set(ExamAttempt.objects.filter(user=person, exam=attempt.exam).values_list("attempt_number", flat=True))
    if attempt.attempt_number in taken:  # ``uniq_attempt_number_per_user_exam`` — adamın öz cəhdləri ilə toqquşmasın
        attempt.attempt_number = max(taken) + 1
        fields.append("attempt_number")
    attempt.save(update_fields=fields)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=attempt,
        old_values={"user": holder.pk},
        new_values={"user": person.pk, "exam": attempt.exam_id},
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(attempt.pk),
    )
    counts["attempts_moved"] += 1
    status, _row = sync_midterm_attempt(attempt, actor=actor, notify=False)
    counts[f"attempt_sync_{status}"] += 1


def run(*, organization, actor, cases, counts) -> None:
    for case in cases:
        holder = _student(organization, case["holder"])
        person = _student(organization, case["person"])
        if holder is None or person is None:
            counts["skip_case_account_unknown"] += 1
            continue
        counts["cases"] += 1
        move_enrollments(
            organization=organization,
            actor=actor,
            holder=holder,
            person=person,
            ids=case.get("enrollments", []),
            counts=counts,
        )
        for spec in case.get("attempts", []):
            move_attempt(organization=organization, actor=actor, holder=holder, person=person, spec=spec, counts=counts)


def failure_code(exc: BaseException) -> str:
    """``legacy_split_failed_<sinif>_<mesaj>`` — yalnız ``[a-z0-9_]`` (şəxsi məlumat / sitat yoxdur), ≤ 120 simvol."""
    import re

    text = f"{type(exc).__name__} {str(exc)[:160]}".lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return ("legacy_split_failed_" + text)[:120].rstrip("_")


class Command(BaseCommand):
    help = (
        "Köhnə sistemdə eyni FİN-lə bir hesaba birləşmiş tələbənin yazılışlarını və Midterm cəhdini öz hesabına keçir."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="Təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--file", required=True, help="legacy-identity-split/1 JSON planı")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        cases = load_plan(options["file"])
        actor = (
            get_user_model()
            .objects.filter(username=str(options["actor"]).strip(), is_active=True, is_superuser=True)
            .first()
        )
        if actor is None:
            raise CommandError("actor_must_be_active_superuser")
        Organization = django_apps.get_model("organizations", "Organization")
        counts: Counter = Counter()
        with rls_worker_atomic(), bypass_rls():
            organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
            if organization is None:
                raise CommandError("legacy_split_organization_unknown")
            apply_rls_request_context(user_id=actor.pk, org_id=organization.pk)
            try:
                # Sistem yazısı: köhnə xanaların/komponent ballarının köçürülməsi (yeni sətir + köhnənin silinməsi)
                # jurnalın 2 saatlıq DB qoruyucusundan keçməlidir — ``twin_merge_scored`` / midterm_bridge ilə eyni rəsmi yol.
                with journal_unlock(), transaction.atomic():  # unlock atomic-dən SONRA bağlanır (dry-run rollback)
                    run(organization=organization, actor=actor, cases=cases, counts=counts)
                    if not options["apply"]:
                        transaction.set_rollback(True)
            except CommandError:
                raise
            except Exception as exc:  # noqa: BLE001 — iş axını yalnız «CommandError: kod» sətrini göstərir
                # Prod dry-run 42652974176: traceback süzülür, səbəb görünmürdü — sinif + mesaj yalnız [a-z0-9_] kimi.
                raise CommandError(failure_code(exc)) from None
        self.stdout.write(f"{PREFIX} mode={'apply' if options['apply'] else 'dry_run'}")
        self.stdout.write(PREFIX + " " + " ".join(f"{key}={value}" for key, value in sorted(counts.items())))
