from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.constants import (
    ATTEMPT_FINISHED_STATUSES,
    DEFAULT_EXAM_LANGUAGE,
    get_live_active_states,
    get_live_session_model,
)
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.language_variants import available_language_options
from apps.exams.views.shared.tenant import tenant_scoped_exams
from core.tenancy import get_request_organization

from ._helpers import build_exam_history_url, ensure_student_exam_tenant_context

# ───────────────────────────── filter taxonomy ─────────────────────────────
# `exam_type` (mexanika) filtrləri — modeldəki real saxlama dəyəri.
MECHANIC_TYPE_FILTERS = {"test", "written", "coding"}
# `exam_type_extended` (kateqoriya) filtrləri — Final/Midterm/Quiz və s.
EXTENDED_TYPE_FILTERS = {"quiz", "midterm", "final", "placement", "practice"}
# Geriyə uyğunluq üçün köhnə adı saxlayırıq (başqa modullar import edə bilər).
VALID_EXAM_TYPE_FILTERS = MECHANIC_TYPE_FILTERS
# "live" virtual filtridir — DB sahəsi deyil, aktiv LiveSession-a görə hesablanır.
# (Aktiv state-lər üçün apps.exams.constants.get_live_active_states() istifadə olunur.)
LIVE_TYPE_FILTER = "live"

# Sıralama seçimləri — dizayndakı "Sırala" menyusuna uyğun.
SORT_SOON = "soon"
SORT_NEW = "new"
SORT_DURATION = "duration"
VALID_SORTS = {SORT_SOON, SORT_NEW, SORT_DURATION}
DEFAULT_SORT = SORT_SOON

# Hər səhifədə göstərilən imtahan sayı. Paginator sayı ilə real göstərilən
# kart sayının üst-üstə düşməsi üçün bütün görünürlük filtrləri SQL
# səviyyəsində (paginate-dən ƏVVƏL) tətbiq olunmalıdır.
EXAMS_PER_PAGE = 9

# attempts_left_for() ilə eyni status dəsti — limit hesabına yalnız
# tamamlanmış cəhdlər daxildir (tək mənbə: apps.exams.constants).
FINISHED_ATTEMPT_STATUSES = ATTEMPT_FINISHED_STATUSES


def _user_finished_attempt_count_sq(user):
    """Per-exam subquery: user-in tamamlanmış (limitə sayılan) cəhd sayı."""
    return (
        ExamAttempt.objects.filter(
            exam=OuterRef("pk"),
            user=user,
            status__in=FINISHED_ATTEMPT_STATUSES,
        )
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )


def _live_session_exists_sq():
    """Per-exam Exists subquery: imtahanın aktiv (bitməmiş) canlı sessiyası varmı."""
    return get_live_session_model().objects.filter(exam=OuterRef("pk"), state__in=get_live_active_states())


def _exclude_attempt_exhausted(queryset):
    """
    Cəhd limiti bitmiş imtahanları SQL səviyyəsində çıxar.

    Bu filtr paginate-dən ƏVVƏL tətbiq olunur ki, Paginator.count ilə
    səhifədə real göstərilən kart sayı uyğun gəlsin. `max_attempts_per_user`
    0/NULL → limitsiz (attempts_left_for ilə eyni semantika).
    """
    return queryset.filter(
        Q(max_attempts_per_user__isnull=True)
        | Q(max_attempts_per_user=0)
        | Q(finished_attempt_count__lt=F("max_attempts_per_user"))
    )


def _exclude_expired_exams(queryset):
    """Vaxtı bitmiş imtahanları siyahı və tab saylarından çıxar."""
    now = timezone.now()
    return queryset.filter(Q(end_datetime__isnull=True) | Q(end_datetime__gte=now))


def _apply_exam_type_filter(queryset, filter_type):
    """
    Tip tabına görə süzgəc.

    - "live"  → aktiv canlı sessiyası olan imtahanlar (is_live_now annotasiyası).
    - mexanika (test/written/coding) → exam_type sahəsi.
    - kateqoriya (final/midterm/quiz/placement/practice) → exam_type_extended sahəsi.
    """
    if filter_type == LIVE_TYPE_FILTER:
        return queryset.filter(is_live_now=True)
    if filter_type in MECHANIC_TYPE_FILTERS:
        return queryset.filter(exam_type=filter_type)
    if filter_type in EXTENDED_TYPE_FILTERS:
        return queryset.filter(exam_type_extended=filter_type)
    return queryset


def _normalize_sort(raw_sort):
    sort = (raw_sort or "").strip()
    return sort if sort in VALID_SORTS else DEFAULT_SORT


def _apply_sort(queryset, sort):
    """
    Sıralama. Canlı imtahanlar hər zaman yuxarıda (`-is_live_now`), sonra
    seçilmiş sıralama meyarı tətbiq olunur. NULL dəyərlər sona atılır ki,
    tarixsiz/müddətsiz imtahanlar siyahını pozmasın.
    """
    if sort == SORT_NEW:
        order = ["-created_at"]
    elif sort == SORT_DURATION:
        order = [F("total_duration_minutes").desc(nulls_last=True), "-created_at"]
    else:  # SORT_SOON — tezliklə başlayan
        order = [F("start_datetime").asc(nulls_last=True), "-created_at"]
    return queryset.order_by("-is_live_now", *order)


def _build_type_counts(base_qs):
    """
    Tip tablarının yanındakı saylar — tək aqreqat sorğu (per-tab COUNT yox).

    DİQQƏT: canlı sayını ayrı hesablayırıq, çünki `live_sessions`-a JOIN
    digər (test/written/...) sayları şişirdərdi.
    """
    # distinct=True vacibdir: baza sorğusu M2M JOIN-lər üzərində .distinct()
    # istifadə edir, ona görə adi Count('id') dublikat sətirləri sayardı.
    counts = base_qs.aggregate(
        total=Count("id", distinct=True),
        test=Count("id", filter=Q(exam_type="test"), distinct=True),
        written=Count("id", filter=Q(exam_type="written"), distinct=True),
        coding=Count("id", filter=Q(exam_type="coding"), distinct=True),
        quiz=Count("id", filter=Q(exam_type_extended="quiz"), distinct=True),
        midterm=Count("id", filter=Q(exam_type_extended="midterm"), distinct=True),
        final=Count("id", filter=Q(exam_type_extended="final"), distinct=True),
        placement=Count("id", filter=Q(exam_type_extended="placement"), distinct=True),
        practice=Count("id", filter=Q(exam_type_extended="practice"), distinct=True),
    )
    counts["live"] = base_qs.filter(is_live_now=True).count()
    return counts


def _live_session_map(exam_ids):
    """
    Cari səhifədəki canlı imtahanlar üçün ən son aktiv sessiyanı qaytarır.
    {exam_id: {"pin", "players", "state"}}. Yalnız səhifədəki imtahanlar üçün
    çağırılır — ağır deyil.
    """
    if not exam_ids:
        return {}

    sessions = (
        get_live_session_model()
        .objects.filter(exam_id__in=exam_ids, state__in=get_live_active_states())
        .annotate(player_count=Count("players"))
        .order_by("exam_id", "-created_at")
    )
    live_map = {}
    for session in sessions:
        # order_by ilə hər exam üçün ən yeni sessiya birinci gəlir.
        if session.exam_id not in live_map:
            live_map[session.exam_id] = {
                "pin": session.pin,
                "players": session.player_count,
                "state": session.state,
            }
    return live_map


def _display_type(exam, is_live):
    """
    Kartda göstəriləcək vahid tip açarı (badge rəngi/etiketi üçün).
    Prioritet: canlı > kateqoriya (exam_type_extended) > mexanika (exam_type).
    Açarlar filter/tab/CSS data-type ilə eynidir.
    """
    if is_live:
        return "live"
    if exam.exam_type_extended:
        return exam.exam_type_extended
    return exam.exam_type or "test"


def _type_label(key):
    """Tip açarı → cari dilə uyğun göstəriş etiketi (tablar + kart badge-ləri)."""
    labels = {
        "all": pgettext("exams.type.label", "all"),
        "live": pgettext("exams.type.label", "live"),
        "final": pgettext("exams.type.label", "final"),
        "midterm": pgettext("exams.type.label", "midterm"),
        "quiz": pgettext("exams.type.label", "quiz"),
        "placement": pgettext("exams.type.label", "placement"),
        "practice": pgettext("exams.type.label", "practice"),
        "written": pgettext("exams.type.label", "written"),
        "test": pgettext("exams.type.label", "test"),
        "coding": pgettext("exams.type.label", "coding"),
    }
    return labels.get(key, key)


def _build_type_tabs(counts):
    """
    Göstəriləcək tip tablarını qurur. Əsas tablar həmişə görünür; canlı,
    praktiki, placement və practice yalnız say > 0 olduqda görünür ki,
    interfeys lüzumsuz dolmasın.
    """
    tabs = [{"key": "all", "label": _type_label("all"), "count": counts.get("total", 0)}]

    def add(key, count_key, *, always=False):
        count = counts.get(count_key, 0)
        if always or count:
            tabs.append({"key": key, "label": _type_label(key), "count": count})

    add("live", "live")
    add("final", "final", always=True)
    add("midterm", "midterm", always=True)
    add("quiz", "quiz", always=True)
    add("written", "written", always=True)
    add("test", "test", always=True)
    add("coding", "coding")
    add("placement", "placement")
    add("practice", "practice")
    return tabs


def _build_language_modal_context(exam):
    options = [
        {
            "language": option["language"],
            "display_name": option["display_name"],
        }
        for option in available_language_options(exam)
    ]
    codes = {option["language"] for option in options}
    default_language = ""
    if DEFAULT_EXAM_LANGUAGE in codes:
        default_language = DEFAULT_EXAM_LANGUAGE
    elif options:
        default_language = options[0]["language"]

    return {
        "language_options": options,
        "language_options_id": f"exam-language-options-{exam.id}",
        "default_language": default_language,
    }


def _annotate_exam_list_base(queryset, user):
    """Hər iki siyahı view-i üçün ortaq annotasiyalar (N+1-i SQL-ə köçürür)."""
    user_attempt_count_sq = (
        ExamAttempt.objects.filter(exam=OuterRef("pk"), user=user)
        .exclude(status="draft")
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )
    return queryset.select_related("author", "organization", "course").annotate(
        user_attempt_count=Subquery(user_attempt_count_sq),
        finished_attempt_count=Coalesce(Subquery(_user_finished_attempt_count_sq(user)), 0),
        is_live_now=Exists(_live_session_exists_sq()),
    )


def _build_exam_items(page_object_list, user, request, live_map):
    """Səhifədəki imtahanları template üçün zəngin item-lərə çevirir."""
    exam_items = []
    for exam in page_object_list:
        # SECURITY GUARD: baza sorğusu yalnız icazəli imtahanları gətirir,
        # bu yoxlama son sədd kimi qalır (normal halda heç vaxt işə düşmür).
        if exam.is_after_end():
            continue
        if not exam.can_user_see(user):
            continue

        is_live = bool(getattr(exam, "is_live_now", False)) and exam.id in live_map
        live_info = live_map.get(exam.id) if is_live else None
        display_type = _display_type(exam, is_live)
        mechanic_type = exam.exam_type or "test"
        category_type = exam.exam_type_extended or ""

        # Yalnız göstərmək üçün hesablanır (lazy expiry daxil) — limit filtri
        # artıq SQL-də tətbiq olunub, burada kart atılmır.
        left = exam.attempts_left_for(user)

        can_without_code, _ = exam.can_user_start(user, code=None)
        requires_code = bool(exam.access_code and not can_without_code)

        if exam.access_code:
            access_label = pgettext("exams.view.student.list.label", "access_code_required")
        elif exam.is_public:
            access_label = pgettext("exams.view.student.list.label", "access_public")
        else:
            access_label = pgettext("exams.view.student.list.label", "access_allowed_only")

        exam_items.append(
            {
                "exam": exam,
                "left": left,
                "attempt_count": exam.user_attempt_count or 0,
                "requires_code": requires_code,
                "access_label": access_label,
                "display_type": display_type,
                "type_label": _type_label(display_type),
                "mechanic_type": mechanic_type,
                "mechanic_label": _type_label(mechanic_type),
                "category_type": category_type,
                "category_label": _type_label(category_type) if category_type else "",
                "is_live": is_live,
                "live": live_info,
                "history_url": build_exam_history_url(exam, return_to=request.get_full_path()),
                **_build_language_modal_context(exam),
            }
        )
    return exam_items


def _render_exam_list(request, *, base_queryset, page_title, current_url_name, show_type_tabs=True):
    """
    student_exam_list və assigned_student_exam_list üçün ortaq render axını.

    `base_queryset` artıq tenant + giriş-icazəsi filtrlərini ehtiva edir.
    Bütün görünürlük/tip/canlı filtrləri paginate-dən ƏVVƏL SQL-də tətbiq
    olunur ki, Paginator.count ekrandakı kart sayı ilə uyğun gəlsin.
    """
    user = request.user
    exams_qs = _annotate_exam_list_base(base_queryset, user)

    # --- SEARCH (axtarış: başlıq və ya müəllim) ---
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        exams_qs = exams_qs.filter(Q(title__icontains=search_query) | Q(author__username__icontains=search_query))

    # Real görünürlük filtrləri saylardan ƏVVƏL tətbiq olunur ki, tab sayı
    # kliklənəndə boş səhifəyə aparmasın (məs. cəhd limiti bitmiş imtahan).
    exams_qs = _exclude_expired_exams(exams_qs)
    exams_qs = _exclude_attempt_exhausted(exams_qs)

    # Tab sayları tip filtrindən ƏVVƏL hesablanır (axtarış + görünürlükdən sonra).
    type_counts = _build_type_counts(exams_qs)

    # --- FILTER (tip tabı) ---
    filter_type = (request.GET.get("type") or "").strip()
    exams_qs = _apply_exam_type_filter(exams_qs, filter_type)

    # --- SORT ---
    sort = _normalize_sort(request.GET.get("sort"))
    exams_qs = _apply_sort(exams_qs, sort)

    # --- PAGINATION (queryset səviyyəsində) ---
    paginator = Paginator(exams_qs, EXAMS_PER_PAGE)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Canlı sessiya detalları yalnız səhifədəki imtahanlar üçün gətirilir.
    page_exam_ids = [exam.id for exam in page_obj.object_list]
    live_map = _live_session_map(page_exam_ids)

    exam_items = _build_exam_items(page_obj.object_list, user, request, live_map)
    page_obj.object_list = exam_items

    # Pagination linklərinin q/type/sort parametrlərini saxlaması üçün.
    preserved = request.GET.copy()
    preserved.pop("page", None)
    extra_query = preserved.urlencode()

    context = {
        "page_obj": page_obj,
        "exam_items": page_obj,
        "page_title": page_title,
        "current_url_name": current_url_name,
        "type_counts": type_counts,
        "type_tabs": _build_type_tabs(type_counts) if show_type_tabs else [],
        "live_count": type_counts.get("live", 0),
        "active_type": filter_type,
        "active_sort": sort,
        "search_query": search_query,
        "total_count": type_counts.get("total", 0),
        "extra_query": extra_query,
        "organization": get_request_organization(request),
    }
    return render(request, "exams/student/student_exam_list.html", context)


@login_required
def assigned_student_exam_list(request):
    ensure_student_exam_tenant_context(request)
    user = request.user

    # Yalnız user-ə təyin olunmuş aktiv imtahanlar (is_public=False).
    base_queryset = tenant_scoped_exams(
        request,
        Exam.objects.filter(is_active=True, is_public=False)
        .filter(
            Q(allowed_users=user)
            | Q(allowed_groups__students=user)
            | Q(
                course__memberships__user=user,
                course__memberships__role="student",
                course__status="published",
            )
        )
        .exclude(excluded_users=user)
        .distinct(),
    )

    return _render_exam_list(
        request,
        base_queryset=base_queryset,
        page_title=pgettext_lazy("exams.view.student.list.title", "assigned_exams"),
        current_url_name="assigned_exam_list",
    )


@login_required
def student_exam_list(request):
    ensure_student_exam_tenant_context(request)
    user = request.user
    now = timezone.now()

    # Aktiv + tarixi keçməmiş, user-in görə bildiyi bütün imtahanlar.
    base_queryset = tenant_scoped_exams(
        request,
        Exam.objects.filter(is_active=True)
        .filter(
            Q(is_public=True)
            | Q(allowed_users=user)
            | Q(allowed_groups__students=user)
            | Q(
                course__memberships__user=user,
                course__memberships__role="student",
                course__status="published",
            )
            | Q(author=user)
        )
        .exclude(excluded_users=user)
        .filter(Q(end_datetime__isnull=True) | Q(end_datetime__gte=now))  # keçmişləri gizlədir
        .distinct(),
    )

    return _render_exam_list(
        request,
        base_queryset=base_queryset,
        page_title=pgettext_lazy("exams.view.student.list.title", "available_exams"),
        current_url_name="student_exam_list",
    )
