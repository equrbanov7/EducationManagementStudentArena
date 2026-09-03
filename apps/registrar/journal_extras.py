"""Elektron jurnal əlavə bölmələri: Kollokvium (3 ədəd) + Sərbəst iş + Kurs işi.

Kollokvium mövcud komponent mexanizmi üzərində işləyir (``AssessmentComponent``
kind=KOLLOKVIUM + ``held_on`` tarixi; ballar ``ComponentScore``-da — 2 saat
pəncərəsi və DB trigger oraya da şamildir). Sərbəst iş mövzu-çeklistdir
(``SelfWorkTopic``/``SelfWorkMark``): bal yazılmır, təhvil sayı avtomatik giriş
balına çevrilir (bax ``gradebook.entry_score_for``); lövhənin özü —
köçürülmüş "arxiv" balı da daxil — ``selfwork_board`` modulundadır. Kurs işi
giriş balından kənar ayrıca 0-100 qiymətdir.

Kilid qaydaları: jurnal kilidli (təsdiqdə/yekunlaşıb) → heç nə yazılmır; sərbəst
işdə "verilib" işarəsi hər zaman qoyulur, GERİ ALMA yalnız 2 saat içində (bal
silmə saxtakarlığına qarşı); kurs işi yazılışdan 2 saat sonra dondurulur.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.registrar import exam_eligibility, grade_audit
from apps.registrar.gradebook import MARK_EDIT_WINDOW, journal_is_locked
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    CourseWork,
    Enrollment,
    SelfWorkMark,
    SelfWorkTopic,
)

# Sərbəst iş lövhəsi modul-ölçü büdcəsinə görə ayrıca moduldadır; adlar
# buradan re-eksport olunur — çağıranlar üçün API dəyişməyib.
from apps.registrar.selfwork_board import (  # noqa: F401
    SELF_WORK_MAX_TOPICS,
    get_selfwork_board,
)

KOLLOKVIUM_COUNT = 3
KOLLOKVIUM_MAX = 10
COURSE_WORK_MAX = Decimal("100")


def _to_decimal(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ── Kollokvium (K1-K3) ───────────────────────────────────────────────────────


@transaction.atomic
def ensure_kollokviums(offering):
    """3 kollokvium komponentini idempotent yarat (K1, K2, K3 · max 10).

    Köhnə məlumat uyğunluğu: "Kollokvium N" ADLI generic komponent artıq varsa
    (kind sahəsi yeni olduğundan köhnə sətirlər generic-dir), onu yenidən
    yaratmaq əvəzinə MƏNİMSƏYİRİK — kind=KOLLOKVIUM-a normalizə olunur
    (unique (offering, name) toqquşması da bununla aradan qalxır)."""
    all_components = list(AssessmentComponent.objects.filter(offering=offering))
    by_name = {c.name: c for c in all_components}
    result = []
    base_order = len(all_components)
    for i in range(1, KOLLOKVIUM_COUNT + 1):
        name = f"Kollokvium {i}"
        component = by_name.get(name)
        if component is not None:
            if component.kind != ComponentKind.KOLLOKVIUM:
                component.kind = ComponentKind.KOLLOKVIUM
                component.save(update_fields=["kind"])
            result.append(component)
            continue
        result.append(
            AssessmentComponent.objects.create(
                organization=offering.organization,
                offering=offering,
                name=name,
                kind=ComponentKind.KOLLOKVIUM,
                max_score=KOLLOKVIUM_MAX,
                order=base_order + i,
            )
        )
    return result


def set_kollokvium_date(*, component, held_on) -> bool:
    """Kollokviumun keçirilmə tarixini yaz (tələbə tarixçəsində göstərilir)."""
    if component.kind != ComponentKind.KOLLOKVIUM or journal_is_locked(component.offering):
        return False
    component.held_on = held_on or None
    component.save(update_fields=["held_on"])
    return True


def get_kollokvium_grid(offering):
    """Kollokvium tabı: 3 komponent × tələbələr + ballar.

    Redaktə edilə bilirlik İmtahan Mərkəzi PƏNCƏRƏSİNDƏN gəlir — kollokvium üçün
    2 saat kilidi YOXDUR (pəncərə onu əvəz edir). Hər sütun (K1/K2/K3) üçün
    vəziyyət ``kollokvium_windows.entry_state`` ilə hesablanır.
    """
    from apps.registrar import kollokvium_windows as kw

    components = ensure_kollokviums(offering)
    today = timezone.localdate()
    states = [kw.entry_state(offering, idx, today) for idx in range(len(components))]
    columns = [
        {
            "component": c,
            "k_index": idx,
            "status": states[idx]["status"],
            "opens_on": states[idx].get("opens_on"),
            "deadline": states[idx].get("deadline"),
            "open": states[idx]["status"] == "open",
        }
        for idx, c in enumerate(components)
    ]
    open_by_comp = {c.id: columns[idx]["open"] for idx, c in enumerate(components)}

    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    score_map = {}
    for cs in ComponentScore.objects.filter(component__in=components, enrollment__offering=offering):
        score_map[(cs.enrollment_id, cs.component_id)] = cs.score
    rows = [
        {
            "enrollment": e,
            "student": e.student,
            "cells": [
                {
                    "component": c,
                    "score": score_map.get((e.id, c.id)),
                    "editable": open_by_comp[c.id],
                }
                for c in components
            ],
        }
        for e in enrollments
    ]
    return {
        "components": components,
        "columns": columns,
        "rows": rows,
        "any_open": any(col["open"] for col in columns),
    }


# ── Sərbəst iş (mövzu çeklisti) ──────────────────────────────────────────────


@transaction.atomic
def ensure_selfwork_component(offering):
    """Sərbəst iş komponentini idempotent yarat (kind=SELF_WORK, max 10).

    Yeni jurnalda bura bal YAZILMIR — ``entry_score_for`` çeklist cəmindən
    oxuyur. Tək istisna: köçürmə köhnə ``si`` balını bu komponentə
    ``ComponentScore`` kimi yazır; o bal YALNIZ lövhədə "arxiv" sütunu kimi
    göstərilir və giriş balına əlavə OLUNMUR (bax ``selfwork_board``)."""
    component = AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.SELF_WORK).first()
    if component is None:
        component = AssessmentComponent.objects.create(
            organization=offering.organization,
            offering=offering,
            name="Sərbəst iş",
            kind=ComponentKind.SELF_WORK,
            max_score=SELF_WORK_MAX_TOPICS,
            order=AssessmentComponent.objects.filter(offering=offering).count() + 1,
        )
    return component


@transaction.atomic
def add_selfwork_topic(*, offering, title) -> SelfWorkTopic | None:
    """Yeni sərbəst iş mövzusu (ən çoxu 10)."""
    title = (title or "").strip()
    if not title or journal_is_locked(offering):
        return None
    if SelfWorkTopic.objects.filter(offering=offering).count() >= SELF_WORK_MAX_TOPICS:
        return None
    ensure_selfwork_component(offering)
    return SelfWorkTopic.objects.create(
        organization=offering.organization,
        offering=offering,
        title=title[:255],
        order=SelfWorkTopic.objects.filter(offering=offering).count() + 1,
    )


@transaction.atomic
def delete_selfwork_topic(*, topic, by_user=None) -> bool:
    """Mövzunu sil. İşarələr də silinir (CASCADE) → giriş balı düşür, yəni akademik
    nəticə dəyişir; itən təhvillər audit izinə yazılır (2026-08 auditi)."""
    if journal_is_locked(topic.offering):
        return False
    offering, title = topic.offering, topic.title
    losing = list(SelfWorkMark.objects.filter(topic=topic, done=True).select_related("enrollment__student"))
    try:
        topic.delete()  # Correction evidence varsa PROTECT akademik tarixi saxlayır.
    except ProtectedError:
        return False
    grade_audit.log_selfwork_topic_removal(offering=offering, topic_title=title, marks=losing, by_user=by_user)
    return True


@transaction.atomic
def set_selfwork_mark(*, offering, topic_id, enrollment_id, done, by_user=None, allow_locked=False) -> bool:
    """Təhvil işarəsi: 1 hər zaman qoyulur; 1→0 geri alma yalnız 2 saat içində.
    ``allow_locked`` İKT/superuser üçün 2 saat pəncərəsini keçir."""
    if journal_is_locked(offering):
        return False
    topic = SelfWorkTopic.objects.filter(pk=topic_id, offering=offering).first()
    enrollment = offering.enrollments.filter(pk=enrollment_id, status=Enrollment.Status.ENROLLED).first()
    if topic is None or enrollment is None:
        return False
    mark = SelfWorkMark.objects.filter(topic=topic, enrollment=enrollment).first()
    if mark is None:
        if not done:
            return True  # onsuz da yoxdur
        SelfWorkMark.objects.create(
            organization=offering.organization, topic=topic, enrollment=enrollment, done=True, entered_by=by_user
        )
    else:
        if mark.done == bool(done):
            return True
        if mark.done and not done and not allow_locked and (timezone.now() - mark.updated_at) > MARK_EDIT_WINDOW:
            return False  # verilmiş işi 2 saatdan sonra geri almaq olmaz (İKT keçir)
        mark.done = bool(done)
        mark.entered_by = by_user
        mark.save(update_fields=["done", "entered_by", "updated_at"])
    grade_audit.log_grade_changes(
        offering=offering,
        by_user=by_user,
        kind="component",
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": f"Sərbəst iş · {topic.title[:60]}",
                "old": "0" if done else "1",
                "new": "1" if done else "0",
            }
        ],
    )
    return True


# ── Kurs işi (0-100, giriş balından kənar) ───────────────────────────────────


@transaction.atomic
def save_course_work(*, enrollment, topic, score, submitted_on=None, by_user=None, allow_locked=False) -> bool:
    """Kurs işini yaz/yenilə — mövcud qeyd yalnız 2 saat içində (İKT keçir)."""
    if not Enrollment.objects.filter(pk=enrollment.pk, status=Enrollment.Status.ENROLLED).exists():
        return False
    offering = enrollment.offering
    if journal_is_locked(offering):
        return False
    existing = CourseWork.objects.filter(enrollment=enrollment).first()
    now = timezone.now()
    if existing is not None and not allow_locked and (now - existing.created_at) > MARK_EDIT_WINDOW:
        return False
    value = _to_decimal(score)
    if value is not None:
        value = min(max(Decimal("0"), value), COURSE_WORK_MAX)
    old = existing.score if existing else None
    CourseWork.objects.update_or_create(
        organization=offering.organization,
        enrollment=enrollment,
        defaults={
            "topic": (topic or "").strip()[:255],
            "score": value,
            "submitted_on": submitted_on or None,
            "entered_by": by_user,
        },
    )
    if old != value:
        grade_audit.log_grade_changes(
            offering=offering,
            by_user=by_user,
            kind="component",
            changes=[
                {
                    "student": grade_audit.student_label(enrollment),
                    "item": "Kurs işi",
                    "old": grade_audit.score_repr(old),
                    "new": grade_audit.score_repr(value),
                }
            ],
        )
        if value is not None:
            from django.db import transaction as _tx

            from apps.registrar import journal_notifications as jn

            events = [{"enrollment": enrollment, "kind": jn.EVENT_COURSEWORK, "score": value}]
            _tx.on_commit(lambda: jn.send_journal_events(offering=offering, events=events))
    return True


def get_course_work_rows(offering):
    """Kurs işi tabı: tələbə → (mövzu, bal, tarix, kilid bayrağı)."""
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    works = {w.enrollment_id: w for w in CourseWork.objects.filter(enrollment__offering=offering)}
    now = timezone.now()
    rows = []
    for e in enrollments:
        work = works.get(e.id)
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                "work": work,
                "locked": bool(work and (now - work.created_at) > MARK_EDIT_WINDOW),
            }
        )
    return rows


# ── Yekun qiymət (imtahana qədər bal) breakdown cədvəli ─────────────────────


def get_final_breakdown(offering):
    """ "Yekun qiymət" tabı: mockup sütunları — Davamiyyət/10, K1-K3 + orta,
    Seminar orta, Sərbəst iş/10, Lab orta, Kurs işi/100, İmtahana qədər bal.

    İmtahana qədər bal KANONİK :func:`gradebook.entry_score_for`-dan gəlir —
    sütunlar informativdir, cəm mənbəyi dəyişmir."""
    from apps.registrar import finals_batch, gradebook
    from apps.registrar.models import LessonKind, LessonMark

    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    kolls = list(
        AssessmentComponent.objects.filter(offering=offering, kind=ComponentKind.KOLLOKVIUM).order_by("order", "name")
    )
    enrollments = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student")
        .order_by("student__last_name", "student__username")
    )
    kscore_map = {}
    if kolls:
        for cs in ComponentScore.objects.filter(component__in=kolls, enrollment__offering=offering):
            kscore_map[(cs.enrollment_id, cs.component_id)] = cs.score
    marks = LessonMark.objects.filter(enrollment__offering=offering).select_related("lesson")
    per_student: dict = {}
    for m in marks:
        agg = per_student.setdefault(m.enrollment_id, {"absent": 0, "sem": [], "lab": []})
        if m.status == "absent":
            agg["absent"] += 1
        if m.score is not None:
            if m.lesson.kind == LessonKind.SEMINAR:
                agg["sem"].append(m.score)
            elif m.lesson.kind == LessonKind.LAB:
                agg["lab"].append(m.score)
    selfwork_totals = {r["enrollment"].id: r["total"] for r in get_selfwork_board(offering)["rows"]}
    works = {w.enrollment_id: w for w in CourseWork.objects.filter(enrollment__offering=offering)}
    lessons_all = list(offering.lessons.all())
    # Məxrəc də TƏK yerdən (tələbənin öz işarələrindən YOX) — bax
    # :func:`exam_eligibility.lesson_hours_for`.
    allowed = exam_eligibility.lesson_hours_for(offering, lessons_all)
    limit_percent = gradebook.absence_limit_percent_for(offering)
    allowed_absence = allowed * Decimal(limit_percent) / Decimal(100)
    warn_at = allowed_absence * Decimal("0.75")
    # TƏK MƏNBƏ (bax :mod:`apps.registrar.exam_eligibility`) — açılış üzrə bir dəfə.
    frozen = exam_eligibility.is_frozen(offering)
    exempt_ids = exam_eligibility.exempt_student_ids(offering.organization, [e.student_id for e in enrollments])
    # Giriş balı üçün komponent/bal/sərbəst-iş oxumaları BİR dəfə (sətir-sətir
    # 4 sorğu idi — bax :mod:`apps.registrar.finals_batch`).
    entry_batch = finals_batch.entry_batch(enrollments)

    def _avg(values):
        return (sum(values) / len(values)).quantize(Decimal("0.1")) if values else None

    rows = []
    for e in enrollments:
        agg = per_student.get(e.id, {"absent": 0, "sem": [], "lab": []})
        kvals = [kscore_map.get((e.id, c.id)) for c in kolls]
        entered = [v for v in kvals if v is not None]
        absence_hours = Decimal(e.absence_hours)
        eligibility = exam_eligibility.resolve(
            absence_hours=absence_hours,
            lesson_hours=allowed,
            allowed_hours=allowed_absence,
            limit_percent=limit_percent,
            exempt=e.student_id in exempt_ids,
            frozen=frozen,
        )
        barred = eligibility["barred"]
        warning = (not frozen) and (not barred) and allowed_absence > 0 and absence_hours >= warn_at
        entry = gradebook.entry_score_for(e, scheme.entry_score_max, **entry_batch.entry_kwargs(e))
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                # Rəsmi "DAVAMİYYƏT BALININ HESABLANMASI" cədvəli — resolver-dən.
                # ⚠️ ``attendance.attendance_score``-u BURADA çağırmayın: istisna /
                # təkrar imtahan / donma qaydası ikinci dəfə yazılmış olur və
                # tələbənin öz ekranı ilə ayrılır (2026-08-31, 2-ci bloker).
                "dav": eligibility["attendance_score"],
                "kvals": kvals,
                "korta": _avg(entered),
                "sorta": _avg(agg["sem"]),
                "lab_orta": _avg(agg["lab"]),
                "selfwork": selfwork_totals.get(e.id, 0),
                "coursework": works.get(e.id),
                "entry": entry,
                "entry_pct": (
                    min(100, int(entry / Decimal(scheme.entry_score_max) * 100)) if scheme.entry_score_max else 0
                ),
                "barred": barred,
                "eligibility": eligibility,
                "warning": warning,
                "absence_hours": e.absence_hours,
            }
        )
    return {
        "kolls": kolls,
        "rows": rows,
        "entry_max": scheme.entry_score_max,
        "allowed_absence": allowed_absence,
    }


# ── Yeni-dərs modalının köməkçiləri (views-dən köçürülüb — modul büdcəsi) ────


def _schedule_slot_model():
    from apps.registrar.models import ScheduleSlot

    return ScheduleSlot


def locked_lesson_kind(offering):
    """Jurnalın dərs tipi kilidi: qrupun cədvəlində YALNIZ BİR növ slot varsa
    (məs. bu jurnal mühazirə jurnalıdır) yeni dərsin növü seçilə bilmir —
    avtomatik həmin növə düşür (istifadəçi tələbi)."""
    kinds = list(_schedule_slot_model().objects.filter(offering=offering).values_list("kind", flat=True).distinct())
    return kinds[0] if len(kinds) == 1 else None


# Mövzu mənbəyi (təsdiqlənmiş sillabus → LMS kursu) ayrıca modula köçürülüb ki,
# bu fayl modul-ölçü büdcəsində (600 sətir) qalsın; adlar geriyə uyğunluq üçün
# buradan da import oluna bilər.
from .journal_topics import (  # noqa: E402,F401  (modulun sonunda — dövr yoxdur)
    SYLLABUS_HOUR_KINDS,
    lesson_topic_choices,
    lesson_topic_meta,
    syllabus_topic_rows,
)

# Qeyd: dərs saatı artıq STANDARD_LESSON_TIMES-dan seçilir (schedule.py) —
# köhnə slot-əsaslı seçici silinib.


def calendar_plan(offering, lessons, today):
    """Sol panel "TƏQVİM PLANI — MÖVZULAR": kursun mövzu planı + hansının
    keçirildiyi (yanında tarix). Planda olmayan mövzulu/mövzusuz dərslər sona
    xronoloji əlavə olunur — müəllim nəyi keçdiyini bir baxışda görür."""
    chrono = sorted(lessons, key=lambda item: (item.date, item.created_at))
    lesson_by_topic = {}
    for lesson in chrono:
        if lesson.topic and lesson.topic not in lesson_by_topic:
            lesson_by_topic[lesson.topic] = lesson

    plan = []
    seen = set()
    for title in lesson_topic_choices(offering):
        lesson = lesson_by_topic.get(title)
        plan.append(
            {
                "title": title,
                "lesson": lesson,
                "covered": lesson is not None,
                "is_today": bool(lesson and lesson.date == today),
            }
        )
        seen.add(title)
    for lesson in chrono:
        if lesson.topic and lesson.topic in seen:
            continue
        # Mövzu qeyd olunmayan dərs: panel MÖVZULAR-dır — dərs tipini (Lecture/
        # Seminar) BAŞLIQ kimi göstərmirik. Mövzu yoxdursa neytral etiket.
        plan.append(
            {
                "title": lesson.topic or _("Mövzu qeyd olunmayıb"),
                "lesson": lesson,
                "covered": True,
                "is_today": lesson.date == today,
            }
        )
        if lesson.topic:
            seen.add(lesson.topic)
    return plan


def journal_teaching_summary(offering):
    """Fənn açılışının dərs-saat mənzərəsi + növ-müəllimləri (bir sorğuda).

    Qaytarır:
      * ``kinds`` — YALNIZ MÖVCUD dərs növləri (mühazirə/seminar/lab); hər biri üçün
        keçirilmiş saat + o növü keçən müəllim(lər)in adı. Yalnız bir növ varsa yalnız
        o görünür (#8); 2 müəllim arasında bölünübsə hər növün öz müəllimi (#9).
      * ``held_total`` keçirilmiş toplam saat, ``total`` fənnin tam saatı,
        ``remaining`` qalan saat (#7). ``over`` — həddi keçibsə True (#6 göstərişi).
    """
    from apps.registrar.models import Lesson, LessonKind

    lessons = list(
        Lesson.objects.filter(offering=offering)
        .select_related("instructor")
        .only("kind", "hours", "instructor__first_name", "instructor__last_name", "instructor__username")
    )
    fallback = offering.instructor
    by_kind: dict = {}
    for lesson in lessons:
        row = by_kind.setdefault(lesson.kind, {"held": 0, "teachers": {}})
        row["held"] += int(lesson.hours or 0)
        inst = lesson.instructor or fallback
        if inst is not None:
            row["teachers"][inst.id] = (inst.get_full_name() or "").strip() or inst.username
    labels = dict(LessonKind.choices)
    order = {"lecture": 0, "seminar": 1, "lab": 2}
    kinds = [
        {
            "kind": kind,
            "label": labels.get(kind, kind),
            "held": data["held"],
            "teachers": list(data["teachers"].values()),
        }
        for kind, data in by_kind.items()
    ]
    kinds.sort(key=lambda k: order.get(k["kind"], 9))
    held_total = sum(k["held"] for k in kinds)
    total = int(offering.lesson_hours or 0)
    return {
        "kinds": kinds,
        "held_total": held_total,
        "total": total,
        "remaining": max(0, total - held_total) if total else None,
        "over": bool(total and held_total > total),
    }


def lesson_teacher_choices(offering):
    """Dərs modalı üçün müəllim namizədləri — açılışın müəllimi + təşkilatın digər
    dərs deyən müəllimləri (fənn 2 müəllim arasında bölünə bilər — mühazirə/seminar)."""
    from django.contrib.auth import get_user_model

    from apps.registrar.models import CourseOffering

    ids = set(
        CourseOffering.objects.filter(organization=offering.organization, instructor__isnull=False).values_list(
            "instructor_id", flat=True
        )
    )
    if offering.instructor_id:
        ids.add(offering.instructor_id)
    users = get_user_model().objects.filter(pk__in=ids).order_by("last_name", "first_name", "username")
    return [{"id": str(u.id), "name": (u.get_full_name() or "").strip() or u.username} for u in users]
