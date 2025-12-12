# blog/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse 
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.core.mail import send_mail 
from django.template.loader import render_to_string 
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import timedelta
from .models import Post, Category, Comment, Subscriber, Question, Exam, ExamQuestion, ExamQuestionOption, ExamAttempt, ExamAnswer, ExamAnswerFile
from .forms import (
    SubscriptionForm,
    RegisterForm,
    PostForm,
    CommentForm,
    QuestionForm,
    ExamForm, ExamQuestionCreateForm
)
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.views.decorators.http import require_POST

# ------------------- ƏSAS SƏHİFƏLƏR ------------------- #

def home(request):
    
    query = request.GET.get("q", "").strip()
    post_list = (
        Post.objects
        .filter(is_published=True) 
        .select_related("category", "author")
        .order_by("-created_at")
    )

    if query:
        post_list = post_list.filter(
            Q(title__icontains=query) |
            Q(excerpt__icontains=query) |
            Q(content__icontains=query)
        ).distinct()
        
 
    paginator = Paginator(post_list, 6) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = (
        Category.objects
        .annotate(
            post_count=Count('posts', filter=Q(posts__is_published=True))
        )
        .filter(post_count__gt=0)
        .order_by('name')
    )

 
    context = {
        "page_obj": page_obj,  
        "categories": categories,
        "search_query": query,
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(request, "blog/about.html")

def technology(request):
   
    TECH_CATEGORIES = [
        "proqramlasdirma", 
        "suni-intellekt", 
        "python", 
        "django", 
        "texnologiya", 
        "backend"
    ]
    
    
    post_list = (
        Post.objects
        .filter(category__slug__in=TECH_CATEGORIES)
        .select_related("category", "author")
        .order_by("-created_at")
    )

  
    paginator = Paginator(post_list, 6) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    

    return render(request, "blog/technology.html", {"page_obj": page_obj})


def contact(request):
    return HttpResponse("Contact Us Page (demo)")


# ------------------- POST DETAY + COMMENT ------------------- #

def post_detail(request, slug):
    """
    Bir postun detal səhifəsi + şərhlər və rating forması.
    Rating yalnız ilk şərhdə nəzərə alınır.
    """
    # 1) Postu statusdan asılı olmayaraq tap
    post = get_object_or_404(Post, slug=slug)

    # 2) Əgər post nəşr olunmayıbsa və bu user author DEYİLSƏ -> 404
    if not post.is_published and request.user != post.author:
        raise Http404("No Post matches the given query.")

    comments = (
        post.comments
        .select_related("user")
        .order_by("-created_at")
    )

    user_first_comment = None
    if request.user.is_authenticated:
        user_first_comment = Comment.objects.filter(
            post=post,
            user=request.user
        ).order_by("created_at").first()

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Şərh yazmaq üçün əvvəlcə daxil olun.")
            return redirect("login")

        form = CommentForm(request.POST)

        if form.is_valid():
            if user_first_comment is None:
                # İlk dəfə şərh yazır → həm text, həm rating götürürük
                comment = form.save(commit=False)
                comment.post = post
                comment.user = request.user
                comment.save()
                messages.success(request, "Şərhiniz və qiymətləndirməniz əlavə olundu. ⭐")
            else:
                # Artıq bu posta şərhi var → yeni şərh, eyni rating
                comment = Comment(
                    post=post,
                    user=request.user,
                    text=form.cleaned_data["text"],
                    rating=user_first_comment.rating,
                )
                comment.save()
                messages.success(request, "Yeni şərhiniz əlavə olundu, rating dəyişdirilmədi. 🙂")

            return redirect("post_detail", slug=post.slug)
    else:
        form = CommentForm()

    context = {
        "post": post,
        "comments": comments,
        "comment_form": form,
        "user_first_comment": user_first_comment,
    }
    return render(request, "blog/postDetail.html", context)


# ------------------- SUBSCRIBE ------------------- #

def subscribe_page(request):
    if request.method == "POST":
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            try:
                # 1. Abunəçini bazaya yaz
                subscriber, created = Subscriber.objects.get_or_create(email=email)
                
                if created or not subscriber.is_active:
                    
                    # 2. Email şablonunu yarat
                    html_message = render_to_string(
                        'email_templates/welcome_email.html',
                        {'email': email}
                    )
                    
                    # 3. Email göndər
                    send_mail(
                        'Abunəliyə Xoş Gəlmisiniz! [Sənin Blog Adın]',
                        # Text versiyası (html-i dəstəkləməyən proqramlar üçün)
                        f'Salam, {email}! Blogumuza uğurla abunə oldunuz. Ən son yenilikləri qaçırmamaq üçün bizi izləyin.',
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                    
                    messages.success(request, f"'{email}' ünvanına təsdiq maili göndərildi. Zəhmət olmasa poçt qutunuzu yoxlayın.")
                    
                else:
                    messages.warning(request, f"'{email}' ünvanı artıq abunəçilərimizdədir.")


            except Exception as e:
                # Hər hansı bir xəta (məsələn, SMTP xətası) olarsa
                messages.error(request, f"Email göndərilərkən xəta baş verdi. Zəhmət olmasa, bir az sonra yenidən cəhd edin.")
                print(f"EMAIL ERROR: {e}") # Xətanı konsolda göstər
                
            return redirect("subscribe")
        else:
            messages.error(request, "Zəhmət olmasa düzgün email ünvanı daxil edin.")
    else:
        form = SubscriptionForm()

    return render(request, "blog/subscribe.html", {"form": form})


# ------------------- POST CRUD ------------------- #



@login_required
def create_post(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user

            new_cat_name = form.cleaned_data.get('new_category')
            selected_cat = form.cleaned_data.get('category')

            if new_cat_name:
              
                category, created = Category.objects.get_or_create(name=new_cat_name)
                post.category = category
                
                if created:
                    messages.info(request, f"Yeni '{new_cat_name}' kateqoriyası yaradıldı.")

            elif selected_cat:
                # 2. Əgər yeni heç nə yazmayıb, sadəcə siyahıdan seçibsə:
                post.category = selected_cat
            
            else:
                # 3. Heç nə seçməyibsə (istəyə bağlı):
                # post.category = None # (Modeldə null=True olduğu üçün problem yoxdur)
                pass

            # --- SLUG MƏNTİQİ SİLİNDİ ---
            # Sənin Post modelinin save() metodu slug-ı və unikallığı 
            # avtomatik həll edir. Burda artıq kod yazmağa ehtiyac yoxdur.

            post.save()
            messages.success(request, "Post uğurla yaradıldı.")
            return redirect("post_detail", slug=post.slug)
    else:
        form = PostForm()

    return render(request, "post_form.html", {"form": form})









# 1. POSTU REDAKTƏ ET (AJAX Endpoint)


@login_required
@require_POST
def post_edit_ajax(request, pk):
    # Yalnız öz postunu düzəldə bilsin
    post = get_object_or_404(Post, pk=pk, author=request.user)

    title = request.POST.get("title", "").strip()
    content = request.POST.get("content", "").strip()
    excerpt = request.POST.get("excerpt", "").strip()
    category_id = request.POST.get("category")  # select name="category"
    image_url = request.POST.get("image_url", "").strip()
    is_published = bool(request.POST.get("is_published"))  # "on" gəlir

    # Sadə validasiya (istəsən form ilə də edə bilərsən)
    if not title or not content:
        return JsonResponse(
            {"success": False, "message": "Başlıq və məzmun tələb olunur."},
            status=400,
        )

    # Məlumatları post-a yaz
    post.title = title
    post.content = content
    post.excerpt = excerpt

    # Kateqoriya
    if category_id:
        try:
            post.category = Category.objects.get(pk=category_id)
        except Category.DoesNotExist:
            post.category = None
    else:
        post.category = None

    # Şəkil faylı
    image_file = request.FILES.get("image")
    if image_file:
        post.image = image_file

    # Şəkil URL
    post.image_url = image_url or None

    # Dərc statusu
    post.is_published = is_published

    # Save
    post.save()

    return JsonResponse({"success": True})


# 2. POSTU SİLMƏ (Təsdiqdən sonra)
@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id, author=request.user)

    if request.method == 'POST':
        # Yalnız POST gələndə silməni icra et (silmə düyməsi POST göndərməlidir)
        post.delete()
        # Və ya sadəcə redirect edirik (çünki JS modalı bağlayıb səhifəni yeniləyir)
        return redirect('user_profile', username=request.user.username)
    
    # Əgər GET gələrsə, xəta veririk və ya sadəcə silməni icra etmədən geri göndəririk
    return redirect('user_profile', username=request.user.username)


def list_posts(request):
    """
    Bütün postların siyahısı (əgər ayrıca page istəyirsənsə).
    """
    posts = (
        Post.objects
        .select_related("category", "author")
        .order_by("-created_at")
    )
    return render(request, "blog/post_list.html", {"posts": posts})


def search_posts(request):
    """
    Sadə search: ?q=... ilə title və excerpt-də axtarır.
    """
    query = request.GET.get("q", "").strip()
    posts = Post.objects.all()

    if query:
        posts = posts.filter(
            title__icontains=query
        ) | posts.filter(
            excerpt__icontains=query
        )

    posts = posts.order_by("-created_at")

    return render(request, "blog/search_results.html", {
        "posts": posts,
        "query": query,
    })


# ------------------- USER REGISTER / PROFILE / LOGOUT ------------------- #

def register_view(request):
    """
    Yeni istifadəçi qeydiyyatı.
    Qeydiyyat uğurlu olduqda user-i login edib onun profil səhifəsinə yönləndiririk.
    """
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data["password"]
            user.set_password(password)  # şifrəni hash-lə saxla
            user.save()
            login(request, user)        # qeydiyyatdan sonra avtomatik login
            return redirect("user_profile", username=user.username)
    else:
        form = RegisterForm()

    return render(request, "blog/register.html", {"form": form})

def user_profile(request, username):
    """
    İstifadəçi profili.
    + Müəllimlər üçün yoxlanmamış (pending) imtahan sayı hesablanır.
    Məntiq: Statusu 'submitted' və ya 'expired' olan, 
            hələ 'checked_by_teacher=False' olan 
            və tipi 'test' OLMAYAN cəhdlər.
    """
    profile_user = get_object_or_404(User, username=username)

    # 1. Postların Filterlənməsi
    if request.user == profile_user:
        # Öz profilinə baxanda – bütün postlar
        user_posts_list = (
            Post.objects
            .filter(author=profile_user)
            .select_related("category")
            .order_by("-created_at")
        )
    else:
        # Başqasının profilinə baxanda – yalnız dərc olunmuşlar
        user_posts_list = (
            Post.objects
            .filter(author=profile_user, is_published=True)
            .select_related("category")
            .order_by("-created_at")
        )
    
    # 2. Pagination
    paginator = Paginator(user_posts_list, 4)
    page_number = request.GET.get('page')
    try:
        posts = paginator.page(page_number)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        posts = paginator.page(paginator.num_pages)

    # 3. YOXLANILMAMIŞ İMTAHANLARIN SAYI (Düzəliş edilən hissə)
    pending_count = 0
    
    # Şərt: Login olub + Öz profilidir + Müəllimdir
    if request.user.is_authenticated and request.user == profile_user and getattr(request.user, 'is_teacher', False):
        pending_count = ExamAttempt.objects.filter(
            exam__author=request.user,           # Müəllimin öz imtahanları
            status__in=['submitted', 'expired'], # Tələbə bitirib (və ya vaxtı bitib)
            checked_by_teacher=False             # Müəllim hələ "Təsdiq" etməyib
        ).exclude(
            exam__exam_type='test'               # ƏSAS DÜZƏLİŞ: Testləri siyahıdan çıxarırıq
        ).count()

    # 4. Kateqoriyalar
    categories = Category.objects.all().order_by('name') 

    context = {
        "profile_user": profile_user,
        "posts": posts,
        "categories": categories,
        "pending_count": pending_count, 
    }
    return render(request, "blog/user_profile.html", context)


def logout_view(request):
    """
    İstifadəçini çıxış etdirib ana səhifəyə yönləndirir.
    """
    logout(request)
    return redirect("home")


# ------------------- CATEGORY DETAIL ------------------- #

def category_detail(request, slug):
    # 1. Hazırkı seçilmiş kateqoriyanı tapırıq (yoxdursa 404 qaytarır)
    category = get_object_or_404(Category, slug=slug)

    # 2. YALNIZ bu kateqoriyaya aid olan və yayımlanmış postları tapırıq
    posts = Post.objects.filter(category=category, is_published=True).order_by("-created_at")

    # 3. Sidebar üçün bütün kateqoriyaları və post saylarını hesablayırıq (Home view-dakı kimi)
    categories = (
        Category.objects
        .annotate(post_count=Count('posts', filter=Q(posts__is_published=True)))
        .filter(post_count__gt=0)
        .order_by('name')
    )

    context = {
        'category': category,   # Başlıqda adını yazmaq üçün
        'posts': posts,         # Süzülmüş postlar
        'categories': categories # Sidebar üçün siyahı
    }

    return render(request, 'blog/category_detail.html', context)


# ------------------- QUESTION SUBMISSION ------------------- #

@login_required
def create_question(request):
    # Yalnız teacher qrupu olanlar sual yarada bilsin
    if not request.user.is_teacher:
        raise PermissionDenied("Bu səhifə yalnız müəllimlər üçündür.")

    if request.method == "POST":
        form = QuestionForm(request.POST)
        if form.is_valid():
            question = form.save(commit=False)
            question.author = request.user
            question.save()
            form.save_m2m()  # visible_users üçün lazımdır
            return redirect("my_questions")
    else:
        form = QuestionForm()

    return render(request, "blog/create_question.html", {
        "form": form
    })


@login_required
def my_questions(request):
    """
    Bu view müəllimin öz yaratdığı sualları göstərir.
    """
    questions = Question.objects.filter(author=request.user).order_by("-created_at")
    return render(request, "blog/my_questions.html", {
        "questions": questions
    })


@login_required
def questions_i_can_see(request):
    """
    Bu view login olan user-in görə bildiyi bütün sualları göstərir.
    visible_to_all = True olanlar,
    + author = user olanlar,
    + visible_users siyahısında user olanlar.
    """
    from django.db.models import Q

    questions = (
        Question.objects
        .filter(
            Q(visible_to_all=True) |
            Q(author=request.user) |
            Q(visible_users=request.user)
        )
        .distinct()
        .select_related("author")
    )

    return render(request, "blog/questions_i_can_see.html", {
        "questions": questions
    })


# ------------------- EXAM VIEWS (BÖLÜM 3) ------------------- #

def _ensure_teacher(user):
    if not getattr(user, "is_teacher", False):
        raise PermissionDenied("Bu səhifə yalnız müəllimlər üçündür.")


@login_required
def teacher_exam_list(request):
    """
    Müəllimin yaratdığı bütün imtahanların siyahısı.
    """
    _ensure_teacher(request.user)
    exams = Exam.objects.filter(author=request.user).order_by("-created_at")
    return render(request, "blog/teacher_exam_list.html", {
        "exams": exams,
    })


@login_required
def create_exam(request):
   
    _ensure_teacher(request.user)

    if request.method == "POST":
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.author = request.user
            exam.save()
            # form.save(commit=False) etdiyimiz üçün related sahələri sonra saxlayırıq
            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamForm()

    return render(request, "blog/create_exam.html", {
        "form": form,
    })


@login_required
def teacher_exam_detail(request, slug):
    """
    Müəllim üçün konkret imtahanın detal səhifəsi:
    - məlumat
    - suallar
    - 'Sual əlavə et' düyməsi
    (sonra bura statistikalar, attempts və s. də əlavə ediləcək).
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    questions = exam.questions.all().order_by("order")

    return render(request, "blog/teacher_exam_detail.html", {
        "exam": exam,
        "questions": questions,
    })


@login_required
def add_exam_question(request, slug):
    """
    Müəllim imtahana sual əlavə edir.
    Test imtahanı üçün variantlar da eyni formda daxil olunur.
    Yazılı imtahan üçün yalnız sual mətni + ideal cavab hissəsi istifadə edilir.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if request.method == "POST":
        form = ExamQuestionCreateForm(request.POST, exam_type=exam.exam_type)
        if form.is_valid():
            # Sualı yaradıq
            last_q = exam.questions.order_by("-order").first()
            next_order = (last_q.order + 1) if last_q else 1

            question = form.save(commit=False)
            question.exam = exam
            question.order = next_order

            # Yazılı imtahan üçün answer_mode-u zorla "single" edə bilərik
            if exam.exam_type == "written":
                question.answer_mode = "single"

            question.save()

            # Əgər exam tipi testdirsə → variantları yarat
            if exam.exam_type == "test":
                form.create_options(question)

            # hansı düyməyə basıldığını yoxlayaq
            if "save_and_continue" in request.POST:
                # eyni imtahan üçün yenidən boş formada aç
                return redirect("add_exam_question", slug=exam.slug)
            else:
                # Sadəcə imtahan detalına qayıt
                return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamQuestionCreateForm(exam_type=exam.exam_type)

    return render(request, "blog/add_exam_question.html", {
        "exam": exam,
        "form": form,
    })



@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt aktiv/deaktiv edə bilsin.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if request.method == "POST":
        exam.is_active = not exam.is_active
        exam.save()
    return redirect("teacher_exam_detail", slug=exam.slug)


@login_required
def edit_exam(request, slug):
    """
    Mövcud imtahanın parametrlərini redaktə etmək.
    (ad, tip, vaxt, attempt limiti, aktiv/passiv və s.)
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if request.method == "POST":
        form = ExamForm(request.POST, instance=exam)
        if form.is_valid():
            form.save()
            # Sadə success sonrası imtahan detalına qayıdırıq
            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamForm(instance=exam)

    return render(request, "blog/edit_exam.html", {
        "exam": exam,
        "form": form,
    })


@login_required
def delete_exam(request, slug):
    """
    İmtahanı silmək – amma əvvəlcə təsdiq istəyəciyik.
    Əgər imtahan üzrə cəhd (attempt) varsa, silməyə icazə vermirik.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if exam.attempts.exists():
        # sadə variant: hazırda cəhd varsa silməyə icazə vermirik
        # istəsən bunu sonradan dəyişərik
        raise PermissionDenied("Bu imtahan üzrə artıq cəhdlər var, silə bilməzsiniz.")

    if request.method == "POST":
        exam.delete()
        return redirect("teacher_exam_list")

    return render(request, "blog/confirm_delete_exam.html", {"exam": exam})


@login_required
def edit_exam_question(request, slug, question_id):
    """
    Mövcud sualı redaktə etmək (text, cavab rejimi, vaxt, variantlar və s.).
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            request.POST,
            instance=question,
            exam_type=exam.exam_type,
        )
        if form.is_valid():
            q = form.save(commit=False)
            q.exam = exam

            if exam.exam_type == "written":
                q.answer_mode = "single"

            q.save()

            if exam.exam_type == "test":
                form.save_options(q)

            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamQuestionCreateForm(
            instance=question,
            exam_type=exam.exam_type,
        )

    return render(request, "blog/add_exam_question.html", {
        "exam": exam,
        "form": form,
        "editing": True,
        "question": question,
    })



@login_required
def delete_exam_question(request, slug, question_id):
    """
    Sualı silmək – əvvəlcə təsdiq istənilir.
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)

    if request.method == "POST":
        question.delete()
        return redirect("teacher_exam_detail", slug=exam.slug)

    return render(request, "blog/confirm_delete_question.html", {
        "exam": exam,
        "question": question,
    })





# ---------------- STUDENT TƏRƏFİ -------------------

@login_required
def student_exam_list(request):
    """
    Tələbə üçün görünən imtahanlar:
    - is_active = True
    - attempts_left > 0 (əgər limit qoyulubsa)
    """
    exams = Exam.objects.filter(is_active=True).order_by("-created_at")
    available_exams = []
    for exam in exams:
        left = exam.attempts_left_for(request.user)
        # left == None → limitsiz, yoxsa 0-dan böyük olmalıdır
        if left is None or left > 0:
            available_exams.append((exam, left))

    return render(request, "blog/student_exam_list.html", {
        "exam_items": available_exams,
    })


@login_required
def start_exam(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    # Bu userin bu imtahan üzrə bütün cəhdləri
    qs = exam.attempts.filter(user=request.user).order_by("-started_at")

    # 1) Davam edən attempt varsa → ora yönləndir
    current = qs.filter(status__in=["draft", "in_progress"]).first()
    if current:
        return redirect("take_exam", slug=exam.slug, attempt_id=current.id)

    # 2) Bitmiş cəhdlərin sayı
    finished_qs = qs.filter(status__in=["submitted", "expired"])
    finished_count = finished_qs.count()

    # 3) Max attempt – default 1 olsun
    max_attempts = exam.max_attempts_per_user or 1

    if finished_count >= max_attempts:
        # Artıq yeni attempt YOX, sadəcə son nəticəyə buraxırıq
        last = finished_qs.first()
        if last:
            return redirect("exam_result", slug=exam.slug, attempt_id=last.id)
        return redirect("student_exam_list")

    # 4) Yeni attempt yaradılır
    attempt_number = finished_count + 1
    attempt = ExamAttempt.objects.create(
        user=request.user,
        exam=exam,
        attempt_number=attempt_number,
        status="in_progress",
    )

    return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)

@login_required
def take_exam(request, slug, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        exam__slug=slug,
        user=request.user,
    )
    exam = attempt.exam

    # Əgər artıq bitibsə, nəticəyə at
    if attempt.is_finished:
        return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

    questions = ExamQuestion.objects.filter(
        exam=exam
    ).order_by('order', 'id').prefetch_related("options")

    # --- Server tərəfli Vaxt Hesablaması ---
    remaining_seconds = None
    is_time_up = False

    if exam.total_duration_minutes and attempt.started_at:
        now = timezone.now()
        finish_time = attempt.started_at + timedelta(minutes=exam.total_duration_minutes)
        diff = finish_time - now
        total_seconds = diff.total_seconds()
        
        if total_seconds <= 0:
            is_time_up = True
            remaining_seconds = 0
        else:
            remaining_seconds = int(total_seconds)

    if request.method == "POST":
        action = (request.POST.get("submit_action") or "").strip()
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

        # 1. Cavabları yadda saxla
        for q in questions:
            ans, created = ExamAnswer.objects.get_or_create(
                attempt=attempt,
                question=q
            )
            ans.selected_options.clear()

            if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
                if q.answer_mode == "single":
                    opt_id = request.POST.get(f"q_{q.id}")
                    if opt_id:
                        opt = q.options.filter(id=opt_id).first()
                        if opt:
                            ans.selected_options.add(opt)
                else:
                    for opt in q.options.all():
                        if request.POST.get(f"q_{q.id}_opt_{opt.id}"):
                            ans.selected_options.add(opt)

                ans.text_answer = ""
                ans.auto_evaluate()

            else:
                text = request.POST.get(f"q_{q.id}", "").strip()
                ans.text_answer = text
                ans.is_correct = False
                ans.save()

                # Fayllar (yazılı suallar üçün)
                files = request.FILES.getlist(f"file_{q.id}[]")
                if files:
                    # köhnə faylları silib yenisini yazırıq (duplikat olmasın deyə)
                    ans.files.all().delete()
                    for f in files:
                        ExamAnswerFile.objects.create(answer=ans, file=f)

        if exam.exam_type == "test":
            attempt.recalculate_score()

        # 2. Status qərarı
        if action == "finish" or is_time_up:
            status = "expired" if is_time_up else "submitted"
            attempt.mark_finished(status=status)

            if is_ajax:
                return JsonResponse({
                    "success": True,
                    "finished": True,
                    "redirect_url": reverse(
                        "exam_result",
                        kwargs={"slug": exam.slug, "attempt_id": attempt.id}
                    ),
                })
            return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

        # autosave və ya "draft kimi saxla"
        attempt.status = "draft"
        attempt.save(update_fields=["status"])

        if is_ajax:
            return JsonResponse({"success": True, "finished": False})

        return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)

    # GET sorğusu
    answers = attempt.answers.select_related("question").prefetch_related("selected_options", "files")
    answers_by_qid = {a.question_id: a for a in answers}

    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "answers_by_qid": answers_by_qid,
        "remaining_seconds": remaining_seconds,
    }
    return render(request, "blog/take_exam.html", context)




@login_required
def exam_result(request, slug, attempt_id):
    """
    Student üçün konkret attempt-in nəticə səhifəsi.
    """
    exam = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam, user=request.user)

    questions = exam.questions.all().order_by("order").prefetch_related("options")
    answers = (
        ExamAnswer.objects
        .filter(attempt=attempt)
        .prefetch_related("selected_options", "files")
    )
    answers_by_qid = {a.question_id: a for a in answers}

    return render(request, "blog/exam_result.html", {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "answers_by_qid": answers_by_qid,
    })


@login_required
def student_exam_history(request):
    # Tələbənin bitirdiyi və ya vaxtı bitmiş bütün cəhdləri gətiririk
    attempts = ExamAttempt.objects.filter(
        user=request.user, 
        status__in=['submitted', 'graded', 'expired']
    ).order_by('-started_at')

    context = {
        'attempts': attempts
    }
    return render(request, 'blog/student_exam_history.html', context)

# ---------------- TEACHER EXAM RESULTS ------------------- #

@login_required
def teacher_exam_results(request, slug):
    """
    Müəllim üçün imtahan nəticələri:
    - solda bütün cəhdlər cədvəli
    - aşağıda/sağda seçilmiş cəhdin cavabları + qiymətləndirmə formu
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    attempts = exam.attempts.select_related("user").order_by("-started_at")

    selected_attempt = None
    selected_answers = None

    # ---------- POST: müəllim bal + feedback saxlayır ----------
    if request.method == "POST":
        attempt_id = request.POST.get("attempt_id")
        score_raw = request.POST.get("teacher_score", "").strip()
        feedback = request.POST.get("teacher_feedback", "").strip()

        selected_attempt = get_object_or_404(
            ExamAttempt,
            id=attempt_id,
            exam=exam
        )

        if score_raw:
            try:
                score_val = int(score_raw)
            except ValueError:
                messages.error(request, "Bal tam ədəd olmalıdır.")
            else:
                if 0 <= score_val <= 100:
                    selected_attempt.teacher_score = score_val
                    selected_attempt.teacher_feedback = feedback
                    selected_attempt.mark_checked()
                    messages.success(request, "Bal və rəy yadda saxlanıldı.")
                    # yenidən eyni attempt seçilmiş halda geri dön
                    return redirect(f"{request.path}?attempt={selected_attempt.id}")
                else:
                    messages.error(request, "Bal 0–100 aralığında olmalıdır.")
        else:
            # yalnız feedback saxlanılır
            selected_attempt.teacher_score = None
            selected_attempt.teacher_feedback = feedback
            selected_attempt.checked_by_teacher = False
            selected_attempt.save(
                update_fields=["teacher_score", "teacher_feedback", "checked_by_teacher"]
            )
            messages.success(request, "Rəy yadda saxlanıldı.")
            return redirect(f"{request.path}?attempt={selected_attempt.id}")

    # ---------- GET: hansı attempt seçilib? ----------
    if selected_attempt is None:
        attempt_param = request.GET.get("attempt")
        if attempt_param:
            selected_attempt = (
                exam.attempts
                .filter(id=attempt_param)
                .select_related("user")
                .first()
            )

    if selected_attempt:
        selected_answers = (
            ExamAnswer.objects
            .filter(attempt=selected_attempt)
            .select_related("question")
            .order_by("question__order", "question__id")
        )

    # Statistikalar (sənin əvvəlki kodun kimi qalsın)
    fastest_attempts = sorted(
        [a for a in attempts if a.duration_seconds],
        key=lambda a: a.duration_seconds
    )[:5]

    questions = exam.questions.all()
    hardest_questions = sorted(
        questions,
        key=lambda q: q.correct_ratio
    )[:5]

    return render(request, "blog/teacher_exam_results.html", {
        "exam": exam,
        "attempts": attempts,
        "fastest_attempts": fastest_attempts,
        "hardest_questions": hardest_questions,
        "selected_attempt": selected_attempt,
        "selected_answers": selected_answers,
    })


@login_required
def teacher_check_attempt(request, slug, attempt_id):
    """
    Müəllim yazılı/praktiki imtahandakı BİR cəhdi sual-sual yoxlayır.
    Hər suala bal və feedback yaza bilir.
    """
    _ensure_teacher(request.user)

    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    # İstəsən yalnız yazılı imtahanları məhdudlaşdıra bilərik
    # if exam.exam_type != "written":
    #     return redirect("teacher_exam_results", slug=exam.slug)

    questions = exam.questions.all().order_by("order", "id")

    # Mövcud cavabları xəritəyə çeviririk
    existing_answers = {
        a.question_id: a
        for a in ExamAnswer.objects.filter(
            attempt=attempt,
            question__exam=exam
        )
    }

    if request.method == "POST":
        total_score = 0
        any_score = False

        for q in questions:
            ans = existing_answers.get(q.id)
            if not ans:
                # Normalda hamısı olmalıdır, amma safety üçün:
                ans = ExamAnswer.objects.create(
                    attempt=attempt,
                    question=q,
                )

            score_raw = request.POST.get(f"score_{q.id}", "").strip()
            feedback = request.POST.get(f"feedback_{q.id}", "").strip()

            if score_raw == "":
                ans.teacher_score = None
            else:
                try:
                    score_val = int(score_raw)
                except ValueError:
                    score_val = 0
                ans.teacher_score = score_val
                total_score += score_val
                any_score = True

            ans.teacher_feedback = feedback
            ans.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])

        # Cəmi balı attempt səviyyəsinə yazırıq.
        # Sən özün qərar verərsən ki, sual ballarını elə böləsən ki,
        # cəmi 100 olsun.
        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        attempt.save(update_fields=["teacher_score", "checked_by_teacher"])

        messages.success(request, "İmtahan cəhdi uğurla yoxlanıldı.")
        return redirect("teacher_exam_results", slug=exam.slug)

    # GET sorğusu – suallar + cavablar siyahısı
    qa_list = []
    for q in questions:
        qa_list.append({
            "question": q,
            "answer": existing_answers.get(q.id),
        })

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": qa_list,
    }
    return render(request, "blog/teacher_check_attempt.html", context)


@login_required
def teacher_pending_attempts(request):
    """
    Müəllimin bütün imtahanlarından yığılmış, 
    yoxlanılmağı gözləyən (Pending) işlərin siyahısı.
    """
    # Yalnız müəllimlər görə bilsin
    if not getattr(request.user, 'is_teacher', False):
        return render(request, '403_forbidden.html') # Və ya redirect

    # Yoxlanılacaq işləri tapırıq
    pending_attempts = ExamAttempt.objects.filter(
        exam__author=request.user,           # Bu müəllimin imtahanları
        status__in=['submitted', 'expired'], # Bitmiş imtahanlar
        checked_by_teacher=False             # Hələ yoxlanmayıb
    ).exclude(
        exam__exam_type='test'               # Testləri çıxarırıq
    ).select_related('user', 'exam').order_by('finished_at') # Ən köhnədən yeniyə

    context = {
        'pending_attempts': pending_attempts,
    }
    return render(request, 'blog/teacher_pending_attempts.html', context)