"""Elektron jurnal əlavə bölmələri: aralıq qiymətləndirmə + Sərbəst iş + Kurs işi.

Aralıq qiymətləndirmə keçmiş dövrlərdə 3 kollokvium, 2026/2027-dən isə TƏK 20 ballıq
midterm-dir (rejim :mod:`apps.registrar.interim_assessment`, komponentlər və tab grid-i
:mod:`apps.registrar.interim_components`). Hər ikisi mövcud komponent mexanizmi üzərində
işləyir (``AssessmentComponent`` kind=KOLLOKVIUM; ballar ``ComponentScore``-da — bal yazma
İmtahan Mərkəzinin pəncərəsi ilə idarə olunur). Sərbəst iş sillabusun strukturunu
izləyir (1 × 10 / 2 × 5 / 10 × 1; köhnə jurnallarda mövzu-çeklisti): cəm (≤10)
avtomatik giriş balına ÜSTƏGƏL olunur — kanonik qayda ``selfwork_points``; lövhə —
köçürülmüş "arxiv" balı da daxil — ``selfwork_board``, yazı servisləri
``selfwork_marks``, struktur ``selfwork_structure`` modulundadır. Kurs işi
giriş balından kənar ayrıca 0-100 qiymətdir.

Kilid qaydaları: jurnal kilidli (təsdiqdə/yekunlaşıb) → heç nə yazılmır; sərbəst
işdə boş xanaya təhvil/bal hər zaman yazılır, GERİ ALMA/DƏYİŞMƏ yalnız 2 saat içində
(bal silmə saxtakarlığına qarşı); kurs işi yazılışdan 2 saat sonra dondurulur.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.registrar import absence_limit, exam_eligibility, grade_audit
from apps.registrar.gradebook import MARK_EDIT_WINDOW, journal_is_locked

# Keçmiş dövrlərin kollokvium sabitləri (geriyə uyğunluq) — rejim qərarı ``interim_assessment``-dədir.
from apps.registrar.interim_assessment import KOLLOKVIUM_COUNT, KOLLOKVIUM_MAX  # noqa: F401

# Aralıq qiymətləndirmə (kollokvium K1-K3 / midterm): rejimə görə komponent qurulması və
# müəllim tabının grid-i modul-ölçü büdcəsinə görə ``interim_components``-dədir; adlar
# buradan re-eksport olunur — çağıranlar üçün API dəyişməyib.
from apps.registrar.interim_components import (  # noqa: F401
    display_components,
    ensure_kollokviums,
    get_kollokvium_grid,
    interim_score_options,
    kollokvium_columns_only,
    set_kollokvium_date,
)
from apps.registrar.models import ComponentScore, CourseWork, Enrollment

# Sərbəst iş lövhəsi + yazı servisləri modul-ölçü büdcəsinə görə ayrıca
# modullardadır; adlar buradan re-eksport olunur — çağıranlar üçün API dəyişməyib.
from apps.registrar.selfwork_board import (  # noqa: F401
    SELF_WORK_MAX_TOPICS,
    get_selfwork_board,
)
from apps.registrar.selfwork_marks import (  # noqa: F401
    add_selfwork_topic,
    delete_selfwork_topic,
    set_selfwork_mark,
)
from apps.registrar.selfwork_structure import ensure_selfwork_component  # noqa: F401

COURSE_WORK_MAX = Decimal("100")


def _to_decimal(raw):
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ── Sərbəst iş (sillabus strukturu / çeklist) ────────────────────────────────
#
# Yazı servisləri (mövzu əlavə/sil, işarə/bal) modul-ölçü büdcəsinə görə
# ``selfwork_marks``-dadır, struktur + SELF_WORK komponenti ``selfwork_structure``-da;
# adlar yuxarıda re-eksport olunur — çağıranlar üçün API dəyişməyib.


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
    """ "Yekun qiymət" tabı: mockup sütunları — Davamiyyət/10, K1-K3 + orta (keçmiş dövrlər)
    və ya Midterm/20 (2026/2027-dən), Seminar orta, Sərbəst iş/10, Lab orta, Kurs işi/100,
    İmtahana qədər bal.

    UNEC «Yekun qiymət» kimi audit sütunları (2026-09-25): Auditoriya saatı (plan =
    buraxılış qərarının KANONİK məxrəci ``exam_eligibility.lesson_hours_for``, keçirilib =
    bu günə qədərki dərslərin saatı), Buraxılan saat (``Enrollment.absence_hours``) və
    Qayıb % (buraxılan ÷ plan, 1 onluq) — hamısı artıq oxunmuş datadan, ƏLAVƏ SORĞU YOXDUR.

    İmtahana qədər bal KANONİK :func:`gradebook.entry_score_for`-dan gəlir —
    sütunlar informativdir, cəm mənbəyi dəyişmir."""
    from apps.registrar import finals_batch, gradebook
    from apps.registrar.models import LessonKind, LessonMark

    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    interim, kolls = display_components(offering)
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
    # Sərbəst iş sütunu lövhənin CƏMİ-dir (arxiv qaydası daxil) — struktur/sillabus oxunmur.
    selfwork_totals = {
        r["enrollment"].id: r["total"] for r in get_selfwork_board(offering, with_structure=False)["rows"]
    }
    works = {w.enrollment_id: w for w in CourseWork.objects.filter(enrollment__offering=offering)}
    lessons_all = list(offering.lessons.all())
    # Məxrəc də TƏK yerdən (bax :func:`exam_eligibility.lesson_hours_for`); başlıq həddi açılış-
    # səviyyəli, SƏTİR qərarı isə TƏLƏBƏNİN ÖZ həddi ilə (F-06 / 2026-09-14) — tək toplu sorğu.
    allowed = exam_eligibility.lesson_hours_for(offering, lessons_all)
    today = timezone.localdate()
    held_hours = sum(int(lesson.hours or 0) for lesson in lessons_all if lesson.date is None or lesson.date <= today)
    allowed_absence = absence_limit.allowed_absence_hours(offering, lessons_all)
    org_id = offering.organization_id
    row_limits = absence_limit.row_limits(organization_id=org_id, enrollments=enrollments, total_hours=allowed)
    # TƏK MƏNBƏ (bax :mod:`apps.registrar.exam_eligibility`) — açılış üzrə bir dəfə.
    frozen = exam_eligibility.is_frozen(offering)
    exempt_ids = exam_eligibility.exempt_student_ids(offering.organization, [e.student_id for e in enrollments])
    # Giriş balı üçün komponent/bal/sərbəst-iş oxumaları BİR dəfə (sətir-sətir
    # 4 sorğu idi — bax :mod:`apps.registrar.finals_batch`).
    entry_batch = finals_batch.entry_batch(enrollments)

    def _avg(values):
        return (sum(values) / len(values)).quantize(Decimal("0.1")) if values else None

    def _pct(hours):
        # Qayıb % — buraxılış qaydası ilə EYNİ məxrəc; məxrəc yoxdursa «—» (0% yalan olardı).
        return (Decimal(hours) * 100 / allowed).quantize(Decimal("0.1")) if allowed > 0 else None

    rows = []
    for e in enrollments:
        agg = per_student.get(e.id, {"absent": 0, "sem": [], "lab": []})
        kvals = [kscore_map.get((e.id, c.id)) for c in kolls]
        entered = [v for v in kvals if v is not None]
        absence_hours = Decimal(e.absence_hours)
        row_limit = row_limits[e.student_id]
        eligibility = exam_eligibility.resolve(
            absence_hours=absence_hours,
            lesson_hours=allowed,
            allowed_hours=row_limit.allowed_hours,
            limit_percent=row_limit.percent,
            exempt=e.student_id in exempt_ids,
            frozen=frozen,
        )
        barred = eligibility["barred"]
        warning = absence_limit.near_limit(absence_hours, row_limit, frozen=frozen, barred=barred)
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
                "absence_pct": _pct(absence_hours),
                "allowed_absence": row_limit.allowed_hours,  # tələbənin ÖZ həddi (F-06)
            }
        )
    return {
        "interim": interim,
        "kolls": kolls,
        "rows": rows,
        "entry_max": scheme.entry_score_max,
        "allowed_absence": allowed_absence,
        "lesson_hours": allowed,  # Auditoriya saatı — plan (buraxılışın kanonik məxrəci)
        "held_hours": held_hours,  # Auditoriya saatı — bu günə qədər keçirilib
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
    from django.utils import timezone

    from apps.registrar.models import Lesson, LessonKind

    lessons = list(
        Lesson.objects.filter(offering=offering)
        .select_related("instructor")
        .only("kind", "hours", "date", "instructor__first_name", "instructor__last_name", "instructor__username")
    )
    fallback = offering.instructor
    today = timezone.localdate()
    by_kind: dict = {}
    scheduled_total = 0
    for lesson in lessons:
        row = by_kind.setdefault(lesson.kind, {"held": 0, "teachers": {}})
        hours = int(lesson.hours or 0)
        scheduled_total += hours
        # «Keçirilmiş» yalnız bu günə qədərki dərslərdir; gələcək tarixli dərs
        # planlaşdırılmışdır (QA 2026-09-05 JOURNAL-TEACHER-11).
        if lesson.date is None or lesson.date <= today:
            row["held"] += hours
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
        # Bütün (gələcək daxil) dərslərin saatı — saat həddi bununla yoxlanır.
        "scheduled_total": scheduled_total,
        "total": total,
        "remaining": max(0, total - scheduled_total) if total else None,
        "over": bool(total and scheduled_total > total),
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
