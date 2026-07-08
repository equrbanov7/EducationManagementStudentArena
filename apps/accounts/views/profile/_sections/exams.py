"""Profil "my-exams" bölməsi üçün context-fragment qurucusu."""

from django.db.models import Count, Prefetch, Q


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

    # Kart redizaynı: sual sayı + apellyasiya sayı (annotate) və aktiv dil
    # variantları (prefetch). Səhifələmə yoxdur — qruplaşma/KPI servisdə Python
    # tərəfdə hesablanır.
    display_qs = my_exams_qs.annotate(
        card_question_count=Count("questions", filter=Q(questions__is_active=True), distinct=True),
        card_appeal_count=Count("appeals", distinct=True),
        card_allowed_group_count=Count("allowed_groups", distinct=True),
        card_allowed_user_count=Count("allowed_users", distinct=True),
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
        "my_exams_dashboard": build_teacher_exam_dashboard(exams_list),
        "my_exams_search_query": search_query,
        "my_exams_filter_type": filter_type,
    }
