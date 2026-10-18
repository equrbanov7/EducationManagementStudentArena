"""Fənn birləşdirməsi — UNİKALLIQ toqquşmalarının aşkarlanması (2026-10-19).

Birləşmədən sonra hədəf + bütün mənbələr BİR fəndir; ona görə hər qayda «fənn sütunu çıxarılmış
açar üzrə bir neçə sətir» axtarır (mənbələrin ÖZ aralarındakı toqquşma da tutulur).

BLOKLAYAN (``blocking``) — yazı YOXDUR, siyahı linklərlə göstərilir:
* kredit: mənbənin ECTS-i hədəfdən fərqlidir VƏ mənbə üzrə yekun qiymətli (və ya «completed») tələbə var —
  transkript krediti ``offering.subject.ects``-dən oxunduğu üçün keçmiş ÜOMG dəyişərdi;
* açılış: ``uniq_offering_subject_period_group`` → eyni dövr + qrup;
* plan sətri: ``uniq_curriculum_subject_semester`` → eyni plan + semestr (təsdiqlənmiş / baxışdakı plan);
* qeydiyyat: eyni tələbənin eyni dövrdə hər iki fənn üzrə aktiv qeydiyyatı (ikiqat kredit/yekun qiymət);
* sillabus: ``uniq_syllabus_per_subject_period`` (dövr) / ``uniq_syllabus_base_per_subject_author`` (baza);
* fənn qovluğu: ``sf_folder_uniq_subject_owner_period`` / ``…_noperiod``;
* təkrar imtahan: ``registrar_retake_one_active_per_subject`` (aktiv müraciətlər);
* tədris tapşırığı: ``workload.services.tasks._duplicate_row_exists`` (tapşırıq + mövsüm + ixtisas + qruplar).

HƏLL OLUNAN (``resolvable``) — qaralama/qaytarılmış planda eyni semestr: HƏDƏF sətri saxlanılır,
mənbə sətri plandan çıxarılır (tam snapshot audit-ə yazılır, geri qaytarmada bərpa olunur).

DB toqquşması YOXDUR (məlumat): ``GroupElectiveChoice`` (açarı fənnsizdir), sorğu cavabları,
imtahan/sual bankı; imtahan qrupunun təkrar əlaqəsi avtomatik çıxarılır.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Q
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import pgettext

from .models import CourseOffering, CurriculumSubject, Enrollment, RetakeApplication
from .models.curriculum_meta import PlanStatus
from .models.retake import ACTIVE_STATUSES

_CTX = "registrar.subject_merge"

#: Planın sətri çıxarıla bilən statusları (təsdiq zəncirindən kənar).
EDITABLE_PLAN_STATUSES = (PlanStatus.DRAFT, PlanStatus.RETURNED)
#: Bir qayda üzrə göstərilən maksimal sətir (qalanı «və daha N» kimi sayılır).
LIST_LIMIT = 50


def period_label(period) -> str:
    if period is None:
        return pgettext(_CTX, "Dövrsüz")
    year = (getattr(period, "academic_year", "") or "").strip()
    name = (getattr(period, "name", "") or "").strip()
    return name if year and year in name else " ".join(part for part in (year, name) if part)


def group_label(group) -> str:
    if group is None:
        return pgettext(_CTX, "Qrupsuz")
    return (getattr(group, "code", "") or "").strip() or group.name


def person_label(user) -> str:
    if user is None:
        return "—"
    return (user.get_full_name() or "").strip() or user.get_username()


def _journal_link(offering) -> dict:
    return {
        "label": f"{offering.subject.code} · {group_label(offering.group)}",
        "url": reverse("registrar:journal_detail", kwargs={"offering_id": offering.pk}),
    }


def _plan_link(curriculum) -> dict:
    query = urlencode({"section": "curriculum-editor", "cu_program": curriculum.program_id, "cu_plan": curriculum.pk})
    return {"label": curriculum.name or str(curriculum.program), "url": f"{reverse('accounts:profile')}?{query}"}


def _item(code, message, *, ids=(), links=()):
    return {"code": code, "message": message, "ids": [str(pk) for pk in ids], "links": list(links)}


def _buckets(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    return {bucket: items for bucket, items in grouped.items() if len(items) > 1}


# ── Qaydalar ────────────────────────────────────────────────────────────────


def _offerings(organization, subject_ids, blocking, warnings):
    rows = list(
        CourseOffering._base_manager.filter(organization=organization, subject_id__in=subject_ids)
        .select_related("subject", "period", "group")
        .order_by("period__start_date", "group__name", "subject__code")
    )
    for (_period_id, group_id), items in _buckets(rows, lambda row: (row.period_id, row.group_id)).items():
        first = items[0]
        if group_id is None:
            warnings.append(
                pgettext(_CTX, "%(period)s: hər iki fənn üzrə qrupsuz açılış var — birləşmədən sonra ikisi qalır.")
                % {"period": period_label(first.period)}
            )
            continue
        blocking.append(
            _item(
                "offering",
                pgettext(_CTX, "%(period)s · %(group)s: hər iki fənn üzrə açılış var — əvvəlcə birini ləğv edin.")
                % {"period": period_label(first.period), "group": group_label(first.group)},
                ids=[row.pk for row in items],
                links=[_journal_link(row) for row in items],
            )
        )


def _curriculum(organization, target_id, subject_ids, source_order, blocking, resolvable, warnings):
    rows = list(
        CurriculumSubject.objects.filter(organization=organization, subject_id__in=subject_ids)
        .select_related("curriculum", "curriculum__program", "subject")
        .order_by("curriculum__name", "semester_number", "pk")
    )
    for (_curriculum_id, semester), items in _buckets(
        rows, lambda row: (row.curriculum_id, row.semester_number)
    ).items():
        plan = items[0].curriculum
        values = {"plan": plan.name or str(plan.program), "status": plan.get_status_display(), "semester": semester}
        if plan.status in EDITABLE_PLAN_STATUSES:
            ranked = sorted(items, key=lambda row: (row.subject_id != target_id, source_order.get(row.subject_id, 99)))
            keep, drop = ranked[0], ranked[1:]
            resolvable.append(
                {
                    "code": "curriculum_row",
                    "message": pgettext(
                        _CTX,
                        "Plan «%(plan)s» (%(status)s) · %(semester)s-ci semestr: hər iki fənn sətri var — "
                        "saxlanılan fənnin sətri qalır, digəri plandan çıxarılır.",
                    )
                    % values,
                    "keep": str(keep.pk),
                    "drop": [str(row.pk) for row in drop],
                    "links": [_plan_link(plan)],
                }
            )
            continue
        blocking.append(
            _item(
                "curriculum_row",
                pgettext(
                    _CTX,
                    "Plan «%(plan)s» (%(status)s) · %(semester)s-ci semestr: hər iki fənn sətri var — "
                    "bu statusda plan dəyişmir; əvvəlcə yeni versiyada birini çıxarın.",
                )
                % values,
                ids=[row.pk for row in items],
                links=[_plan_link(plan)],
            )
        )
    by_plan = defaultdict(set)
    for row in rows:
        by_plan[row.curriculum].add(row.semester_number)
    for plan, semesters in by_plan.items():
        plan_subjects = {row.subject_id for row in rows if row.curriculum_id == plan.pk}
        if len(plan_subjects) > 1 and len(semesters) > 1:
            warnings.append(
                pgettext(
                    _CTX,
                    "Plan «%(plan)s»: fənlər müxtəlif semestrlərdədir — birləşmədən sonra fənn planda %(n)s dəfə olacaq.",
                )
                % {"plan": plan.name or str(plan.program), "n": len(semesters)}
            )


def _enrollments(organization, subject_ids, blocking):
    rows = list(
        Enrollment.objects.filter(
            organization=organization, offering__subject_id__in=subject_ids, superseded_by__isnull=True
        )
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related("student", "offering__period", "offering__subject", "offering__group")
        .order_by("student__last_name", "student__first_name", "offering__period__start_date")
    )
    graded = set(
        django_apps.get_model("registrar", "FinalGrade")
        .objects.filter(enrollment_id__in=[row.pk for row in rows])
        .values_list("enrollment_id", flat=True)
    )
    found = []
    for _key, items in _buckets(rows, lambda row: (row.student_id, row.offering.period_id)).items():
        if len({row.offering.subject_id for row in items}) < 2:
            continue  # eyni fənn daxilində köhnə ikiqat qeydiyyat bu əməliyyatın işi deyil
        first = items[0]
        message = pgettext(
            _CTX,
            "%(student)s · %(period)s: eyni dövrdə hər iki fənn üzrə aktiv qeydiyyat var — əvvəlcə birini bağlayın.",
        ) % {"student": person_label(first.student), "period": period_label(first.offering.period)}
        if sum(1 for row in items if row.pk in graded) > 1:
            message += " " + pgettext(_CTX, "Hər ikisində yekun qiymət yazılıb.")
        found.append(
            _item(
                "enrollment",
                message,
                ids=[row.pk for row in items],
                links=[_journal_link(row.offering) for row in items],
            )
        )
    blocking.extend(found)


def _syllabi(organization, subject_ids, blocking):
    Syllabus = django_apps.get_model("syllabus", "Syllabus")
    rows = list(
        Syllabus._base_manager.filter(organization=organization, subject_id__in=subject_ids, offering__isnull=True)
        .select_related("period", "author", "subject")
        .order_by("pk")
    )
    per_period = [row for row in rows if row.period_id is not None]
    for _key, items in _buckets(per_period, lambda row: row.period_id).items():
        blocking.append(
            _item(
                "syllabus_period",
                pgettext(
                    _CTX, "Sillabus · %(period)s: hər iki fənnin semestr sillabusu var — əvvəlcə birini ləğv edin."
                )
                % {"period": period_label(items[0].period)},
                ids=[row.pk for row in items],
            )
        )
    base = [row for row in rows if row.period_id is None]
    for _key, items in _buckets(base, lambda row: row.author_id).items():
        blocking.append(
            _item(
                "syllabus_base",
                pgettext(
                    _CTX,
                    "Sillabus (baza) · %(author)s: hər iki fənn üzrə baza sillabusu var — əvvəlcə birini ləğv edin.",
                )
                % {"author": person_label(items[0].author)},
                ids=[row.pk for row in items],
            )
        )


def _folders(organization, subject_ids, blocking):
    SubjectFolder = django_apps.get_model("subject_folder", "SubjectFolder")
    rows = list(
        SubjectFolder._base_manager.filter(organization=organization, subject_id__in=subject_ids)
        .select_related("owner", "period")
        .order_by("pk")
    )
    for _key, items in _buckets(rows, lambda row: (row.owner_id, row.period_id)).items():
        blocking.append(
            _item(
                "subject_folder",
                pgettext(
                    _CTX,
                    "Fənn qovluğu · %(owner)s · %(period)s: hər iki fənn üzrə qovluq var — əvvəlcə birini ləğv edin.",
                )
                % {"owner": person_label(items[0].owner), "period": period_label(items[0].period)},
                ids=[row.pk for row in items],
            )
        )


def _retakes(organization, subject_ids, blocking):
    rows = list(
        RetakeApplication.objects.filter(
            organization=organization,
            subject_id__in=subject_ids,
            status__in=[status.value for status in ACTIVE_STATUSES],
        )
        .select_related("student")
        .order_by("pk")
    )
    for _key, items in _buckets(rows, lambda row: row.student_id).items():
        blocking.append(
            _item(
                "retake",
                pgettext(
                    _CTX,
                    "Təkrar imtahan · %(student)s: hər iki fənn üzrə aktiv müraciət var — əvvəlcə birini bağlayın.",
                )
                % {"student": person_label(items[0].student)},
                ids=[row.pk for row in items],
            )
        )


def _task_rows(organization, subject_ids, blocking):
    TeachingTaskRow = django_apps.get_model("workload", "TeachingTaskRow")
    rows = list(
        TeachingTaskRow._base_manager.filter(organization=organization, subject_id__in=subject_ids)
        .select_related("task", "specialty")
        .prefetch_related("groups")
        .order_by("pk")
    )

    def key(row):
        return (row.task_id, row.season, row.specialty_id, frozenset(group.pk for group in row.groups.all()))

    for _key, items in _buckets(rows, key).items():
        first = items[0]
        blocking.append(
            _item(
                "task_row",
                pgettext(
                    _CTX,
                    "Tədris tapşırığı «%(task)s» · %(groups)s: eyni ixtisas və qruplar üçün hər iki fənn sətri var — "
                    "əvvəlcə birini silin.",
                )
                % {
                    "task": str(first.task),
                    "groups": ", ".join(sorted(group_label(group) for group in first.groups.all())) or "—",
                },
                ids=[row.pk for row in items],
            )
        )


def _credits(organization, target, sources, blocking):
    """Kredit fərqi + QİYMƏTLƏNMİŞ sətir → blok (review 2026-10-19).

    Transkript krediti ``offering.subject.ects``-dən oxunur (``transcript._credit_for``): fərqli ECTS-li
    mənbənin açılışları hədəfə keçsə, keçmiş qiymətlər hədəfin krediti ilə sayılar — qazanılmış kredit və
    ÜOMG geriyə dönük dəyişərdi. Yekun qiyməti (və ya «completed» qeydiyyatı) olan tələbə yoxdursa, fərq
    yalnız xəbərdarlıqdır (``subject_merge._warnings``).
    """
    FinalGrade = django_apps.get_model("registrar", "FinalGrade")
    for source in sources:
        if source.ects == target.ects:
            continue
        graded = Enrollment.objects.filter(organization=organization, offering__subject_id=source.pk)
        graded_ids = FinalGrade.objects.filter(enrollment__in=graded).values("enrollment_id")
        students = (
            graded.filter(Q(pk__in=graded_ids) | Q(status=Enrollment.Status.COMPLETED))
            .values("student_id")
            .distinct()
            .count()
        )
        if not students:
            continue
        blocking.append(
            _item(
                "credit_mismatch",
                pgettext(
                    _CTX,
                    "Kredit fərqi: %(source)s — %(source_ects)s ECTS, saxlanılan %(target)s — %(target_ects)s ECTS. "
                    "%(source)s üzrə %(n)s tələbənin yekun qiyməti var — birləşmə onların keçmiş transkriptində "
                    "krediti və ÜOMG-ni dəyişərdi. Əvvəlcə ECTS-i uyğunlaşdırın və ya hər iki kartı saxlayın.",
                )
                % {
                    "source": source.code,
                    "source_ects": source.ects,
                    "target": target.code,
                    "target_ects": target.ects,
                    "n": students,
                },
                ids=[source.pk],
            )
        )


def detect(organization, target, sources) -> dict:
    """Toqquşmalar: ``blocking`` (yazı yoxdur), ``resolvable`` (plan sətri), ``warnings`` (məlumat)."""
    subject_ids = [target.pk] + [source.pk for source in sources]
    source_order = {source.pk: index for index, source in enumerate(sources)}
    blocking, resolvable, warnings = [], [], []
    _credits(organization, target, sources, blocking)
    _offerings(organization, subject_ids, blocking, warnings)
    _curriculum(organization, target.pk, subject_ids, source_order, blocking, resolvable, warnings)
    _enrollments(organization, subject_ids, blocking)
    _syllabi(organization, subject_ids, blocking)
    _folders(organization, subject_ids, blocking)
    _retakes(organization, subject_ids, blocking)
    _task_rows(organization, subject_ids, blocking)
    return {"blocking": blocking, "resolvable": resolvable, "warnings": warnings}


__all__ = ["EDITABLE_PLAN_STATUSES", "LIST_LIMIT", "detect", "group_label", "period_label", "person_label"]
