"""Profil "my-exams" bölməsi üçün context-fragment qurucusu."""

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, OuterRef, Prefetch, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

#: Bir səhifədə göstərilən imtahan sayı.
MY_EXAMS_PAGE_SIZE = 12


def _lifecycle_status_expression():
    """``Exam.lifecycle_status`` propertysinin SQL qarşılığı.

    Property: ``is_active`` yoxdursa `draft`; ``start_datetime`` gələcəkdədirsə
    `scheduled`; əks halda `active`. ``start_datetime`` NULL olanda
    ``is_before_start()`` False qaytarır — ``__gt`` müqayisəsi də NULL üçün
    yanlışdır, yəni davranış eynidir.

    NƏ ÜÇÜN SQL: KPI kartları və kateqoriya çipləri BÜTÜN filtrlənmiş dəst üzrə
    olmalıdır. Səhifələmədən sonra Python tərəfdə saymaq yalnız cari səhifəni
    sayardı və istifadəçi «Aktiv: 12» görərdi, halbuki 150-dir.
    """
    return Case(
        When(is_active=False, then=Value("draft")),
        When(start_datetime__gt=timezone.now(), then=Value("scheduled")),
        default=Value("active"),
    )


def _related_count(queryset, *, group_by):
    """Korrelyasiyalı ``COUNT`` alt-sorğusu.

    NƏ ÜÇÜN: eyni sorğuda bir neçə çoxdəyərli əlaqə üzrə ``Count(distinct=True)``
    yazmaq dekart hasili yaradır — hər JOIN sətirləri çoxaldır, `DISTINCT` isə
    şişmiş aralıq nəticəni sonradan təmizləyir. 4 belə sayğac (suallar,
    apellyasiyalar, icazəli qruplar, icazəli istifadəçilər) bir sorğuda idi.
    Korrelyasiyalı alt-sorğu hər sayğacı öz cədvəlində, indeks üzərində hesablayır.
    """
    return Coalesce(
        Subquery(
            queryset.order_by().values(group_by).annotate(_c=Count("pk")).values("_c")[:1],
            output_field=IntegerField(),
        ),
        0,
    )


def build_my_exams_context(request, *, my_exams_qs, active_section) -> dict:
    """Müəllifin imtahanları bölməsi üçün ``context`` açarlarını qaytarır.

    "my-exams" aktivdirsə tam siyahını (annotate + prefetch ilə N+1-siz) yükləyir
    və müəllim dashboard-ını qurur; əks halda yalnız ucuz sayğacı qaytarır.
    Davranış köhnə inline blokla eynidir; ``my_exams_qs`` yalnız daxildə (lokal)
    filtrlənir.
    """
    if active_section != "my-exams":
        return {
            "my_exams_count": my_exams_qs.count(),
            "my_exams_list": [],
            "my_exams_dashboard": None,
            "my_exams_search_query": "",
            "my_exams_filter_type": "",
            "my_exams_filter_status": "",
            "my_exams_is_paginated": False,
            "my_exams_page_obj": None,
            "my_exams_pagination_query": "",
        }

    from apps.exams.models import ExamLanguageVariant
    from apps.exams.public import build_teacher_exam_dashboard
    from apps.exams.services.access_policy import is_exam_center_user

    # --- Search ---
    search_query = (request.GET.get("exam_q", "") or "").strip()
    if search_query:
        my_exams_qs = my_exams_qs.filter(title__icontains=search_query)

    # --- Filter by exam type ---
    filter_type = (request.GET.get("exam_type", "") or "").strip()
    if filter_type not in {"", "test", "written", "coding"}:
        filter_type = ""
    if filter_type:
        my_exams_qs = my_exams_qs.filter(exam_type=filter_type)

    # --- Status filtri (KPI kartlarına klik) ---
    # Səhifələmədən əvvəl bu filtr YALNIZ klient-tərəfdə vardı: JS DOM-dakı
    # kartları gizlədirdi. Səhifələmə ilə DOM-da cəmi 12 kart olur, yəni klient
    # filtri qalan sətirləri heç vaxt görmür. Ona görə status da serverə
    # daşınır — eyni `Case/When` ifadəsi ilə, KPI sayğacları ilə tam uyğun.
    filter_status = (request.GET.get("exam_status", "") or "").strip()
    if filter_status not in {"", "draft", "scheduled", "active"}:
        filter_status = ""
    if filter_status:
        my_exams_qs = my_exams_qs.annotate(_status_f=_lifecycle_status_expression()).filter(_status_f=filter_status)

    # Kart redizaynı: sual sayı + apellyasiya sayı və aktiv dil variantları
    # (prefetch). Səhifələmə VAR; KPI/kateqoriya sayğacları isə ayrıca aqreqat
    # sorğulardan gəlir, yəni kartlar səhifə üzrə, saylar tam dəst üzrədir.
    from apps.appeals.models import Appeal
    from apps.exams.models import Exam, ExamQuestion

    allowed_users_through = Exam.allowed_users.through
    allowed_groups_through = Exam.allowed_groups.through

    display_qs = my_exams_qs.annotate(
        card_question_count=_related_count(
            ExamQuestion.objects.filter(exam=OuterRef("pk"), is_active=True), group_by="exam"
        ),
        card_appeal_count=_related_count(Appeal.objects.filter(exam=OuterRef("pk")), group_by="exam"),
        card_allowed_group_count=_related_count(
            allowed_groups_through.objects.filter(exam=OuterRef("pk")), group_by="exam"
        ),
        card_allowed_user_count=_related_count(
            allowed_users_through.objects.filter(exam=OuterRef("pk")), group_by="exam"
        ),
    ).prefetch_related(
        Prefetch(
            "language_variants",
            queryset=ExamLanguageVariant.objects.filter(is_active=True).order_by("language"),
            to_attr="active_language_variants",
        )
    )
    # KPI/çip sayğacları — BÜTÜN filtrlənmiş dəst üzrə, iki aqreqat sorğusu ilə.
    # DİQQƏT: `order_by()` MƏCBURİDİR. `values().annotate()` ilə birlikdə
    # `Meta.ordering` sahələri GROUP BY-a düşür və hər imtahan ayrıca sətir olur
    # (sayğac 1 qaytarır) — layihədə eyni tələ apellyasiya statistikasında da var.
    status_rows = (
        my_exams_qs.order_by()
        .annotate(_lifecycle=_lifecycle_status_expression())
        .values("_lifecycle")
        .annotate(n=Count("pk"))
    )
    status_counts = {row["_lifecycle"]: row["n"] for row in status_rows}
    status_counts["all"] = sum(status_counts.values())
    category_counts = {
        row["exam_type_extended"]: row["n"]
        for row in my_exams_qs.order_by().values("exam_type_extended").annotate(n=Count("pk"))
    }

    paginator = Paginator(display_qs, MY_EXAMS_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("exam_page"))
    exams_list = list(page_obj.object_list)

    pagination_params = {}
    if search_query:
        pagination_params["exam_q"] = search_query
    if filter_type:
        pagination_params["exam_type"] = filter_type
    if filter_status:
        pagination_params["exam_status"] = filter_status
    pagination_params["section"] = "my-exams"

    return {
        "my_exams_count": status_counts["all"],
        "my_exams_list": exams_list,
        "my_exams_dashboard": build_teacher_exam_dashboard(
            exams_list,
            include_empty_categories=is_exam_center_user(request.user),
            status_counts=status_counts,
            category_counts_override=category_counts,
            total=status_counts["all"],
        ),
        "my_exams_search_query": search_query,
        "my_exams_filter_type": filter_type,
        "my_exams_filter_status": filter_status,
        "my_exams_is_paginated": page_obj.has_other_pages(),
        "my_exams_page_obj": page_obj,
        "my_exams_pagination_query": urlencode(pagination_params),
    }
