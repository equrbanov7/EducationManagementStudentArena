# blog/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.views.decorators.http import require_POST
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
from .models import Post, Category, Comment, Subscriber, Question, Exam, ExamQuestion, ExamQuestionOption, ExamAttempt, ExamAnswer, ExamAnswerFile, StudentGroup, QuestionBlock
from .forms import (
    SubscriptionForm,
    RegisterForm,
    PostForm,
    CommentForm,
    QuestionForm,
    ExamForm, ExamQuestionCreateForm,
    StudentGroupForm
    
)
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import random  # Faylın ən başında olsun
import re
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
    paginator = Paginator(user_posts_list, 6)
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
        form = ExamForm(request.POST, user=request.user)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.author = request.user
            exam.save()
            form.save_m2m()
            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamForm(user=request.user)

    return render(request, "blog/create_exam.html", {"form": form})


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


# 1. Səhifəni açan view (YENİLƏNİB)
def create_question_bank(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    
    # Mövcud blokları gətiririk ki, ekranda görsənsin
    blocks = exam.question_blocks.all().order_by('order')
    
    # Hər blok üçün sualları mətn formatına çeviririk (Textarea üçün)
    # Məsələn: [ {block_obj: block, text_content: "1. Salam\n2. Necəsən"}, ... ]
    blocks_data = []
    for block in blocks:
        questions = block.questions.all().order_by('order')
        # Sualları "1. Sual mətni" formatında birləşdiririk
        text_content = "\n".join([f"{q.order}. {q.text}" for q in questions])
        
        blocks_data.append({
            'obj': block,
            'text_content': text_content
        })

    return render(request, 'blog/create_question_bank.html', {
        'exam': exam,
        'blocks_data': blocks_data
    })

# views.py (Yalnız bu funksiyanı yeniləyin)

def process_question_bank(request, slug):
    exam = get_object_or_404(Exam, slug=slug)
    
    if request.method == "POST":
        # 1. Silinməli olan blokları silirik
        # Frontend-dən vergüllə ayrılmış ID-lər gələcək (məs: "5,8,12")
        deleted_ids = request.POST.get('deleted_block_ids', '').split(',')
        for d_id in deleted_ids:
            if d_id.strip():
                QuestionBlock.objects.filter(id=d_id, exam=exam).delete()

        # 2. Ümumi sual sayını yenilə
        random_count = request.POST.get('random_question_count')
        if random_count:
            exam.random_question_count = int(random_count)
            exam.save()

        # Adların təkrar olub-olmadığını yoxlamaq üçün set
        used_names = set()

        # 3. Blokları emal edirik
        for key, value in request.POST.items():
            if key.startswith('block_name_'):
                ui_id = key.split('_')[-1]
                block_name = value.strip()
                
                # Validation: Eyni sorğuda dublikat ad varmı?
                if block_name.lower() in used_names:
                    messages.error(request, f"Diqqət: '{block_name}' adlı blok artıq mövcuddur. Zəhmət olmasa fərqli adlardan istifadə edin.")
                    return redirect('create_question_bank', slug=exam.slug)
                used_names.add(block_name.lower())

                content_key = f'block_content_{ui_id}'
                content_text = request.POST.get(content_key, '')
                time_key = f'block_time_{ui_id}'
                time_val = request.POST.get(time_key)
                db_id_key = f'block_db_id_{ui_id}'
                db_id = request.POST.get(db_id_key)

                # Validation: Bazada başqa blok eyni adda varmı? (özü xaric)
                existing_check = QuestionBlock.objects.filter(exam=exam, name__iexact=block_name)
                if db_id:
                    existing_check = existing_check.exclude(id=db_id)
                
                if existing_check.exists():
                    messages.error(request, f"'{block_name}' adlı blok artıq bazada mövcuddur.")
                    return redirect('create_question_bank', slug=exam.slug)

                if block_name:
                    # Blok Yaradılması/Yenilənməsi
                    if db_id:
                        # Bazada yoxlayırıq ki, silinməyibsə (concurrency üçün)
                        block_qs = QuestionBlock.objects.filter(id=db_id)
                        if block_qs.exists():
                            block = block_qs.first()
                            block.name = block_name
                            block.time_limit_minutes = int(time_val) if time_val else None
                            block.save()
                            # Sualları yeniləyirik
                            block.questions.all().delete()
                        else:
                            continue # Blok tapılmadısa keçirik
                    else:
                        block = QuestionBlock.objects.create(
                            exam=exam,
                            name=block_name,
                            time_limit_minutes=int(time_val) if time_val else None,
                            order=ui_id
                        )

                    # Sualların Parse edilməsi
                    if content_text.strip():
                        pattern = r'(?:\n|^)\s*\d+[\.\)]\s+'
                        questions = re.split(pattern, content_text)
                        questions = [q.strip() for q in questions if q.strip()]
                        
                        for index, q_text in enumerate(questions, start=1):
                            ExamQuestion.objects.create(
                                exam=exam,
                                block=block,
                                text=q_text,
                                order=index,
                                answer_mode='single'
                            )
        
        messages.success(request, "Sual bankı uğurla yadda saxlanıldı!")
        return redirect('teacher_exam_detail', slug=exam.slug)
    
    return redirect('create_question_bank', slug=exam.slug)



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
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    if request.method == "POST":
        form = ExamForm(request.POST, instance=exam, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamForm(instance=exam, user=request.user)

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
    user = request.user
    
    # 1. BAZA SORĞUSU (İlkin Filter)
    # Hələ icazələri yoxlamırıq, sadəcə aktivləri gətiririk
    exams_qs = Exam.objects.filter(is_active=True).select_related('author')

    # --- SEARCH (Axtarış) ---
    search_query = request.GET.get('q')
    if search_query:
        # İmtahan adı və ya müəllim adına görə axtarış
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

    # 2. PYTHON MƏNTİQİ (Permissions & List Construction)
    # Bazadan gələn nəticələri yoxlayıb siyahıya yığırıq
    exam_items = []

    for exam in exams_qs:
        # Bu user ümumiyyətlə bu imtahan kartını görməlidir?
        if not exam.can_user_see(user):
            continue

        # Cəhd limiti
        left = exam.attempts_left_for(user)
        if left is not None and left <= 0:
            # Kartı göstərməyə dəymir – cəhd qalmayıb
            continue

        # Kod tələb olunub–olunmamağı user-ə görə hesablayırıq
        can_without_code, _ = exam.can_user_start(user, code=None)

        requires_code = False
        if exam.access_code and not can_without_code:
            requires_code = True

        # Ekrandakı status yazısı
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

    # 3. PAGINATION (Səhifələmə)
    # Hər səhifədə 6 imtahan göstərək
    paginator = Paginator(exam_items, 2) 
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        # Əgər page rəqəm deyilsə, birinci səhifəni göstər
        page_obj = paginator.page(1)
    except EmptyPage:
        # Əgər səhifə limitdən kənardırsa, sonuncu səhifəni göstər
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "page_obj": page_obj,      # Pagination idarəetməsi üçün (_pagination.html buna baxır)
        "exam_items": page_obj,    # Siyahını dövr etmək üçün (Template-dəki for loop buna baxır)
    }

    return render(request, "blog/student_exam_list.html", context)





def _start_or_resume_attempt(request, exam: Exam):
    user = request.user

    qs = exam.attempts.filter(user=user).order_by("-started_at")

    # Davam edən attempt varsa – ora gedək
    current = qs.filter(status__in=["draft", "in_progress"]).first()
    if current:
        return redirect("take_exam", slug=exam.slug, attempt_id=current.id)

    # Bitmiş cəhdlər
    finished_qs = qs.filter(status__in=["submitted", "expired"])
    finished_count = finished_qs.count()

    max_attempts = exam.max_attempts_per_user or 1
    if finished_count >= max_attempts:
        last = finished_qs.first()
        if last:
            return redirect("exam_result", slug=exam.slug, attempt_id=last.id)
        return redirect("student_exam_list")

    attempt_number = finished_count + 1
    attempt = ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=attempt_number,
        status="in_progress",
    )
    
    generate_random_questions_for_attempt(attempt)
    
    return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)


@login_required
def start_exam(request, slug):
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    can_start, reason = exam.can_user_start(request.user, code=None)
    if not can_start:
        messages.error(request, reason or "Bu imtahana başlaya bilmirsiniz.")
        return redirect("student_exam_list")

    return _start_or_resume_attempt(request, exam)


@csrf_exempt   # DEV üçün CSRF-dən azad edirik (sonra istəsən götürərsən)
@login_required
@require_POST
def exam_code_check(request):
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        messages.error(request, reason or "İmtahana başlamaq mümkün olmadı.")
        return redirect("student_exam_list")

    return _start_or_resume_attempt(request, exam)




def generate_random_questions_for_attempt(attempt):
    """
    Bu funksiya yeni yaradılan cəhd (attempt) üçün sualları seçir.
    Əgər 'random_question_count' varsa, bloklardan bərabər sayda seçir.
    Yoxdursa, bütün sualları götürür.
    """
    exam = attempt.exam
    
    # Əgər random limiti yoxdursa (0), bütün sualları seç
    if not exam.random_question_count:
        selected_qs = list(exam.questions.all().order_by('order'))
    else:
        # Sual Bankı Məntiqi
        all_blocks = list(exam.question_blocks.all())
        selected_qs = []
        total_needed = exam.random_question_count

        if all_blocks:
            # Bloklar varsa, bərabər bölmək
            blocks_count = len(all_blocks)
            base_count = total_needed // blocks_count # Hər bloka düşən əsas pay
            remainder = total_needed % blocks_count   # Qalıq suallar

            # Qalıq sualları paylamaq üçün blokları qarışdırırıq
            # Məsələn: 2 qalıq varsa, təsadüfi 2 fərqli blokdan 1 əlavə sual götürəcəyik
            random.shuffle(all_blocks)

            for i, block in enumerate(all_blocks):
                # Bu blokdan neçə sual götürməliyik?
                count_to_take = base_count
                if i < remainder:
                    count_to_take += 1
                
                # Blokun suallarını qarışdırıb götürürük
                block_qs = list(block.questions.all())
                random.shuffle(block_qs)
                selected_qs.extend(block_qs[:count_to_take])
            
            # Əgər bloklardan gələn sual sayı azdırsa (məsələn blokda sual çatmırsa),
            # çatışmayanları random doldura bilərik (optional)
        else:
            # Blok yoxdursa, sadəcə bütün suallardan random seç
            all_qs = list(exam.questions.all())
            random.shuffle(all_qs)
            selected_qs = all_qs[:total_needed]

    # Seçilmiş sualları ExamAnswer cədvəlinə əlavə edirik (boş cavabla)
    # Bu bizə imkan verir ki, tələbə refresh edəndə suallar dəyişməsin
    final_questions = []
    for q in selected_qs:
        ExamAnswer.objects.create(
            attempt=attempt,
            question=q
        )

@login_required
def take_exam(request, slug, attempt_id):
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        exam__slug=slug,
        user=request.user,
    )
    exam = attempt.exam

    if attempt.is_finished:
        return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

    # --- DÜZƏLİŞ: Sualları Attempt-ə bağlanmış cavablardan götürürük ---
    # Bu sayədə yalnız seçilmiş (random) suallar görünür.
    answers_qs = attempt.answers.select_related("question").order_by('id') 
    # order_by('id') qoyduq ki, qarışıq gələn suallar hər dəfə yerini dəyişməsin
    
    # Əgər nəsə xəta olub suallar yaranmayıbsa (köhnə koddan qalan attemptlər üçün)
    if not answers_qs.exists():
         generate_random_questions_for_attempt(attempt)
         answers_qs = attempt.answers.select_related("question").order_by('id')

    # Template-ə ötürmək üçün suallar siyahısı
    questions = [a.question for a in answers_qs] 
    # Options-ları da yükləmək üçün (prefetch manual edilir)
    from django.db.models import Prefetch
    # Bu hissə bir az performance üçün optimallaşdırıla bilər, amma sadə yol:
    for q in questions:
        # options-ları template-də q.options.all kimi işlətmək üçün cache edirik
        pass 
        # Django template-də q.options.all çağıranda onsuzda işləyəcək, 
        # amma prefetch_related işlətmək istəsəniz ExamQuestion səviyyəsində edə bilərsiz.
    
    # --- Server tərəfli Vaxt Hesablaması (Olduğu kimi qalır) ---
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

        # DÜZƏLİŞ: Yalnız seçilmiş suallar üzərindən dövr edirik
        for q in questions:
            # Cavab obyekti artıq var, onu tapırıq
            ans = ExamAnswer.objects.get(attempt=attempt, question=q)
            
            ans.selected_options.clear()

            if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
                if q.answer_mode == "single":
                    opt_id = request.POST.get(f"q_{q.id}")
                    if opt_id:
                        # Variantın düzgün suala aid olduğunu yoxla
                        opt = ExamQuestionOption.objects.filter(id=opt_id, question=q).first()
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
                
                files = request.FILES.getlist(f"file_{q.id}[]")
                if files:
                    ans.files.all().delete()
                    for f in files:
                        ExamAnswerFile.objects.create(answer=ans, file=f)

        if exam.exam_type == "test":
            attempt.recalculate_score()

        if action == "finish" or is_time_up:
            status = "expired" if is_time_up else "submitted"
            attempt.mark_finished(status=status)
            if is_ajax:
                return JsonResponse({
                    "success": True, 
                    "finished": True, 
                    "redirect_url": reverse("exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id})
                })
            return redirect("exam_result", slug=exam.slug, attempt_id=attempt.id)

        attempt.status = "draft"
        attempt.save(update_fields=["status"])
        if is_ajax:
            return JsonResponse({"success": True, "finished": False})
        return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)

    # GET sorğusu üçün answers map
    answers_by_qid = {a.question_id: a for a in answers_qs}

    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions, # Artıq bu filterlənmiş suallardır
        "answers_by_qid": answers_by_qid,
        "remaining_seconds": remaining_seconds,
    }
    return render(request, "blog/take_exam.html", context)





@login_required
def exam_result(request, slug, attempt_id):
    """
    Student üçün konkret attempt-in nəticə səhifəsi.
    Yalnız həmin attempt üçün seçilmiş suallar göstərilir.
    """
    exam = get_object_or_404(Exam, slug=slug)
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        exam=exam,
        user=request.user
    )

    # YALNIZ bu attempt-ə düşən suallar:
    answers_qs = (
        attempt.answers
        .select_related("question")
        .prefetch_related(
            "selected_options",
            "files",
            "question__options",
        )
        .order_by("id")  # attempt yaranma ardıcıllığı ilə
    )

    # Template-də istifadə üçün:
    questions = [a.question for a in answers_qs]
    answers_by_qid = {a.question_id: a for a in answers_qs}

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
    Yalnız həmin attempt-ə düşən sualları göstərir.
    """
    _ensure_teacher(request.user)

    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    # ✅ YALNIZ attempt-də yaranmış cavablar (yəni düşən suallar)
    answers_qs = (
        attempt.answers
        .select_related("question")
        .prefetch_related("files", "selected_options", "question__options")
        .order_by("id")
    )

    # attempt-də cavablar yoxdursa (köhnə attemptlər üçün safety)
    if not answers_qs.exists():
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers
            .select_related("question")
            .prefetch_related("files", "selected_options", "question__options")
            .order_by("id")
        )

    # Template üçün sual+cavab listi (artıq hamısı attempt-ə aid)
    qa_list = [{"question": a.question, "answer": a} for a in answers_qs]

    if request.method == "POST":
        total_score = 0
        any_score = False

        for a in answers_qs:
            q = a.question

            score_raw = (request.POST.get(f"score_{q.id}") or "").strip()
            feedback = (request.POST.get(f"feedback_{q.id}") or "").strip()

            if score_raw == "":
                a.teacher_score = None
            else:
                try:
                    score_val = int(score_raw)
                except ValueError:
                    score_val = 0
                a.teacher_score = score_val
                total_score += score_val
                any_score = True

            a.teacher_feedback = feedback
            a.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])

        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        attempt.save(update_fields=["teacher_score", "checked_by_teacher"])

        messages.success(request, "İmtahan cəhdi uğurla yoxlanıldı.")
        return redirect("teacher_exam_results", slug=exam.slug)

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

# --- 1. SİYAHI VƏ MODAL ÜÇÜN FORM ---
@login_required
def teacher_group_list(request):
    # Bu funksiya yəqin ki sizdə var (müəllim olduğunu yoxlayan)
    # _ensure_teacher(request.user) 
    
    # Müəllimin mövcud qrupları
    groups = StudentGroup.objects.filter(teacher=request.user).prefetch_related("students")
    
    # DÜZƏLİŞ: Formu yaradarkən 'teacher' parametrini ötürürük
    # Bu, formun __init__ metodunda işlənəcək və tələbə siyahısını filterləyəcək
    form = StudentGroupForm(teacher=request.user)
    
    context = {
        "groups": groups,
        "form": form
    }
    return render(request, "blog/teacher_group_list.html", context)


# --- 2. YENİ QRUP YARATMAQ (POST) ---
@login_required
@require_POST
def teacher_create_group(request):
    # _ensure_teacher(request.user)
    
    # DÜZƏLİŞ: POST sorğusunu qəbul edərkən də 'teacher' ötürürük
    form = StudentGroupForm(request.POST, teacher=request.user)
    
    if form.is_valid():
        group = form.save(commit=False)
        group.teacher = request.user  # Qrupu bu müəllimə bağlayırıq
        group.save()
        form.save_m2m()  # ManyToMany (tələbələr) üçün vacibdir
        
    return redirect('teacher_group_list')


# --- 3. QRUPU YENİLƏMƏK (UPDATE - POST) ---
@login_required
@require_POST
def teacher_update_group(request, group_id):
    # _ensure_teacher(request.user)
    
    # Yalnız bu müəllimin qrupunu tapırıq
    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user)
    
    # DÜZƏLİŞ: 'instance=group' və 'teacher=request.user'
    form = StudentGroupForm(request.POST, instance=group, teacher=request.user)
    
    if form.is_valid():
        form.save()
        
    return redirect('teacher_group_list')


# --- 4. QRUPU SİLMƏK (DELETE) ---
@login_required
def teacher_delete_group(request, group_id):
    # _ensure_teacher(request.user)
    
    group = get_object_or_404(StudentGroup, id=group_id, teacher=request.user)
    group.delete()
    
    return redirect('teacher_group_list')

@login_required
def create_student_group(request):
    _ensure_teacher(request.user)

    if request.method == "POST":
        form = StudentGroupForm(request.POST, teacher=request.user)
        if form.is_valid():
            group = form.save(commit=False)
            group.teacher = request.user
            group.save()
            form.save_m2m()
            messages.success(request, "Qrup uğurla yaradıldı.")
            return redirect("teacher_group_list")
    else:
        form = StudentGroupForm(teacher=request.user)

    return render(request, "blog/create_student_group.html", {"form": form})

