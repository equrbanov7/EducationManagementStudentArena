from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.language_variants import available_language_options
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import build_exam_history_url, ensure_student_exam_tenant_context

VALID_EXAM_TYPE_FILTERS = {"test", "written", "coding"}

# Hər səhifədə göstərilən imtahan sayı. Paginator sayı ilə real göstərilən
# kart sayının üst-üstə düşməsi üçün bütün görünürlük filtrləri SQL
# səviyyəsində (paginate-dən ƏVVƏL) tətbiq olunmalıdır.
EXAMS_PER_PAGE = 3

# attempts_left_for() ilə eyni status dəsti — limit hesabına yalnız
# tamamlanmış cəhdlər daxildir.
FINISHED_ATTEMPT_STATUSES = ("submitted", "expired", "graded")


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


def _exclude_attempt_exhausted(queryset):
    """
    Cəhd limiti bitmiş imtahanları SQL səviyyəsində çıxar.

    Bu filtr paginate-dən ƏVVƏL tətbiq olunur ki, Paginator.count ilə
    səhifədə real göstərilən kart sayı uyğun gəlsin (əvvəllər limit yoxlaması
    paginate-dən sonra Python-da edilirdi və səhifələrdə 3 əvəzinə 1-2 kart
    görünürdü). `max_attempts_per_user` 0/NULL → limitsiz (attempts_left_for
    ilə eyni semantika).
    """
    return queryset.filter(
        Q(max_attempts_per_user__isnull=True)
        | Q(max_attempts_per_user=0)
        | Q(finished_attempt_count__lt=F("max_attempts_per_user"))
    )


def _apply_exam_type_filter(queryset, filter_type):
    if filter_type in VALID_EXAM_TYPE_FILTERS:
        return queryset.filter(exam_type=filter_type)
    return queryset


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


@login_required
def assigned_student_exam_list(request):
    ensure_student_exam_tenant_context(request)
    user = request.user

    # Annotate each exam with this user's non-draft attempt count in a single
    # subquery so we avoid one COUNT query per exam in the loop below.
    user_attempt_count_sq = (
        ExamAttempt.objects.filter(exam=OuterRef("pk"), user=user)
        .exclude(status="draft")
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    # 1) BAZA SORĞUSU (İlkin Filter)
    # Fərq burdadır: yalnız user-ə təyin olunmuş aktiv imtahanlar
    exams_qs = tenant_scoped_exams(
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
        .distinct()
        .select_related("author", "organization", "course")
        .annotate(
            user_attempt_count=Subquery(user_attempt_count_sq),
            finished_attempt_count=Coalesce(Subquery(_user_finished_attempt_count_sq(user)), 0),
        ),
    )

    # --- SEARCH (Axtarış) ---
    search_query = request.GET.get("q")
    if search_query:
        exams_qs = exams_qs.filter(Q(title__icontains=search_query) | Q(author__username__icontains=search_query))

    # --- FILTER (Tipə görə) ---
    filter_type = request.GET.get("type")
    exams_qs = _apply_exam_type_filter(exams_qs, filter_type)

    # Cəhd limiti bitmiş imtahanlar SQL-də çıxarılır ki, pagination sayı
    # ekrandakı kart sayı ilə üst-üstə düşsün.
    exams_qs = _exclude_attempt_exhausted(exams_qs)

    # Sıralama
    exams_qs = exams_qs.order_by("-created_at")

    # 2) Paginasiya queryset səviyyəsində. Bütün görünürlük filtrləri artıq
    # SQL-də tətbiq olunub, ona görə hər səhifədə (sonuncu istisna) tam
    # EXAMS_PER_PAGE kart görünür. Ağır model metodları (can_user_see/
    # can_user_start/attempts_left_for) yalnız səhifədəki exam-lar üçün çağırılır.
    paginator = Paginator(exams_qs, EXAMS_PER_PAGE)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    exam_items = []
    for exam in page_obj.object_list:
        # SECURITY GUARD: baza sorğusu yalnız icazəli imtahanları gətirir,
        # bu yoxlama son sədd kimi qalır (normal halda heç vaxt işə düşmür).
        if not exam.can_user_see(user):
            continue

        # Yalnız göstərmək üçün hesablanır (lazy expiry daxil) — limit filtri
        # artıq SQL-də tətbiq olunub, burada kart atılmır.
        left = exam.attempts_left_for(user)

        # kod tələb olunub-olunmamağı user-ə görə hesablayırıq
        can_without_code, _ = exam.can_user_start(user, code=None)

        requires_code = False
        if exam.access_code and not can_without_code:
            requires_code = True

        # ekrandakı status yazısı
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
                "history_url": build_exam_history_url(exam, return_to=request.get_full_path()),
                **_build_language_modal_context(exam),
            }
        )

    # Pagination obyektinin object_list-i visible item-lərlə əvəz edirik ki,
    # template `{% for item in page_obj %}` davranışı dəyişməsin.
    page_obj.object_list = exam_items

    context = {
        "page_obj": page_obj,
        "exam_items": page_obj,
        "page_title": pgettext_lazy("exams.view.student.list.title", "assigned_exams"),
        "current_url_name": "assigned_exam_list",
    }

    return render(request, "exams/student/student_exam_list.html", context)


@login_required
def student_exam_list(request):
    ensure_student_exam_tenant_context(request)
    user = request.user
    now = timezone.now()

    # Annotate each exam with this user's non-draft attempt count in a single
    # subquery so we avoid one COUNT query per exam in the loop below.
    user_attempt_count_sq = (
        ExamAttempt.objects.filter(exam=OuterRef("pk"), user=user)
        .exclude(status="draft")
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt")
    )

    # 1) BAZA SORĞUSU (aktiv + tarixi keçmiş olmayanlar)
    exams_qs = tenant_scoped_exams(
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
        .filter(Q(end_datetime__isnull=True) | Q(end_datetime__gte=now))  # ✅ keçmişləri gizlədir
        .distinct()
        .select_related("author", "organization", "course")
        .annotate(
            user_attempt_count=Subquery(user_attempt_count_sq),
            finished_attempt_count=Coalesce(Subquery(_user_finished_attempt_count_sq(user)), 0),
        ),
    )

    # --- SEARCH ---
    search_query = request.GET.get("q")
    if search_query:
        exams_qs = exams_qs.filter(Q(title__icontains=search_query) | Q(author__username__icontains=search_query))

    # --- FILTER (Tipə görə) ---
    filter_type = request.GET.get("type")
    exams_qs = _apply_exam_type_filter(exams_qs, filter_type)

    # Cəhd limiti bitmiş imtahanlar SQL-də çıxarılır ki, pagination sayı
    # ekrandakı kart sayı ilə üst-üstə düşsün.
    exams_qs = _exclude_attempt_exhausted(exams_qs)

    exams_qs = exams_qs.order_by("-created_at")

    # Paginasiya queryset səviyyəsində (eyni rasional, assigned versiyada
    # olduğu kimi). Bütün görünürlük filtrləri SQL-də tətbiq olunub — hər
    # səhifədə (sonuncu istisna) tam EXAMS_PER_PAGE kart görünür.
    paginator = Paginator(exams_qs, EXAMS_PER_PAGE)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    exam_items = []
    for exam in page_obj.object_list:
        # SECURITY GUARD-lar: baza sorğusu bunları artıq SQL-də filtrləyib,
        # bu yoxlamalar son sədd kimi qalır (normal halda işə düşmür).
        if exam.is_after_end():
            continue

        if not exam.can_user_see(user):
            continue

        # Yalnız göstərmək üçün (lazy expiry daxil) — limit filtri SQL-dədir.
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
                "history_url": build_exam_history_url(exam, return_to=request.get_full_path()),
                **_build_language_modal_context(exam),
            }
        )

    page_obj.object_list = exam_items

    context = {
        "page_obj": page_obj,
        "exam_items": page_obj,
        "page_title": pgettext_lazy("exams.view.student.list.title", "available_exams"),
        "current_url_name": "student_exam_list",
    }

    return render(request, "exams/student/student_exam_list.html", context)
