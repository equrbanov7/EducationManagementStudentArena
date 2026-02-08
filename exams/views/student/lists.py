

from datetime import timezone
from exams.models import Exam
from django.db.models import Q  
from django.shortcuts import  render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


@login_required
def assigned_student_exam_list(request):
    user = request.user

    # 1) BAZA SORĞUSU (İlkin Filter)
    # Fərq burdadır: yalnız user-ə təyin olunmuş aktiv imtahanlar
    exams_qs = (
        Exam.objects
        .filter(is_active=True)
        .filter(
            Q(allowed_users=user) |
            Q(allowed_groups__students=user)
        )
        .distinct()
        .select_related('author')
    )

    # --- SEARCH (Axtarış) ---
    search_query = request.GET.get('q')
    if search_query:
        exams_qs = exams_qs.filter(
            Q(title__icontains=search_query) |
            Q(author__username__icontains=search_query)
        )

    # --- FILTER (Tipə görə) ---
    filter_type = request.GET.get('type')
    if filter_type:
        exams_qs = exams_qs.filter(exam_type=filter_type)

    # Sıralama
    exams_qs = exams_qs.order_by("-created_at")

    # 2) PYTHON MƏNTİQİ (Permissions & List Construction) — EYNİDİR
    exam_items = []

    for exam in exams_qs:
        # bu user ümumiyyətlə bu imtahan kartını görməlidir?
        if not exam.can_user_see(user):
            continue

        # cəhd limiti
        left = exam.attempts_left_for(user)
        if left is not None and left <= 0:
            continue

        # kod tələb olunub-olunmamağı user-ə görə hesablayırıq
        can_without_code, _ = exam.can_user_start(user, code=None)

        requires_code = False
        if exam.access_code and not can_without_code:
            requires_code = True

        # ekrandakı status yazısı
        if exam.access_code:
            access_label = "Kod tələb olunur"
        elif exam.is_public:
            access_label = "Hamı üçün açıq"
        else:
            access_label = "Yalnız icazəli istifadəçilər"

        exam_items.append({
            "exam": exam,
            "left": left,
            "requires_code": requires_code,
            "access_label": access_label,
        }) 

    # 3) PAGINATION (Səhifələmə) — eyni saxla
    paginator = Paginator(exam_items, 2)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "exam_items": page_obj,

        
         "page_title": "Təyin olunmuş imtahanlarım",
         "current_url_name": "assigned_exam_list",
    }

    
    return render(request, "blog/student_exam_list.html", context)




@login_required
def student_exam_list(request):
    user = request.user
    now = timezone.now()

    # 1) BAZA SORĞUSU (aktiv + tarixi keçmiş olmayanlar)
    exams_qs = (
        Exam.objects
        .filter(is_active=True)
        .filter(Q(end_datetime__isnull=True) | Q(end_datetime__gte=now))  # ✅ keçmişləri gizlədir
        .select_related('author')
    )

    # --- SEARCH ---
    search_query = request.GET.get('q')
    if search_query:
        exams_qs = exams_qs.filter(
            Q(title__icontains=search_query) |
            Q(author__username__icontains=search_query)
        )

    # --- FILTER (Tipə görə) ---
    filter_type = request.GET.get('type')
    if filter_type:
        exams_qs = exams_qs.filter(exam_type=filter_type)

    exams_qs = exams_qs.order_by("-created_at")

    exam_items = []

    for exam in exams_qs:
        # 2) SAFETY: hər ehtimala qarşı (timezone / query bypass)
        if exam.is_after_end():
            continue

        if not exam.can_user_see(user):
            continue

        left = exam.attempts_left_for(user)
        if left is not None and left <= 0:
            continue

        can_without_code, _ = exam.can_user_start(user, code=None)
        requires_code = bool(exam.access_code and not can_without_code)

        if exam.access_code:
            access_label = "Kod tələb olunur"
        elif exam.is_public:
            access_label = "Hamı üçün açıq"
        else:
            access_label = "Yalnız icazəli istifadəçilər"

        exam_items.append({
            "exam": exam,
            "left": left,
            "requires_code": requires_code,
            "access_label": access_label,
        })

    paginator = Paginator(exam_items, 2)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,
        "exam_items": page_obj,
        "current_url_name": "student_exam_list",
    }
    # return render(request, "blog/student_exam_list.html", context)
    return render(request, "exams/student/student_exam_list.html", context)


 