"""Paylaşılan səhifə kontekstləri (U12) — standalone səhifə + profil bölməsi.

Registrar səhifələrinin (jurnal siyahısı, dərs cədvəli, akademik təqvim,
qiymət təsdiqləri, analitika) kontekst-qurucuları burada yaşayır ki, eyni data
HƏM `/jurnal/...` standalone görünüşlərində, HƏM DƏ profil kabinetinin sağ
panelində (``?section=...``) istifadə olunsun — kod dublikasiyası yoxdur.

``embedded=True`` rejimində naviqasiya linkləri profil shell-inin içində qalır
(``/accounts/profile/?section=X&...``) — istifadəçi sidebar-ı itirmir.
Performans: hər kontekst yalnız aktiv bölmə üçün qurulur (lazy, stage4 gating).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from apps.registrar import analytics, journal_scope, schedule
from apps.registrar.models import CourseOffering, StudentAcademicRecord


def _profile_section_prefix(section: str) -> str:
    return f"{reverse('accounts:profile')}?section={section}&"


def journal_list_context(user, request=None) -> dict:
    """The teacher's own offerings — entry points into each journal.

    Mockup filter zolağı TAM işləkdir: TƏDRİS İLİ (``?year=``), YARIM İL
    (``?period=``), dərs tipi pilləri (``?kind=`` — cədvəl slotlarından).
    Hər offering-ə dərs tipi etiketi və magistratura (axşam) bayrağı bağlanır."""
    from django.db.models import Count, Q

    from apps.registrar import corrections as corrections_service
    from apps.registrar.models import Lesson, ScheduleSlot, SlotKind
    from apps.registrar.schedule import EVENING_START

    # Korrektorlar (İKT rəhbəri / admin / superadmin — journal.correct icazəsi) BÜTÜN
    # təşkilatın jurnallarını görür (öz dərsi olmasa da); adi müəllim yalnız özününkünü.
    can_correct = bool(request is not None and corrections_service.can_correct_journal(request))
    organization = getattr(request, "organization", None) if request is not None else None
    base_qs = CourseOffering.objects.filter(is_active=True)
    # Jurnal siyahısını idarə edən (koordinator/dekanlıq — `journal.roster`) öz
    # ALT-AĞACININ jurnallarını görür ki, «alt qrupdan tələbə əlavə et»
    # düyməsinə çata bilsin. Korrektordan fərqi: əhatə org-wide DEYİL.
    from apps.registrar import guest_roster

    can_roster = bool(
        request is not None and organization is not None and guest_roster.can_manage_roster(user, organization)
    )
    if can_correct and organization is not None:
        base_qs = base_qs.filter(organization=organization)
        is_broad = True
    elif can_roster:
        # Əhatə üzrə görünən jurnallar YALNIZ aktiv cari dövrdən gəlir: köçürülmüş
        # tarixi semestrlərin jurnalı koordinatorun siyahısında ÇIXMAMALIDIR (əks
        # halda düymə oradadır və köhnə transkript dəyişər — bax guest_roster.
        # assert_roster_open). Müəllimin ÖZ jurnalları toxunulmaz qalır: onun
        # tarixçəsi dövr süzgəcindən keçmir.
        scoped_groups = guest_roster.scoped_group_queryset(user, organization)
        rosterable = Q(group__in=scoped_groups, period__is_current=True, period__is_active=True)
        base_qs = base_qs.filter(organization=organization).filter(Q(instructor=user) | rosterable)
        is_broad = True
    else:
        # Fənni TƏHVİL VERMİŞ köhnə müəllim jurnalı YALNIZ-OXU görməyə davam edir
        # (bax apps/registrar/handover.is_handover_observer). Siyahıda sətir
        # olmasaydı, ona gedən yeganə keçid itərdi və «bal yazan mən idim, indi
        # görə bilmirəm» vəziyyəti yaranardı. Yazma hüququ onsuz da
        # `is_direct_editor`-dədir və təhvildən sonra False-dur.
        from apps.registrar.handover import observer_offering_ids

        observed = observer_offering_ids(user, organization) if organization is not None else set()
        base_qs = (
            base_qs.filter(Q(instructor=user) | Q(pk__in=observed)) if observed else base_qs.filter(instructor=user)
        )
        is_broad = False

    offerings = list(
        base_qs.select_related(
            "subject",
            "period",
            "group",
            "group__parent",
            "group__parent__parent",
            "group__parent__parent__parent",
            "instructor",
        )
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__status="enrolled")))
        .order_by("-period__start_date", "subject__code")
    )

    # Cədvəl slotlarından: offering → dərs tip(lər)i + axşam (magistratura) bayrağı.
    kind_labels = dict(SlotKind.choices)
    kind_order = {value: index for index, (value, _) in enumerate(SlotKind.choices)}
    kinds_by_offering: dict = {}
    evening_offerings: set = set()
    for offering_id, kind, start_time in ScheduleSlot.objects.filter(offering__in=offerings).values_list(
        "offering_id", "kind", "start_time"
    ):
        kinds_by_offering.setdefault(offering_id, set()).add(kind)
        if start_time >= EVENING_START:
            evening_offerings.add(offering_id)
    # Köçürülmüş (legacy) açılışların cədvəl slotu YOXDUR — tip yalnız ``Lesson.kind``-dadır
    # (köçürmə 293,070 dərsə mühazirə/seminar/lab yazır).  Tələbə kabineti onsuz da dərsdən
    # oxuyurdu, jurnal siyahısı isə yalnız slota baxdığı üçün «—» göstərirdi.
    # ``LessonKind`` dəyərləri ``SlotKind`` ilə eynidir (lecture/seminar/lab); naməlum dəyər
    # süzülür ki, etiket heç vaxt KeyError verməsin.
    for offering_id, kind in (
        Lesson.objects.filter(offering__in=offerings).values_list("offering_id", "kind").distinct()
    ):
        if kind in kind_labels:
            kinds_by_offering.setdefault(offering_id, set()).add(kind)
    for offering in offerings:
        # Deterministik sıra: ``SlotKind.choices`` ardıcıllığı (mühazirə → seminar → lab).
        kinds = sorted(kinds_by_offering.get(offering.id, ()), key=lambda k: kind_order.get(k, len(kind_order)))
        offering.slot_kinds = kinds
        offering.kind_label = " · ".join(str(kind_labels[k]) for k in kinds) if kinds else ""
        offering.is_evening = offering.id in evening_offerings

    periods = sorted({o.period for o in offerings if o.period}, key=lambda p: p.start_date, reverse=True)
    for p in periods:
        p.year_label = p.year_display  # "2025/2026" formatı (AcademicPeriod.format_year)
        p.season_label = _season_label(p)
    # Filtr üçün RAW academic_year dəyəri saxlanılır (GET matching xam mətnə görədir),
    # yalnız görünən etiket normallaşdırılır.
    year_label_map = {p.academic_year: p.year_display for p in periods}
    years = sorted(year_label_map, reverse=True)
    year_choices = [{"value": y, "label": year_label_map[y]} for y in years]

    # YARIM İL = fəsil (Payız/Yaz/Yay) — TƏKRAR YOX (çox il olsa da hər fəsil bir dəfə).
    _season_order = {"Payız": 0, "Yaz": 1, "Yay": 2}
    season_choices = sorted({p.season_label for p in periods}, key=lambda s: _season_order.get(s, 9))

    selected_year = ""
    selected_season = ""
    selected_kind = ""
    explicit_filter = False
    if request is not None:
        explicit_filter = "year" in request.GET or "season" in request.GET
        selected_year = (request.GET.get("year") or "").strip()
        if selected_year not in years:
            selected_year = ""
        selected_season = (request.GET.get("season") or "").strip()
        if selected_season not in season_choices:
            selected_season = ""
        selected_kind = (request.GET.get("kind") or "").strip()
        if selected_kind not in dict(SlotKind.choices):
            selected_kind = ""

    # Avto-seçim YALNIZ müəllim görünüşü üçün: cari semestr (il + fəsil). Korrektor
    # (geniş) görünüşdə avto-seçim YOX — İKT/admin DEFAULT bütün jurnalları görsün.
    if not is_broad and not explicit_filter and periods:
        current = _current_semester(periods)
        if current is not None:
            selected_year = current.academic_year
            selected_season = current.season_label

    # ── Korrektor (geniş) görünüş üçün əlavə filtrlər: müəllim, qrup, fakültə,
    # kafedra, mətn axtarışı. Seçim siyahıları TAM dəstdən (illik süzgəcdən əvvəl)
    # qurulur ki, dropdown-lar həmişə mövcud variantları göstərsin. Fakültə/kafedra
    # OrgUnit ata-zəncirindən (path) alınır — organizations importu yoxdur (dövr yox).
    def _ancestor_of(unit, types):
        node = unit
        while node is not None:
            if getattr(node, "unit_type", None) in types:
                return node
            node = getattr(node, "parent", None)
        return None

    teacher_choices, group_choices, faculty_choices, dept_choices = [], [], [], []
    selected_teacher = selected_group = selected_faculty = selected_dept = ""
    query = ""
    if is_broad:
        seen_t, seen_g, seen_f, seen_d = set(), set(), set(), set()
        for o in offerings:
            if o.instructor_id and o.instructor_id not in seen_t:
                seen_t.add(o.instructor_id)
                label = (o.instructor.get_full_name() or o.instructor.username) if o.instructor else ""
                teacher_choices.append({"value": str(o.instructor_id), "label": label})
            g = o.group
            if g is not None and g.id not in seen_g:
                seen_g.add(g.id)
                group_choices.append({"value": str(g.id), "label": g.name})
            fac = _ancestor_of(g, ("faculty", "deanery")) if g is not None else None
            if fac is not None and fac.id not in seen_f:
                seen_f.add(fac.id)
                faculty_choices.append({"value": str(fac.id), "label": fac.name})
            dep = _ancestor_of(g, ("chair", "department")) if g is not None else None
            if dep is not None and dep.id not in seen_d:
                seen_d.add(dep.id)
                dept_choices.append({"value": str(dep.id), "label": dep.name})
        for choices in (teacher_choices, group_choices, faculty_choices, dept_choices):
            choices.sort(key=lambda c: c["label"].lower())
        if request is not None:
            selected_teacher = (request.GET.get("teacher") or "").strip()
            selected_group = (request.GET.get("group") or "").strip()
            selected_faculty = (request.GET.get("faculty") or "").strip()
            selected_dept = (request.GET.get("department") or "").strip()
            query = (request.GET.get("q") or "").strip()

    if selected_year:
        offerings = [o for o in offerings if o.period and o.period.academic_year == selected_year]
    if selected_season:
        offerings = [o for o in offerings if o.period and _season_label(o.period) == selected_season]
    if selected_kind:
        offerings = [o for o in offerings if selected_kind in o.slot_kinds]
    if selected_teacher:
        offerings = [o for o in offerings if str(o.instructor_id) == selected_teacher]
    if selected_group:
        offerings = [o for o in offerings if o.group_id and str(o.group_id) == selected_group]
    if selected_faculty:
        offerings = [o for o in offerings if o.group and o.group.path and selected_faculty in o.group.path.split("/")]
    if selected_dept:
        offerings = [o for o in offerings if o.group and o.group.path and selected_dept in o.group.path.split("/")]
    if query:
        ql = query.lower()
        offerings = [
            o
            for o in offerings
            if ql in f"{o.subject.code} {o.subject.name} "
            f"{(o.instructor.get_full_name() or o.instructor.username) if o.instructor else ''}".lower()
        ]

    def _sel_label(choices, val):
        return next((c["label"] for c in choices if c["value"] == val), "")

    # "Sıfırla" düyməsi yalnız bir filtr aktivdirsə göstərilir.
    has_filters = any(
        [
            selected_year,
            selected_season,
            selected_kind,
            selected_teacher,
            selected_group,
            selected_faculty,
            selected_dept,
            query,
        ]
    )

    # Səhifələmə (İKT rəhbəri bütün offering-ləri görür → çox sətir). Filtr
    # querystring-i qorunur (page istisna) ki, keçidlər filtri saxlasın.
    from django.core.paginator import Paginator

    paginator = Paginator(offerings, 20)
    page_obj = paginator.get_page(request.GET.get("page") if request is not None else None)
    row_offset = page_obj.start_index() - 1 if page_obj else 0
    querystring = ""
    if request is not None:
        params = request.GET.copy()
        params.pop("page", None)
        querystring = params.urlencode()

    return {
        "offerings": list(page_obj),
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "row_offset": row_offset,
        "journal_querystring": querystring,
        "journal_has_filters": has_filters,
        "journal_years": year_choices,
        "journal_selected_year": selected_year,
        "journal_seasons": season_choices,
        "journal_selected_season": selected_season,
        "journal_kinds": SlotKind.choices,
        "journal_selected_kind": selected_kind,
        "teacher_label": user.get_full_name() or user.username,
        # Korrektor (İKT rəhbəri/admin) geniş görünüşü + əlavə filtrlər.
        "journal_is_broad": is_broad,
        "journal_teachers": teacher_choices,
        "journal_selected_teacher": selected_teacher,
        "journal_groups": group_choices,
        "journal_selected_group": selected_group,
        "journal_faculties": faculty_choices,
        "journal_selected_faculty": selected_faculty,
        "journal_departments": dept_choices,
        "journal_selected_department": selected_dept,
        "journal_query": query,
        # Searchable-picker preselection üçün cari seçimin adı (AJAX picker setValue).
        "journal_selected_teacher_label": _sel_label(teacher_choices, selected_teacher),
        "journal_selected_group_label": _sel_label(group_choices, selected_group),
        "journal_selected_faculty_label": _sel_label(faculty_choices, selected_faculty),
        "journal_selected_department_label": _sel_label(dept_choices, selected_dept),
    }


def _season_label(period) -> str:
    """Yarımilin fəsil adı (Payız / Yaz / Yay) — tək mənbə `schedule.season_label`."""
    return schedule.season_label(period)


def _current_semester(periods):
    """Bu günə uyğun yarımil: tarixə düşən period; yoxdursa fəsil qaydası
    (sentyabr–yanvar → Payız, fevral–iyun → Yaz, iyul–avqust → Yay)."""
    today = timezone.localdate()
    containing = [p for p in periods if p.start_date <= today <= p.end_date]
    if containing:
        return containing[0]
    month = today.month
    if month >= 9 or month == 1:
        season = "Payız semestri"
    elif month <= 6:
        season = "Yaz semestri"
    else:
        season = "Yay semestri"
    matching = [p for p in periods if p.season_label == season and p.start_date <= today]
    return matching[0] if matching else periods[0]


def calendar_context(organization) -> dict:
    """Semesters with registration/exam-session window states."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    today = timezone.localdate()
    periods = [
        {
            "period": period,
            "is_running": period.start_date <= today <= period.end_date,
            "registration_state": period.registration_state,
            "exam_session_state": period.exam_session_state,
        }
        for period in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")
    ]
    return {"has_context": True, "periods": periods, "today": today}


def analytics_context(request, organization, *, embedded=False) -> dict:
    """Analytics dashboard: period picker + batched aggregation."""
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    periods = list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"))

    requested = (request.GET.get("period") or "").strip()
    period = None
    if requested:
        period = next((p for p in periods if str(p.id) == requested), None)
    if period is None:
        period = next((p for p in periods if p.is_current), periods[0] if periods else None)

    scope_q = journal_scope.analytics_scope_q(
        request.user,
        organization,
        path_field="offering__group__path",
        id_field="offering__group__id",
    )

    data = (
        analytics.build_period_analytics(organization=organization, period=period, scope_q=scope_q)
        if period is not None
        else {"has_data": False, "period": None, "totals": None, "programs": [], "groups": [], "at_risk": []}
    )
    return {"periods": periods, "analytics": data, "analytics_embedded": embedded}


def _has_active_student_membership(organization, user) -> bool:
    """`student` rolu ilə AKTİV üzvlük varmı?

    `organizations` statik import edilmir (module_deps qapısı) — `get_model`.
    """
    Membership = django_apps.get_model("organizations", "Membership")
    # Tələbə ailəsi: adi tələbə, qrup nümayəndəsi, məzun — heç biri «müəllim» üzü görməməlidir
    # (QA 2026-09-05 P2-31: qeydsiz məzun/tələbə cədvəldə «Müəllim cədvəli» görürdü).
    return Membership.objects.filter(
        organization=organization, user=user, is_active=True, role__name__in=STUDENT_FAMILY_ROLE_NAMES
    ).exists()


STUDENT_FAMILY_ROLE_NAMES = ("student", "lead_student", "alumni")


def schedule_context(request, organization, *, embedded=False) -> dict:
    """Role-aware weekly timetable context (student group / teacher own slots)."""
    from apps.registrar.models import WeekType

    # R-1/R-4: `is_current` bayrağı TƏK meyar deyil — bitmiş semestr cədvəli
    # görünməz edirdi.  Seçim məntiqi (və dövr seçicisinin siyahısı)
    # `schedule.resolve_display_period`-dədir.
    period_view = schedule.resolve_display_period(organization, requested=request.GET.get("period"))
    period = period_view["period"]
    try:
        week_offset = max(-8, min(16, int(request.GET.get("w") or 0)))
    except (TypeError, ValueError):
        week_offset = 0
    week_context = schedule.build_week_context(period, offset=week_offset)

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("group")
        .first()
    )
    teacher_offerings = []
    exam_author = None
    course_ids = []
    if record and record.group and period:
        role = "student"
        owner_label = record.group.name
        slots = schedule.get_group_schedule(organization=organization, group=record.group, period=period)
        course_ids = list(
            CourseOffering.objects.filter(organization=organization, group=record.group, period=period).values_list(
                "course_id", flat=True
            )
        )
    elif _has_active_student_membership(organization, request.user):
        # Qrupu (və ya akademik qeydi) hələ olmayan TƏLƏBƏ — əvvəllər «müəllim»
        # qoluna düşür və başlıqda «Müəllim cədvəli» görürdü (klonda 102 hesab).
        # Cədvəli boş qalır, amma kimliyi tələbə olaraq qalmalıdır.
        role = "student"
        owner_label = request.user.get_full_name() or request.user.username
        slots = []
    else:
        role = "teacher"
        owner_label = request.user.get_full_name() or request.user.username
        exam_author = request.user
        if period:
            slots = schedule.get_teacher_schedule(organization=organization, teacher=request.user, period=period)
            teacher_offerings = list(
                CourseOffering.objects.filter(
                    organization=organization, instructor=request.user, period=period, is_active=True
                ).select_related("subject", "group")
            )
            course_ids = [off.course_id for off in teacher_offerings]
        else:
            slots = []

    exams_by_day = schedule.get_week_exams(
        organization=organization,
        course_ids=course_ids,
        monday=week_context["monday"],
        author=exam_author,
    )

    time_grid = schedule.build_time_grid(slots, week_context=week_context, exams_by_day=exams_by_day)
    _attach_slot_extras(
        time_grid,
        stats_map=_student_offering_stats(request.user, organization, record, period) if role == "student" else None,
        counts_map=_offering_student_counts(teacher_offerings) if role == "teacher" else None,
    )

    from apps.registrar.models import SlotKind

    # Həftə naviqasiyası: standalone-da `?w=N`, profil panelində shell daxilində qalır.
    # Seçilmiş dövr həftə pillələrində İTMİR (`?period=` müqaviləsi — my-journal ilə eyni).
    nav_prefix = _profile_section_prefix("my-schedule") if embedded else "?"
    if period_view["selected_id"]:
        nav_prefix = f"{nav_prefix}period={period_view['selected_id']}&"
    # ŞƏXSİ cədvəldə idarəetmə düymələri `schedule.manage` açarına bağlıdır
    # (2026-09). Adi müəllim burada yalnız-oxu rejimindədir — cədvəl qurmaq
    # koordinator/dekanlıq/RİM işidir və «Cədvəl idarəetməsi» bölməsindədir.
    from apps.registrar import schedule_manage

    can_manage = schedule_manage.can_manage(request.user, organization)
    return {
        "has_context": True,
        "role": role,
        "owner_label": owner_label,
        "record": record,
        "student_course_no": _course_number(record, period) if role == "student" else "",
        "period": period,
        "week": week_context,
        "time_grid": time_grid,
        "teacher_offerings": teacher_offerings,
        "weekdays": schedule.WEEKDAYS,
        "week_types": WeekType.choices,
        "slot_kinds": SlotKind.choices,
        "standard_times": schedule.STANDARD_LESSON_TIMES,
        "schedule_nav_prefix": nav_prefix,
        "schedule_embedded": embedded,
        "schedule_can_manage": can_manage,
        "schedule_next_url": _profile_section_prefix("my-schedule").rstrip("&?") if embedded else "",
        "schedule_period_choices": period_view["choices"],
        "schedule_year_choices": period_view["years"],
        "schedule_selected_period_id": period_view["selected_id"],
        "schedule_selected_year": getattr(period, "academic_year", ""),
        "schedule_base_url": reverse("accounts:profile") if embedded else "",
    }


def _course_number(record, period) -> str:
    """Tələbənin kursu (rum rəqəmi ilə, məs. III) — qəbul ilindən hesablanır."""
    if record is None or period is None or not getattr(period, "start_date", None):
        return ""
    start = period.start_date
    years = start.year - record.admission_year + (1 if start.month >= 8 else 0)
    romans = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
    return romans.get(max(1, years), "")


def _attach_slot_extras(grid, *, stats_map=None, counts_map=None):
    """Modal üçün hər slot elementinə rol-spesifik əlavələr bağlanır:
    tələbəyə öz jurnal statusu (qayıb/giriş balı), müəllimə qrupun tələbə sayı."""
    for rows in (grid["rows"], grid["evening_rows"]):
        for row in rows:
            for cell in row["cells"]:
                for item in cell["slots"]:
                    offering_id = item["slot"].offering_id
                    if stats_map is not None:
                        item["stats"] = stats_map.get(offering_id)
                    if counts_map is not None:
                        item["student_count"] = counts_map.get(offering_id, 0)


def _student_offering_stats(user, organization, record, period) -> dict:
    """Tələbənin fənn-fənn jurnal xülasəsi (cədvəl modalı üçün, yüngül).

    Qayıb saatı denormalizə olunmuş ``Enrollment.absence_hours``-dan gəlir;
    giriş balı kanonik :func:`gradebook.entry_score_for` ilə hesablanır."""
    from decimal import Decimal

    from apps.registrar import exam_eligibility, gradebook
    from apps.registrar.models import Enrollment

    if record is None or period is None:
        return {}
    limit_percent = record.program.absence_limit_percent if record.program else exam_eligibility.DEFAULT_LIMIT_PERCENT
    stats: dict = {}
    enrollments = list(
        Enrollment.objects.filter(
            organization=organization,
            student=user,
            offering__period=period,
            status=Enrollment.Status.ENROLLED,
        ).select_related("offering", "offering__assessment_scheme")
    )
    # Buraxılış statusu donmuş açılışlar — toplu dəst (iki sabit sorğu),
    # cədvəl modalı hər sətir üçün ayrı sorğu ETMİR.
    offering_ids = [e.offering_id for e in enrollments]
    frozen_ids = exam_eligibility.frozen_offering_ids(offering_ids)
    hours_map = exam_eligibility.lesson_hours_map(offering_ids)
    for enrollment in enrollments:
        offering = enrollment.offering
        scheme = getattr(offering, "assessment_scheme", None)
        cap = scheme.entry_score_max if scheme else 50
        total_hours = exam_eligibility.lesson_hours_for(offering, hours_map=hours_map)
        allowed = total_hours * Decimal(limit_percent) / Decimal(100)
        eligibility = exam_eligibility.resolve(
            absence_hours=enrollment.absence_hours,
            lesson_hours=total_hours,
            allowed_hours=allowed,
            limit_percent=limit_percent,
            # İdmançı istisnası burada da ötürülür — cədvəl modalı ilə kabinet
            # eyni sətirdə fərqli cavab verməsin (2026-08-31, 3-cü bloker).
            exempt=bool(record.national_athlete_exemption),
            frozen=offering.id in frozen_ids,
        )
        stats[offering.id] = {
            "absence_hours": enrollment.absence_hours,
            "allowed_absence": allowed,
            "entry_score": gradebook.entry_score_for(enrollment, cap),
            "entry_score_max": cap,
            "barred": eligibility["barred"],
            "attendance_score": eligibility["attendance_score"],
            "eligibility": eligibility,
        }
    return stats


def _offering_student_counts(offerings) -> dict:
    """Müəllim modalı üçün: hər offering-in aktiv tələbə sayı (tək sorğu)."""
    from django.db.models import Count

    from apps.registrar.models import Enrollment

    if not offerings:
        return {}
    rows = (
        Enrollment.objects.filter(offering__in=list(offerings), status=Enrollment.Status.ENROLLED)
        .values("offering_id")
        .annotate(n=Count("id"))
    )
    return {row["offering_id"]: row["n"] for row in rows}


def _current_period(organization):
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )
