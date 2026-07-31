"""Profil "my-exams" bölməsi üçün context-fragment qurucusu."""

from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce


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

    # Kart redizaynı: sual sayı + apellyasiya sayı və aktiv dil variantları
    # (prefetch). Səhifələmə yoxdur — qruplaşma/KPI servisdə Python tərəfdə
    # hesablanır (dashboard bütün siyahı üzərində qurulur).
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
    exams_list = list(display_qs)
    return {
        "my_exams_count": len(exams_list),
        "my_exams_list": exams_list,
        "my_exams_dashboard": build_teacher_exam_dashboard(
            exams_list, include_empty_categories=is_exam_center_user(request.user)
        ),
        "my_exams_search_query": search_query,
        "my_exams_filter_type": filter_type,
    }
