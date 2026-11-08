"""RİM müraciətləri 2026-11-07 — sabit id-li düzəlişlər (sahib: «müraciətləri həll et, təsdiq gözləmə»).

* **MR-000247** (Reyhan Əhmədova): «034 Psixologiya» jurnalı uydurmadır — köhnə sistemdə 034-ün Psixologiya
  jurnalı heç olmayıb, yük sətri (``ba9b10bf``, 10-30, qeydsiz) əl ilə yazılıb, jurnalda dərs / xana yoxdur.
  Jurnal passiv olur (qeydiyyatlar ``dropped``, cədvəl slotu parklanır). «136 Si-2»nin artıq jurnalı 11-06-da
  ``repair_applications_20261106`` (MR-236) ilə «Psixologiya»ya birləşib — burada yalnız YOXLANILIR.
* **MR-000253** (Gövhər Aydəmirova): Kollec «Meşə və park» qrupunun «Azərbaycanın flora və faunası» və «Ekologiya»
  jurnalları — kollec köhnə sistemdə işləyir (köhnə 15392 / 15393 aktivdir); bu jurnallar 10-23 köhnə sistemdən
  köçürmə ilə yaranıb, yeni sistemdə heç kim heç nə yazmayıb. İkisi də passiv olur (dərslər / xanalar QALIR).
* **MR-000245** (Reyhan Əhmədova, 209/6SP magistr): köhnə 14685 jurnalının adı «Sosial psixologiyada qrup problemi…»
  (QKU-1936 — onun 2023-dən bəri hər il keçdiyi, köhnə sillabusu 1702 olan fənn), amma köhnə sistemdə səhvən
  «Sosial-psixoloji treninq…» (QKU-2187, başqa müəllimin fənni) fənninə bağlanıb; köçürmə jurnalı və yük sətrini
  QKU-2187-yə yazıb. Fənn YERİNDƏ düzəlir (mövcud ``fix_offering_subject`` — dərslər / xanalar toxunulmur).

Hər addım YALNIZ gözlənilən vəziyyətdə yazır (id + fənn + qrup + müəllim + dövr; yeni sistemdə istifadəçinin yazdığı
dərs / xana yoxdur) — əks halda sayğacla keçir. İdempotentdir; ``undo`` bu əmrin audit izinə görə geri qaytarır.
Şəxsi məlumat yoxdur — YALNIZ id-lər.
"""

from __future__ import annotations

import re
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"  # 2026/2027 Payız
REYHAN, GOVHAR = 7740, 7760
DEACTIVATED = "registrar.applications_repair_2026_11_07.deactivated"
PARK_REASON = "RİM 2026-11-07: jurnal passivdir (uydurma / köhnə sistemdə aparılır)"

DEACTIVATIONS = (
    {
        "key": "psy",  # MR-247: 034 «Psixologiya»
        "offering": "bf78e986-41b2-4385-bccf-140f3227b776",
        "subject": "9455663e-edb0-48e1-980b-6d430d07575d",
        "group": "c895b91a-d8c2-48ac-a971-10b8812a2692",
        "instructor": REYHAN,
        "reason": "RİM MR-000247: 034 qrupu «Psixologiya» keçmir — köhnə sistemdə jurnalı yoxdur, dərs / xana yoxdur",
    },
    {
        "key": "flora",  # MR-253: Kollec «Meşə və park» — «Azərbaycanın flora və faunası»
        "offering": "a16ba622-bf77-40a1-95ce-8d110bce067f",
        "subject": "824e6fa9-00b1-4ec2-b54a-803c8983e502",
        "group": "e46e0abe-0d6a-4aab-9b45-918c6051e9d7",
        "instructor": GOVHAR,
        "reason": "RİM MR-000253: kollec jurnalı köhnə sistemdə aparılır (köhnə 15393) — yeni sistemdəki nüsxə passiv",
    },
    {
        "key": "ecology",  # MR-253: Kollec «Meşə və park» — «Ekologiya»
        "offering": "931796b4-4403-41b5-9986-0342b2716c8b",
        "subject": "50c59b72-a1cc-4714-ad64-b24ef206a946",
        "group": "e46e0abe-0d6a-4aab-9b45-918c6051e9d7",
        "instructor": GOVHAR,
        "reason": "RİM MR-000253: kollec jurnalı köhnə sistemdə aparılır (köhnə 15392) — yeni sistemdəki nüsxə passiv",
    },
)

# MR-236 (11-06) birləşməsi: mənbə «Çapaqədər…» passiv, hədəf «Psixologiya 136 Si-2» aktiv olmalıdır.
SI2_MERGED_SOURCE = "45985e6b-0500-42e8-a80c-cfc4243601a3"
SI2_TARGET = "e2a4155d-8e96-41e8-bc92-d635eb306429"

SUBJECT_FIX = {  # MR-245: 209/6SP
    "offering": "d4dff429-14ba-49e4-bd96-6bec149128f9",
    "group": "de6fb053-b9e1-4488-80d2-0c4f76f5c933",
    "row": "43cf4197-c4c8-4baf-a5d1-5fd0ea570a20",
    "wrong": "ed802730-dc11-4496-b4a9-4cd034212150",  # QKU-2187 «Sosial-psixoloji treninq: nəzəriyyə və praktika»
    "right": "b3ec33fd-9890-4c23-8b1b-a0e230494468",  # QKU-1936 «Sosial psixologiyada qrup problemi…»
    "instructor": REYHAN,
}
_KEY = re.compile(r"[a-z_]+")


def _model(app, name):
    return django_apps.get_model(app, name)


def _user_entered(offering) -> bool:
    """Yeni sistemdə istifadəçi bu jurnala dərs və ya xana yazıbmı (köçürülən sətirlərdə müəllif boşdur)."""
    Lesson, Mark = _model("registrar", "Lesson"), _model("registrar", "LessonMark")
    lessons = Lesson.objects.filter(offering=offering)
    return (
        lessons.filter(created_by__isnull=False).exists()
        or Mark.objects.filter(lesson__in=lessons, entered_by__isnull=False).exists()
    )


def _exam_linked(offering) -> bool:
    return (
        _model("exams", "Exam").objects.filter(journal_offerings=offering).exists()
        or _model("registrar", "ExamScoreSheet").objects.filter(offering=offering).exists()
    )


def _deactivate(spec, *, organization, actor, counts) -> None:
    Offering, Enrollment = _model("registrar", "CourseOffering"), _model("registrar", "Enrollment")
    Slot, key = _model("registrar", "ScheduleSlot"), spec["key"]
    offering = (
        Offering.objects.select_for_update(of=("self",)).filter(organization=organization, pk=spec["offering"]).first()
    )
    if offering is None:
        counts[f"{key}_missing"] += 1
        return
    if not offering.is_active:
        counts[f"{key}_already_inactive"] += 1
        return
    expected = (spec["subject"], spec["group"], PERIOD, spec["instructor"])
    actual = (str(offering.subject_id), str(offering.group_id), str(offering.period_id), offering.instructor_id)
    if actual != expected:
        counts[f"{key}_state_changed_skipped"] += 1
        return
    if _user_entered(offering):
        counts[f"{key}_in_use_skipped"] += 1
        return
    if _exam_linked(offering):
        counts[f"{key}_exam_linked_skipped"] += 1
        return
    now = timezone.now()
    enrollments = list(
        Enrollment.objects.filter(offering=offering, status="enrolled").order_by("pk").values_list("pk", flat=True)
    )
    Enrollment.objects.filter(pk__in=enrollments).update(status="dropped", updated_at=now)
    slots = list(Slot.objects.filter(offering=offering, is_parked=False).order_by("pk").values_list("pk", flat=True))
    Slot.objects.filter(pk__in=slots).update(
        is_parked=True, parked_at=now, parked_by=actor, park_reason=PARK_REASON, updated_at=now
    )
    Offering.objects.filter(pk=offering.pk).update(is_active=False, updated_at=now)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=offering,
        old_values={"is_active": True},
        new_values={
            "is_active": False,
            "dropped_enrollments": [str(pk) for pk in enrollments],
            "parked_slots": [str(pk) for pk in slots],
        },
        reason=spec["reason"],
        resource_type=DEACTIVATED,
        resource_id=str(offering.pk),
    )
    counts[f"{key}_deactivated"] += 1
    counts["offerings_deactivated"] += 1
    counts["enrollments_dropped"] += len(enrollments)
    counts["slots_parked"] += len(slots)


def check_si2_merge(*, organization, counts) -> None:
    Offering = _model("registrar", "CourseOffering")
    state = dict(
        Offering.objects.filter(organization=organization, pk__in=[SI2_MERGED_SOURCE, SI2_TARGET]).values_list(
            "pk", "is_active"
        )
    )
    states = {str(pk): active for pk, active in state.items()}
    merged = states.get(SI2_MERGED_SOURCE) is False and states.get(SI2_TARGET) is True
    counts["si_merge_applied" if merged else "si_merge_pending"] += 1


def _subject_command(*, organization, actor, counts, subject, apply, prefix) -> None:
    out = StringIO()
    args = ["--org", organization.slug, "--actor", actor.username, f"--offering={SUBJECT_FIX['offering']}"]
    args += [f"--subject={subject}", f"--row={SUBJECT_FIX['row']}"] + (["--apply"] if apply else [])
    try:
        call_command("fix_offering_subject", *args, stdout=out)
    except CommandError as exc:
        code = str(exc).strip()
        counts[f"{prefix}refused"] += 1
        if _KEY.fullmatch(code):
            counts[f"{prefix}refused_{code}"] += 1
        return
    for line in out.getvalue().splitlines():
        if line.startswith("offering_subject_fix: ") and "mode=" not in line:
            for pair in line.split()[1:]:
                key, _, value = pair.partition("=")
                if _KEY.fullmatch(key) and value.isdigit():
                    counts[f"{prefix}{key}"] += int(value)


def fix_subject(*, organization, actor, counts, apply) -> None:
    offering = (
        _model("registrar", "CourseOffering")
        .objects.filter(organization=organization, pk=SUBJECT_FIX["offering"])
        .first()
    )
    if offering is None:
        counts["subject_offering_missing"] += 1
        return
    scope = (str(offering.group_id), str(offering.period_id), offering.instructor_id, offering.is_active)
    if scope != (SUBJECT_FIX["group"], PERIOD, SUBJECT_FIX["instructor"], True):
        counts["subject_state_changed_skipped"] += 1
        return
    if str(offering.subject_id) == SUBJECT_FIX["right"]:
        counts["subject_already_fixed"] += 1
        return
    if str(offering.subject_id) != SUBJECT_FIX["wrong"]:
        counts["subject_state_changed_skipped"] += 1
        return
    _subject_command(
        organization=organization,
        actor=actor,
        counts=counts,
        subject=SUBJECT_FIX["right"],
        apply=apply,
        prefix="subject_",
    )


def run(*, organization, actor, counts, apply=False) -> None:
    for spec in DEACTIVATIONS:
        _deactivate(spec, organization=organization, actor=actor, counts=counts)
    check_si2_merge(organization=organization, counts=counts)
    fix_subject(organization=organization, actor=actor, counts=counts, apply=apply)


def undo(*, organization, actor, counts, apply=False) -> None:
    """Bu əmrin passiv etdiyi jurnallar (audit izinə görə) bərpa olunur; MR-245 fənni geri QKU-2187-yə qaytarılır."""
    Offering, Enrollment = _model("registrar", "CourseOffering"), _model("registrar", "Enrollment")
    Slot, AuditLog = _model("registrar", "ScheduleSlot"), _model("audit", "AuditLog")
    logs = AuditLog.objects.filter(organization=organization, resource_type=DEACTIVATED).order_by("created_at")
    for entry in logs:
        offering = Offering.objects.filter(organization=organization, pk=entry.resource_id, is_active=False).first()
        if offering is None:
            counts["undo_already"] += 1
            continue
        values = entry.new_values or {}
        now = timezone.now()
        counts["undo_enrollments_restored"] += Enrollment.objects.filter(
            offering=offering, pk__in=values.get("dropped_enrollments") or [], status="dropped"
        ).update(status="enrolled", updated_at=now)
        counts["undo_slots_unparked"] += Slot.objects.filter(
            offering=offering, pk__in=values.get("parked_slots") or [], is_parked=True, park_reason=PARK_REASON
        ).update(is_parked=False, parked_at=None, parked_by=None, park_reason="", updated_at=now)
        Offering.objects.filter(pk=offering.pk).update(is_active=True, updated_at=now)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=offering,
            old_values={"is_active": False},
            new_values={"is_active": True, "undo_of": str(entry.pk)},
            reason="RİM 2026-11-07 düzəlişi geri qaytarıldı",
        )
        counts["undo_offerings_reactivated"] += 1
    offering = Offering.objects.filter(organization=organization, pk=SUBJECT_FIX["offering"]).first()
    if offering is not None and str(offering.subject_id) == SUBJECT_FIX["right"]:
        _subject_command(
            organization=organization,
            actor=actor,
            counts=counts,
            subject=SUBJECT_FIX["wrong"],
            apply=apply,
            prefix="undo_subject_",
        )
    else:
        counts["undo_subject_not_applied"] += 1
