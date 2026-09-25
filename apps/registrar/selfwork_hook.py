"""«Fənn qovluğu» → jurnal körpüsü (registrar tərəfi): sərbəst iş balının jurnala yazılması.

Müqavilə ``apps/subject_folder/public.py`` §9-dadır; ictimai giriş nöqtəsi
``apps.registrar.public_services.selfwork_points.record_points`` / ``preview``
(:mod:`apps.registrar.selfwork_points` — bu modula ötürür).

``record_points`` qaydaları (sahib 2026-09-25):

* ``transaction.atomic`` daxilində; kilid sırası açılış (yalnız struktur
  qurulanda) → qeydiyyat → işarə (``select_for_update``) — paralel iki çağırış
  eyni slota İKİ bal yaza bilməz;
* jurnal kilidlidirsə → ``(False, "Jurnal kilidlidir …")`` (qovluq ``blocked`` yazır);
* qeydiyyat bu açılışda ``ENROLLED`` olmalıdır;
* ``max_points`` jurnaldakı slotun tavanına BƏRABƏR olmalıdır (şkala uyğunsuzluğu → imtina);
* ``0 < points ≤ max_points`` (ən çoxu 1 onluq);
* İKİNCİ BAL YOXDUR: slotda HƏR HANSI mənbədən bal varsa → eyni ``source_ref`` +
  eyni bal = idempotent ``(True, "… artıq yazılıb")``, qalan hər hal imtina;
* bütün slotların cəmi ≤ 10;
* yazı: ``done=True, points, source="subject_folder", source_ref, graded_at,
  entered_by`` + qiymət auditi (jurnalın «Tarixçə» paneli).

``preview`` — yazısız, ≤ 3 sorğu (açılış+sxem+mövzular+tələbənin işarələri TƏK
sorğuda; struktur hələ qurulmayıbsa sillabus üçün +2).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import FilteredRelation, Q, Sum
from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import grade_audit
from apps.registrar import selfwork_points as rules
from apps.registrar import selfwork_structure as structure
from apps.registrar.models import CourseOffering, Enrollment, SelfWorkMark, SelfWorkTopic

_CTX = "registrar.selfwork_hook"


# ── Mesajlar (qovluq onları müəllimə olduğu kimi göstərir) ───────────────────


def slot_label(slot) -> str:
    return pgettext(_CTX, "Sərbəst iş %(n)s") % {"n": slot}


def _fmt(label, points, max_points, total) -> dict:
    return {
        "slot": label,
        "points": rules.display(points),
        "max": rules.display(max_points),
        "total": rules.display(total),
        "max_total": rules.display(rules.TOTAL_MAX),
    }


def _msg_written(label, points, max_points, total) -> str:
    return pgettext(_CTX, "Jurnala yazıldı: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)") % _fmt(
        label, points, max_points, total
    )


def _msg_already(label, points, max_points, total) -> str:
    return pgettext(
        _CTX, "Jurnalda artıq yazılıb: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)"
    ) % _fmt(label, points, max_points, total)


def _msg_locked() -> str:
    return pgettext(_CTX, "Jurnal kilidlidir — bal yazılmadı. Dəyişiklik yalnız sənədli düzəlişlə mümkündür.")


def _msg_not_enrolled() -> str:
    return pgettext(_CTX, "Tələbə bu jurnalda aktiv qeydiyyatda deyil — bal yazılmadı.")


def _msg_invalid(max_points) -> str:
    return pgettext(_CTX, "Bal 0-dan böyük və %(max)s-dən çox olmamalıdır (ən çoxu bir onluq) — bal yazılmadı.") % {
        "max": rules.display(max_points) if max_points is not None else "—"
    }


def _msg_wrong_max(label, journal_max, folder_max) -> str:
    return pgettext(
        _CTX,
        "Bal şkalası uyğun gəlmir: jurnalda %(slot)s maksimum %(journal)s baldır, fənn qovluğunda isə %(folder)s. "
        "Sillabusun sərbəst iş strukturunu yoxlayın.",
    ) % {"slot": label, "journal": rules.display(journal_max), "folder": rules.display(folder_max)}


def _msg_second_award(label, current, max_points) -> str:
    return pgettext(
        _CTX,
        "Bu sərbəst iş üçün bal artıq yazılıb (%(slot)s · %(current)s/%(max)s) — ikinci dəfə bal verilmir. "
        "Dəyişiklik yalnız jurnalda sənədli düzəlişlə mümkündür.",
    ) % {"slot": label, "current": rules.display(current), "max": rules.display(max_points)}


def _msg_corrected(label) -> str:
    return pgettext(
        _CTX,
        "%(slot)s üzrə bu bal jurnalda sənədli düzəlişlə dəyişdirilib — yenidən yazılmır.",
    ) % {"slot": label}


def _msg_total(total) -> str:
    return pgettext(_CTX, "Sərbəst iş cəmi %(max_total)s baldan çox ola bilməz (jurnalda artıq %(total)s bal var).") % {
        "max_total": rules.display(rules.TOTAL_MAX),
        "total": rules.display(total),
    }


def _msg_no_slot(plan, slot) -> str:
    if plan is not None and plan.state == structure.STATE_MISMATCH:
        return structure.mismatch_message(plan)
    if plan is not None and plan.is_structured:
        return pgettext(_CTX, "Jurnalın sərbəst iş strukturunda «%(slot)s» yoxdur (%(label)s).") % {
            "slot": slot_label(slot),
            "label": plan.structure.label,
        }
    return pgettext(
        _CTX,
        "Jurnalda sərbəst iş strukturu yoxdur: bu açılışın təsdiqlənmiş sillabusunda sərbəst iş strukturu "
        "(1 × 10 / 2 × 5 / 10 × 1) tapılmadı.",
    )


# ── Köməkçilər ───────────────────────────────────────────────────────────────


def _slot_number(raw):
    try:
        slot = int(raw)
    except (TypeError, ValueError):
        return None
    return slot if 1 <= slot <= rules.TOTAL_MAX else None


def _slot_topic(offering, slot):
    return SelfWorkTopic.objects.filter(offering=offering, slot_index=slot).first()


def _other_points(enrollment, offering, topic) -> Decimal:
    """Tələbənin bu açılışdakı DİGƏR slotlarının effektiv bal cəmi (tavansız — cəm yoxlaması üçün)."""
    total = (
        SelfWorkMark.objects.filter(enrollment=enrollment, topic__offering=offering, done=True)
        .exclude(topic=topic)
        .aggregate(total=Sum(rules.points_expression()))["total"]
    )
    return Decimal(total or 0)


def _journal_locked(offering) -> bool:
    from apps.registrar.gradebook import journal_is_locked

    return journal_is_locked(offering)


# ── Hook ─────────────────────────────────────────────────────────────────────


def record_points(*, offering, enrollment, slot_index, slot_title, max_points, points, source_ref, by_user):
    """Bax modul docstring-i → ``(ok: bool, mesaj: str)``."""
    slot = _slot_number(slot_index)
    try:
        folder_max = rules.parse_points(max_points)
        value = rules.parse_points(points)
    except ValueError:
        return False, _msg_invalid(None)
    if slot is None:
        return False, _msg_no_slot(None, slot_index)
    label = slot_label(slot)
    source_ref = str(source_ref or "")[:64]
    with transaction.atomic():
        if _journal_locked(offering):
            return False, _msg_locked()
        if getattr(enrollment, "offering_id", None) != offering.pk:
            return False, _msg_not_enrolled()
        topic = _slot_topic(offering, slot)
        if topic is None:
            plan = structure.ensure_structure(offering)
            topic = _slot_topic(offering, slot)
            if topic is None:
                return False, _msg_no_slot(plan, slot)
        # ``entry_score_for`` sərbəst işi YALNIZ SELF_WORK komponenti varsa sayır.
        structure.ensure_selfwork_component(offering)
        locked_enrollment = Enrollment.objects.select_for_update().filter(pk=enrollment.pk, offering=offering).first()
        if locked_enrollment is None or locked_enrollment.status != Enrollment.Status.ENROLLED:
            return False, _msg_not_enrolled()
        mark = SelfWorkMark.objects.select_for_update().filter(topic=topic, enrollment=locked_enrollment).first()
        if folder_max is None or folder_max != topic.max_points:
            return False, _msg_wrong_max(label, topic.max_points, folder_max if folder_max is not None else 0)
        if value is None or value <= 0 or value > topic.max_points:
            return False, _msg_invalid(topic.max_points)
        others = _other_points(locked_enrollment, offering, topic)
        if rules.is_graded(mark):
            current = rules.effective_points(mark, topic)
            same_award = (
                mark.source == rules.SOURCE_SUBJECT_FOLDER
                and mark.source_ref == source_ref
                and mark.points is not None
                and rules.normalize(mark.points) == value
            )
            if same_award:
                return True, _msg_already(label, value, topic.max_points, rules.cap_total(others + current))
            return False, _msg_second_award(label, current, topic.max_points)
        if (
            mark is not None
            and mark.source == rules.SOURCE_SUBJECT_FOLDER
            and source_ref
            and mark.source_ref == source_ref
        ):
            return False, _msg_corrected(label)
        if others + value > rules.TOTAL_MAX:
            return False, _msg_total(others)
        _write(offering, topic, locked_enrollment, mark, value, source_ref, by_user, slot_title)
    return True, _msg_written(label, value, topic.max_points, rules.cap_total(others + value))


def _write(offering, topic, enrollment, mark, value, source_ref, by_user, slot_title) -> None:
    from apps.registrar.selfwork_marks import audit_value

    now = timezone.now()
    old = audit_value(mark, topic)
    fields = {
        "done": True,
        "points": value,
        "source": rules.SOURCE_SUBJECT_FOLDER,
        "source_ref": source_ref,
        "graded_at": now,
        "entered_by": by_user if getattr(by_user, "pk", None) else None,
    }
    if mark is None:
        mark = SelfWorkMark.objects.create(
            organization=offering.organization, topic=topic, enrollment=enrollment, **fields
        )
    else:
        for name, field_value in fields.items():
            setattr(mark, name, field_value)
        mark.save(update_fields=[*fields, "updated_at"])
    folder_title = str(slot_title or "").strip()[:60]
    item = f"Sərbəst iş · {topic.title[:60]} · Fənn qovluğu"
    if folder_title and folder_title != topic.title[:60]:
        item = f"{item}: {folder_title}"
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user if getattr(by_user, "pk", None) else None,
        kind="component",
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": item,
                "old": old,
                "new": audit_value(mark, topic),
            }
        ],
    )


# ── Önbaxış (yazısız) ────────────────────────────────────────────────────────


class _Row:
    """Önbaxış sorğusunun mövzu sətri (model obyekti qurulmur)."""

    __slots__ = ("id", "slot_index", "max_points", "title", "order", "created_at", "done", "points", "source")

    def __init__(self, values):
        (
            self.id,
            self.slot_index,
            self.max_points,
            self.title,
            self.order,
            self.created_at,
            self.done,
            self.points,
            self.source,
        ) = values

    @property
    def graded(self) -> bool:
        return bool(self.done) or self.points is not None

    def value(self) -> Decimal:
        return rules.effective_value(points=self.points, done=bool(self.done), max_points=self.max_points)


def _preview_rows(offering, enrollment):
    """``(kilidli?, [mövzu sətirləri])`` — açılış + sxem + mövzular + bu tələbənin işarələri TƏK sorğuda."""
    from apps.registrar.gradebook import _CLOSED_STATUSES

    raw = list(
        CourseOffering.objects.filter(pk=offering.pk)
        .annotate(
            swp_mark=FilteredRelation(
                "self_work_topics__marks",
                condition=Q(self_work_topics__marks__enrollment_id=enrollment.pk),
            )
        )
        .values_list(
            "assessment_scheme__is_published",
            "assessment_scheme__approval_status",
            "self_work_topics__id",
            "self_work_topics__slot_index",
            "self_work_topics__max_points",
            "self_work_topics__title",
            "self_work_topics__order",
            "self_work_topics__created_at",
            "swp_mark__done",
            "swp_mark__points",
            "swp_mark__source",
        )
    )
    locked = any(bool(row[0]) or row[1] in _CLOSED_STATUSES for row in raw)
    rows = sorted(
        (_Row(row[2:]) for row in raw if row[2] is not None),
        key=lambda item: (item.order, item.created_at),
    )
    return locked, rows


def preview(*, offering, enrollment, slot_index, points) -> dict:
    """Bax modul docstring-i. ``blocked=True`` → ``reason`` qovluğun baxış zolağında göstərilir."""
    result = {
        "topic_title": "",
        "max_points": None,
        "current_points": None,
        "total_after": None,
        "total_max": int(rules.TOTAL_MAX),
        "blocked": False,
        "reason": "",
    }
    slot = _slot_number(slot_index)
    if slot is None:
        return {**result, "blocked": True, "reason": _msg_no_slot(None, slot_index)}
    label = slot_label(slot)
    locked, rows = _preview_rows(offering, enrollment)
    target = next((row for row in rows if row.slot_index == slot), None)
    title, max_points = (target.title, target.max_points) if target else (label, None)
    if target is None:
        plan = structure.plan_for(
            rows,
            graded_topic_ids={row.id for row in rows if row.graded},
            structure=structure.syllabus_structure(offering) if structure.needs_syllabus(rows) else None,
        )
        planned = next((row for row, index, _max in plan.adopt if index == slot), None)
        if planned is not None:
            target, title, max_points = planned, planned.title, plan.structure.per_score
        elif slot in plan.create:
            title, max_points = structure.SLOT_TITLE.format(n=slot), plan.structure.per_score
        else:
            return {**result, "topic_title": label, "blocked": True, "reason": _msg_no_slot(plan, slot)}
    others = sum((row.value() for row in rows if row is not target), Decimal("0"))
    current = target.value() if target is not None and target.graded else None
    result.update(topic_title=title, max_points=max_points, current_points=current)
    try:
        value = rules.parse_points(points)
    except ValueError:
        value = None
    if locked:
        reason = _msg_locked()
    elif enrollment.offering_id != offering.pk or enrollment.status != Enrollment.Status.ENROLLED:
        reason = _msg_not_enrolled()
    elif current is not None:
        reason = _msg_second_award(label, current, max_points)
    elif value is None or value <= 0 or value > max_points:
        reason = _msg_invalid(max_points)
    elif others + value > rules.TOTAL_MAX:
        reason = _msg_total(others)
    else:
        return {**result, "total_after": rules.cap_total(others + value)}
    after = others + (current or 0)
    return {**result, "total_after": rules.cap_total(after), "blocked": True, "reason": reason}


__all__ = ["preview", "record_points", "slot_label"]
