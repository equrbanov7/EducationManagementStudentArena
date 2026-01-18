# blog/views.py
import random
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Max
from django.core.mail import send_mail 
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.template.loader import render_to_string 
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import timedelta
from .models import Post, Category, Comment, Subscriber, Question, Exam, ExamQuestion, ExamQuestionOption, ExamAttempt, ExamAnswer, ExamAnswerFile, StudentGroup, QuestionBlock, EmailOTP
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
from django.db.models import Prefetch
from django.db.models import Q
import re
import json
from collections import defaultdict
from docx import Document
import os
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

from .utils import generate_otp, send_verify_email, _save_paint_png_to_answer, _clear_paint_from_answer
from django.db import transaction

User = get_user_model()
signer = TimestampSigner()

LABELS = ["A", "B", "C", "D", "E"]
QUESTION_RE = re.compile(r"^\s*(\d+)\s*[\)\.]\s*(.+)\s*$")
OPTION_RE = re.compile(r"^\s*(\*)?\s*([A-E])\s*[\)\.]\s*(.+)\s*$", re.IGNORECASE)

ANSWERLINE_RE = re.compile(
    r"^\s*(cavab|duz\s*cavab|düz\s*cavab|correct)\s*[:\-]\s*([A-E](?:\s*[,;/]\s*[A-E])*)\s*$",
    re.IGNORECASE
)

def _norm(text: str) -> str:
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t




def normalize_pdf_extracted_text(text: str) -> str:
    """
    PDF-dən çıxan mətni parser üçün uyğun formaya salır:
    - sual nömrələrinin qabağına boş sətir əlavə edir (… \n\n12) …)
    - A–E variantlarının qabağına newline əlavə edir (… \nA) …)
    - "Cavab:" sətrini yeni sətrə keçirir
    - '*' işarəsi ilə variant arasında boşluğu düzəldir (*A) kimi)
    """
    if not text:
        return ""

    t = text.replace("\r", "\n")

    # çoxlu boşluqları normallaşdır
    t = re.sub(r"[ \t]+", " ", t)

    # "Cavab:" həmişə yeni sətirdən başlasın
    t = re.sub(r"(?i)\s+(Cavab\s*:)", r"\n\1", t)

    # "* A)" kimi çıxırsa "*A)" et
    t = re.sub(r"\*\s+([A-E])", r"*\1", t, flags=re.IGNORECASE)

    # Sual nömrələri: " 12)" və ya " 12." -> yeni blok kimi başlasın
    # (Variant daxilində 1) 2) olsa belə parser artıq IN_OPT-də bunu sual saymır, problem olmur.)
    t = re.sub(r"(?<!\n)\s+(\d{1,4})\s*([\)\.])", r"\n\n\1\2", t)

    # Variantlar: " A)" / " *A)" / " B." və s -> yeni sətirdən başlasın
    t = re.sub(r"(?<!\n)\s+(\*?[A-E])\s*([\)\.])", r"\n\1\2", t, flags=re.IGNORECASE)

    # 3+ boş sətiri 2-yə sal
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()



def build_shuffled_options(attempt_id, question):
    opts = list(question.options.all())
    rnd = random.Random(f"{attempt_id}:{question.id}")
    rnd.shuffle(opts)
    packed = []
    for i, opt in enumerate(opts):
        packed.append({
            "id": opt.id,
            "label": LABELS[i] if i < len(LABELS) else "",
            "text": opt.text
        })
    return packed

def _effective_needed_count(exam) -> int:
    """
    0 -> hamısı
    1 -> 1
    10 -> 10
    boş/None -> 10 (default)
    """
    total = exam.questions.count()

    val = getattr(exam, "random_question_count", None)
    if val is None:
        return min(10, total)

    try:
        val = int(val)
    except (TypeError, ValueError):
        return min(10, total)

    if val <= 0:
        return total  # 0 -> hamısı

    return min(val, total)



def _attempt_has_any_answer(attempt) -> bool:
    """
    Tələbə həqiqətən nəsə yazıb/seçibsə True.
    False-positive verməsin deyə count-based yoxlayırıq.
    """
    # text
    if attempt.answers.exclude(text_answer__isnull=True).exclude(text_answer="").exists():
        return True

    # selected options
    if attempt.answers.filter(selected_options__isnull=False).distinct().exists():
        # bu da bəzən false-positive ola bilər, ona görə bir addım da:
        return attempt.answers.filter(selected_options__isnull=False).values("id").distinct().count() > 0

    # files
    if attempt.answers.filter(files__isnull=False).distinct().exists():
        return True

    return False




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
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # password set
            password = form.cleaned_data["password"]
            user.set_password(password)

            # email təsdiqlənənə qədər giriş qadağan
            user.is_active = False
            user.save()

            code = generate_otp()
            EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timezone.timedelta(minutes=10))
            send_verify_email(user, code)

            request.session["pending_verify_email"] = user.email
            messages.success(request, "Email-ə təsdiq kodu göndərildi.")
            return redirect("verify_code")
    else:
        form = RegisterForm()

    return render(request, "blog/register.html", {"form": form})

def verify_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, "Təsdiqləmə üçün email tapılmadı. Yenidən qeydiyyatdan keç.")
        return redirect("register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "User tapılmadı.")
            return redirect("register")

        otp = EmailOTP.objects.filter(user=user, code=code, is_used=False).order_by("-created_at").first()
        if not otp or otp.is_expired():
            messages.error(request, "Kod yanlışdır və ya vaxtı bitib.")
            return render(request, "blog/verify_code.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()

        messages.success(request, "Email təsdiqləndi. İndi daxil ola bilərsən.")
        return redirect("login")

    return render(request, "blog/verify_code.html", {"email": email})

def verify_email_link_view(request):
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=60 * 10)  # 10 dəqiqə
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        messages.success(request, "Email təsdiqləndi. İndi login ola bilərsən.")
        return redirect("login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, "Link yanlışdır və ya vaxtı bitib.")
        return redirect("register")

def resend_code_view(request):
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, "Email tapılmadı.")
        return redirect("register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, "User tapılmadı.")
        return redirect("register")

    code = generate_otp()
    EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timezone.timedelta(minutes=10))
    send_verify_email(user, code)

    messages.success(request, "Yeni kod göndərildi.")
    return redirect("verify_code")


def user_profile(request, username):
    """
    İstifadəçi profili.

    + Müəllimlər üçün yoxlanmamış (pending) imtahan sayı hesablanır.
      Məntiq: Statusu 'submitted' və ya 'expired' olan,
              hələ 'checked_by_teacher=False' olan
              və tipi 'test' OLMAYAN cəhdlər.

    + İstifadəçi (öz profilində) üçün təyin olunmuş (assigned) imtahan sayı hesablanır:
      - Exam.allowed_users içindədirsə
      - və ya Exam.allowed_groups içində olub, həmin qrupun students-i içindədirsə
      - is_active=True
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

    # 3. YOXLANILMAMIŞ İMTAHANLARIN SAYI
    pending_count = 0

    # Şərt: Login olub + Öz profilidir + Müəllimdir
    if (
        request.user.is_authenticated
        and request.user == profile_user
        and getattr(request.user, 'is_teacher', False)
    ):
        pending_count = (
            ExamAttempt.objects
            .filter(
                exam__author=request.user,            # Müəllimin öz imtahanları
                status__in=['submitted', 'expired'],  # Tələbə bitirib (və ya vaxtı bitib)
                checked_by_teacher=False              # Müəllim hələ "Təsdiq" etməyib
            )
            .exclude(exam__exam_type='test')          # Testləri çıxarırıq
            .count()
        )

    # 4. TƏYİN OLUNMUŞ İMTAHANLARIN SAYI (YENİ)
    assigned_count = 0
    if request.user.is_authenticated and request.user == profile_user:
        assigned_count = (
            Exam.objects
            .filter(is_active=True)
            .filter(
                Q(allowed_users=request.user) |
                Q(allowed_groups__students=request.user)
            )
            .distinct()
            .count()
        )

    # 5. Kateqoriyalar
    categories = Category.objects.all().order_by('name')

    context = {
        "profile_user": profile_user,
        "posts": posts,
        "categories": categories,
        "pending_count": pending_count,
        "assigned_count": assigned_count,   # YENİ
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
def createAndEditExamView(request, slug=None):
    """
    Birləşdirilmiş view: Create və Edit
    slug=None -> Yeni imtahan
    slug=<value> -> Mövcud imtahanı redaktə
    """
    _ensure_teacher(request.user)
    
    # Əgər slug varsa -> Edit mode
    if slug:
        exam = get_object_or_404(Exam, slug=slug, author=request.user)
        is_editing = True
    else:
        exam = None
        is_editing = False

    if request.method == "POST":
        if is_editing:
            # Edit mode
            form = ExamForm(request.POST, instance=exam, user=request.user)
        else:
            # Create mode
            form = ExamForm(request.POST, user=request.user)
        
        if form.is_valid():
            exam_instance = form.save(commit=False)
            
            # Yeni imtahanda author-u set et
            if not is_editing:
                exam_instance.author = request.user
            
            exam_instance.save()
            form.save_m2m()  # ManyToMany field-ləri saxla
            
            messages.success(
                request, 
                "İmtahan uğurla yeniləndi!" if is_editing else "İmtahan uğurla yaradıldı!"
            )
            return redirect("teacher_exam_detail", slug=exam_instance.slug)
    else:
        # GET request
        if is_editing:
            form = ExamForm(instance=exam, user=request.user)
        else:
            form = ExamForm(user=request.user)

    return render(request, "blog/createAndEditExam.html", {
        "form": form,
        "exam": exam,
        "is_editing": is_editing,
    })
 
# @login_required
# def create_exam(request):
#     _ensure_teacher(request.user)

#     if request.method == "POST":
#         form = ExamForm(request.POST, user=request.user)
#         if form.is_valid():
#             exam = form.save(commit=False)
#             exam.author = request.user
#             exam.save()
#             form.save_m2m()
#             return redirect("teacher_exam_detail", slug=exam.slug)
#     else:
#         form = ExamForm(user=request.user)

#     return render(request, "blog/create_exam.html", {"form": form})


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
    blocks = QuestionBlock.objects.filter(exam=exam).order_by('order')

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            request.POST,
            request.FILES,
            exam_type=exam.exam_type,
            subject_blocks=blocks
            )
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
        form = ExamQuestionCreateForm(exam_type=exam.exam_type, subject_blocks=blocks)

    return render(request, "blog/add_exam_question.html", {
        "exam": exam,
        "form": form,
    })


# 1. Səhifəni açan view (YENİLƏNİB) Yazili
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


def extract_text_from_upload(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    ext = os.path.splitext(name)[1]

    # təhlükəsizlik: böyük fayl limiti (məs: 5MB)
    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValueError("Fayl çox böyükdür (max 5MB).")

    if ext == ".txt":
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if ext == ".docx":
        # docx.Document file-like də qəbul edir
        doc = Document(uploaded_file)
        lines = []
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if t:
                lines.append(t)
        return "\n".join(lines)

    if ext == ".pdf":
        if PdfReader is None:
            raise ValueError("PDF oxuma üçün 'pypdf' quraşdırılmayıb. `pip install pypdf` edin.")

        reader = PdfReader(uploaded_file)
        parts = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            txt = txt.strip()
            if txt:
                parts.append(txt)

        raw = "\n\n".join(parts)

        # ✅ əsas fix burada
        return normalize_pdf_extracted_text(raw)


    raise ValueError("Yalnız .docx, .pdf, .txt qəbul olunur.")


def parse_bulk_mcq(raw_text: str):
    """
    Output:
      questions: list[
        {
          "q_no": "12" (mətn içindəki nömrə),
          "text": "...",
          "options": {"A": "...", ..., "E": "..."},
          "correct": ["A"] or ["A","C"],
          "answer_mode": "single"|"multiple",
          "warnings": [ {type, msg, ref?}, ... ]
        }
      ]
    """
    lines = raw_text.splitlines()
    OUTSIDE, IN_Q, IN_OPT = 0, 1, 2

    state = OUTSIDE
    current = None
    current_opt_label = None

    def close_option():
        nonlocal current_opt_label
        current_opt_label = None

    def close_question():
        nonlocal current, current_opt_label, state
        if not current:
            return
        close_option()

        # Correct müəyyən et:
        # 1) option-larda * ilə işarələnənlər
        if not current["correct"]:
            # 2) Cavab: A,C sətri ilə verilənlər
            if current.get("_answerline_correct"):
                current["correct"] = current["_answerline_correct"]

        # 3) Heç biri yoxdursa default A
        if not current["correct"]:
            current["correct"] = ["A"]

        # answer_mode set
        current["answer_mode"] = "multiple" if len(current["correct"]) > 1 else "single"

        # cleanup
        current.pop("_answerline_correct", None)
        questions.append(current)

        current = None
        current_opt_label = None
        state = OUTSIDE

    questions = []

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        # Answer line (istənilən yerdə ola bilər)
        m_ans = ANSWERLINE_RE.match(line)
        if m_ans and current:
            labels = re.split(r"\s*[,;/]\s*", m_ans.group(2).upper())
            labels = [x for x in labels if x in list("ABCDE")]
            # uniq preserve order
            seen = set()
            uniq = []
            for x in labels:
                if x not in seen:
                    uniq.append(x)
                    seen.add(x)
            current["_answerline_correct"] = uniq
            continue

        # OPTION?
        m_opt = OPTION_RE.match(line)
        if m_opt and current:
            star = bool(m_opt.group(1))
            label = m_opt.group(2).upper()
            text = m_opt.group(3).strip()

            current["options"][label] = text
            current_opt_label = label
            state = IN_OPT
            if star and label not in current["correct"]:
                current["correct"].append(label)
            continue

        # QUESTION START?
        m_q = QUESTION_RE.match(line)

        if state == OUTSIDE and m_q:
            # yeni sual
            current = {
                "q_no": m_q.group(1),
                "text": m_q.group(2).strip(),
                "options": {},
                "correct": [],
                "answer_mode": "single",
                "warnings": [],
            }
            state = IN_Q
            continue

        # Əgər artıq sualın içindəyiksə:
        if current:
            # Əgər option bitib və yeni sual başlayırsa
            if state == IN_OPT and m_q and len(current["options"]) >= 4:
                # əvvəlki sualı bağla, yenisini başlat
                close_question()
                current = {
                    "q_no": m_q.group(1),
                    "text": m_q.group(2).strip(),
                    "options": {},
                    "correct": [],
                    "answer_mode": "single",
                    "warnings": [],
                }
                state = IN_Q
                continue
            # IN_Q vəziyyətində və yeni sual gəlirsə
            elif state == IN_Q and m_q and current["options"]:
                close_question()
                current = {
                    "q_no": m_q.group(1),
                    "text": m_q.group(2).strip(),
                    "options": {},
                    "correct": [],
                    "answer_mode": "single",
                    "warnings": [],
                }
                state = IN_Q
                continue

            # Əks halda bu sətir ya sualın davamıdır, ya da variantın davamıdır
            if state == IN_OPT and current_opt_label:
                current["options"][current_opt_label] += " " + line.strip()
            else:
                current["text"] += " " + line.strip()
        else:
            # OUTSIDE ikən sual formatına düşməyən mətn → ignore
            pass

    # axırı bağla
    if current:
        close_question()

    # Validations per question
    for q in questions:
        # missing A-D
        for must in ["A", "B", "C", "D"]:
            if must not in q["options"]:
                q["warnings"].append({
                    "type": "missing_option",
                    "msg": f"{must} variantı tapılmadı."
                })

        # E optional warning
        if "E" not in q["options"]:
            q["warnings"].append({
                "type": "missing_option_e",
                "msg": "E variantı yoxdur (opsional)."
            })

        # duplicate options text warning
        norm_map = defaultdict(list)
        for lab, txt in q["options"].items():
            norm_map[_norm(txt)].append(lab)

        dup_groups = [labs for norm_txt, labs in norm_map.items() if norm_txt and len(labs) > 1]
        for labs in dup_groups:
            q["warnings"].append({
                "type": "duplicate_option_text",
                "msg": f"Təkrar variant mətni: {', '.join(labs)} eynidir."
            })

        # correct label exists?
        for c in q["correct"]:
            if c not in q["options"]:
                q["warnings"].append({
                    "type": "correct_missing",
                    "msg": f"Düz cavab kimi işarələnən {c} variantı yoxdur."
                })

    return questions




def test_question_bank(request, slug):
    exam = get_object_or_404(Exam, slug=slug)

    # yalnız test imtahanı üçün
    if exam.exam_type != "test":
        return render(request, "404.html", status=404)

    blocks = exam.question_blocks.all().order_by("order", "id")

    raw_text = ""
    parsed = []
    selected = set()

    warning_count = 0
    duplicate_count = 0

    # >>> YENİ: UI dəyərləri (Preview klikində sıfırlanmasın deyə)
    # NOTE: 0 = hamısı; None/boş = default 10 göstər
    total_q = exam.questions.count()
    exam_rq = getattr(exam, "random_question_count", None)
    rq_default = min(10, total_q) if exam_rq is None else exam_rq

    exam_dp = getattr(exam, "default_question_points", None) or 1
    dp_default = exam_dp

    # GET-də və POST-da input-ların value-ları buradan gedəcək
    rq_value = str(rq_default)
    dp_value = str(dp_default)

    def build_fp_from_parsed(q):
        return _norm(q["text"]) + "||" + "||".join([_norm(q["options"].get(x, "")) for x in "ABCDE"])

    def build_fp_from_db(eq):
        # DB-də option-lar label saxlamadığı üçün sıra ilə götürürük (A..E)
        opt_map = {}
        opts = list(eq.options.all())
        labels = list("ABCDE")
        for i, opt in enumerate(opts[:5]):
            opt_map[labels[i]] = opt.text
        return _norm(eq.text) + "||" + "||".join([_norm(opt_map.get(x, "")) for x in "ABCDE"])

    # GET
    if request.method != "POST":
        return render(request, "blog/test_question_bank.html", {
            "exam": exam,
            "blocks": blocks,
            "raw_text": raw_text,
            "parsed": parsed,
            "selected": selected,
            "warning_count": warning_count,
            "duplicate_count": duplicate_count,

            # >>> YENİ: input-ların value-ları
            "rq_value": rq_value,
            "dp_value": dp_value,
        })

    # POST
    action = request.POST.get("action", "preview")

    # >>> YENİ: Preview-də də input dəyərlərini saxla (DB-yə yazmadan!)
    rq_post = (request.POST.get("random_question_count") or "").strip()
    dp_post = (request.POST.get("default_points") or "").strip()

    if rq_post != "":
        rq_value = rq_post  # typed dəyər geri qayıtsın
    if dp_post != "":
        dp_value = dp_post  # typed dəyər geri qayıtsın

    # 1) raw_text-i formdan al (save formunda hidden textarea olmalıdır!)
    raw_text = request.POST.get("raw_text", "")

    # 2) fayl varsa onu oxu (paste varsa fallback kimi qalır)
    uploaded = request.FILES.get("upload_file")
    if uploaded:
        try:
            raw_text = extract_text_from_upload(uploaded)
        except Exception as e:
            # burada fallback: textarea-dakı raw_text qalsın
            messages.error(request, f"Fayl oxunmadı: {e}")

    # 3) preview/save üçün parse et
    if action in ("preview", "save"):
        parsed = parse_bulk_mcq(raw_text) or []

        # təhlükəsizlik: warnings açarı hər sualda olsun
        for q in parsed:
            q.setdefault("warnings", [])

        # ---- Duplicate check: import daxilində ----
        fp_first = {}
        for idx, q in enumerate(parsed, start=1):
            fp = build_fp_from_parsed(q)
            if fp in fp_first:
                q["warnings"].append({
                    "type": "duplicate_in_import",
                    "msg": f"Təkrar sual: #{idx} sualı əvvəlki #{fp_first[fp]} ilə eynidir.",
                    "ref": fp_first[fp]
                })
            else:
                fp_first[fp] = idx

        # ---- Duplicate check: DB-də artıq var? ----
        existing = ExamQuestion.objects.filter(exam=exam).prefetch_related("options")
        existing_fp = {build_fp_from_db(eq) for eq in existing}

        for idx, q in enumerate(parsed, start=1):
            fp = build_fp_from_parsed(q)
            if fp in existing_fp:
                q["warnings"].append({
                    "type": "already_in_exam",
                    "msg": f"Bu sual artıq imtahanda mövcuddur (import # {idx})."
                })

        # ---- Seçilən suallar ----
        selected_list = request.POST.getlist("selected")
        if selected_list:
            selected = set(int(x) for x in selected_list)
        else:
            selected = set(range(1, len(parsed) + 1))

        # ---- warning sayları (üst panel üçün) ----
        warning_count = sum(len(q.get("warnings", [])) for q in parsed)
        duplicate_count = sum(
            1
            for q in parsed
            for w in q.get("warnings", [])
            if w.get("type") in ("duplicate_in_import", "already_in_exam")
        )

    # 4) SAVE
    if action == "save":
        # ---- Exam settings: random_question_count + default_points(+ optional default_question_points) ----
        rq_raw = (request.POST.get("random_question_count") or "").strip()
        dp_raw = (request.POST.get("default_points") or "").strip()

        update_fields = []

        # random_question_count: 0 = hamısı, 10 = 10, 1 = 1 və s.
        if rq_raw.isdigit():
            exam.random_question_count = int(rq_raw)
            update_fields.append("random_question_count")

        # default_points: formdan gəlmirsə, exam.default_question_points varsa onu götür, yoxdursa 1
        if dp_raw.isdigit() and int(dp_raw) > 0:
            default_points = int(dp_raw)
        else:
            default_points = getattr(exam, "default_question_points", None) or 1

        # Exam-də də saxla (əgər field varsa) – köhnə məntiqi pozmur
        if hasattr(exam, "default_question_points"):
            exam.default_question_points = default_points
            update_fields.append("default_question_points")

        if update_fields:
            exam.save(update_fields=update_fields)

        # ---- blok seçimi / yeni blok ----
        block_id = request.POST.get("block_id")
        new_block_name = (request.POST.get("new_block_name") or "").strip()
        block_obj = None

        if new_block_name:
            max_order = blocks.aggregate(m=Max("order")).get("m") or 0
            block_obj = QuestionBlock.objects.create(
                exam=exam,
                name=new_block_name,
                order=max_order + 1
            )
        elif block_id:
            block_obj = QuestionBlock.objects.filter(id=block_id, exam=exam).first()

        # ---- order başlanğıcı ----
        start_order = (ExamQuestion.objects.filter(exam=exam).aggregate(m=Max("order")).get("m") or 0) + 1

        created_count = 0
        skipped_count = 0

        for idx, q in enumerate(parsed, start=1):
            if idx not in selected:
                continue

            # minimum şərt: A-D olsun
            if any(x not in q["options"] for x in ["A", "B", "C", "D"]):
                skipped_count += 1
                continue

            # per-question points (opsional input: points_1, points_2, ...)
            p_raw = (request.POST.get(f"points_{idx}") or "").strip()
            points = int(p_raw) if p_raw.isdigit() and int(p_raw) > 0 else default_points

            eq = ExamQuestion.objects.create(
                exam=exam,
                block=block_obj,
                text=q["text"],
                answer_mode=q["answer_mode"],
                order=start_order,
                points=points,
            )
            start_order += 1

            # options create (A–E varsa)
            for lab in "ABCDE":
                if lab in q["options"]:
                    ExamQuestionOption.objects.create(
                        question=eq,
                        text=q["options"][lab],
                        is_correct=(lab in q["correct"])
                    )

            created_count += 1

        messages.success(request, f"{created_count} sual əlavə olundu. ({skipped_count} sual keçildi)")
        return redirect("test_question_bank", slug=exam.slug)

    # PREVIEW və ya parse sonrası eyni səhifəni göstər
    return render(request, "blog/test_question_bank.html", {
        "exam": exam,
        "blocks": blocks,
        "raw_text": raw_text,
        "parsed": parsed,
        "selected": selected,
        "warning_count": warning_count,
        "duplicate_count": duplicate_count,

        # >>> YENİ: Preview refresh olsa da input-lar dolu qalsın
        "rq_value": rq_value,
        "dp_value": dp_value,
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
    Mövcud sualı redaktə etmək (text, blok, cavab rejimi, vaxt, variantlar və s.).
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)

    # --- DÜZƏLİŞ: Dropdown-un dolması üçün blokları çağırırıq ---
    blocks = QuestionBlock.objects.filter(exam=exam).order_by('order')
    # ------------------------------------------------------------

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            request.POST,
            request.FILES,
            instance=question,
            exam_type=exam.exam_type,
            subject_blocks=blocks  # <--- Vacib: Blokları formaya ötürürük
        )
        if form.is_valid():
            q = form.save(commit=False)
            q.exam = exam

            if exam.exam_type == "written":
                q.answer_mode = "single"

            q.save()

            if exam.exam_type == "test":
                form.save_options(q)

            if "save_and_continue" in request.POST:
                return redirect("add_exam_question", slug=exam.slug)
            
            return redirect("teacher_exam_detail", slug=exam.slug)
    else:
        form = ExamQuestionCreateForm(
            instance=question,
            exam_type=exam.exam_type,
            subject_blocks=blocks  # <--- Vacib: Blokları formaya ötürürük
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
    return render(request, "blog/student_exam_list.html", context)





def _start_or_resume_attempt(request, exam: Exam):
    """
    İstifadəçi üçün attempt yaradır və ya mövcud attempt-ə yönləndirir.
    """
    user = request.user

    # ✅ DƏYİŞİKLİK: Bitməmiş attempt-i yoxla
    current = exam.attempts.filter(
        user=user,
        status__in=["draft", "in_progress"]
    ).order_by("-started_at").first()
    
    if current:
        # Suallar düzgün generate edilib?
        desired = _effective_needed_count(exam)
        current_count = current.answers.count()
        
        # Əgər sual sayı düzgün deyilsə və heç cavab yazılmayıbsa, yenidən generate et
        if current_count != desired and not _attempt_has_any_answer(current):
            generate_random_questions_for_attempt(current, force_rebuild=True)
        
        return redirect("take_exam", slug=exam.slug, attempt_id=current.id)

    # ✅ Bitmiş cəhdləri yoxla
    finished_qs = exam.attempts.filter(
        user=user,
        status__in=["submitted", "expired"]
    ).order_by("-started_at")
    
    finished_count = finished_qs.count()
    
    # ✅ DƏYİŞİKLİK: Boş olduqda limitsiz cəhd
    max_attempts = exam.max_attempts_per_user
    
    # Əgər max_attempts təyin edilib VƏ limite çatılıbsa
    if max_attempts and finished_count >= max_attempts:
        last = finished_qs.first()
        if last:
            messages.info(request, f"Siz bu imtahana maksimum {max_attempts} dəfə cəhd edə bilərsiniz.")
            return redirect("exam_result", slug=exam.slug, attempt_id=last.id)
        return redirect("student_exam_list")

    # ✅ DƏYİŞİKLİK: Attempt number-i düzgün hesabla
    # Bütün attemptlərdən (bitmiş və bitməmiş) ən böyük nömrəni tap
    last_attempt = exam.attempts.filter(user=user).order_by('-attempt_number').first()
    
    if last_attempt:
        next_attempt_number = last_attempt.attempt_number + 1
    else:
        next_attempt_number = 1
    
    # ✅ Yeni attempt yarat
    attempt = ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )
    
    # Sualları generate et
    generate_random_questions_for_attempt(attempt)
    
    messages.success(request, f"İmtahan başladı! (Cəhd #{next_attempt_number})")
    return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)


@login_required
def start_exam(request, slug):
    """
    İmtahan başlatma view-ı
    """
    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    # İcazə yoxlaması
    can_start, reason = exam.can_user_start(request.user, code=None)
    if not can_start:
        messages.error(request, reason or "Bu imtahana başlaya bilmirsiniz.")
        return redirect("student_exam_list")

    return _start_or_resume_attempt(request, exam)


# ✅ ƏLAVƏ: Helper funksiya - attempt-də cavab var?
def _attempt_has_any_answer(attempt):
    """
    Attempt-də heç olmasa bir doldurulmuş cavab var?
    """
    # Test cavabları
    if attempt.answers.filter(selected_options__isnull=False).exists():
        return True
    
    # Yazılı cavablar
    if attempt.answers.exclude(text_answer="").exists():
        return True
    
    # Fayllar
    from .models import ExamAnswerFile
    if ExamAnswerFile.objects.filter(answer__attempt=attempt).exists():
        return True
    
    return False


def _effective_needed_count(exam):
    """
    Bu exam üçün neçə sual lazımdır?
    """
    # ✅ Əgər random_question_count təyin edilibsə, onu istifadə et
    if exam.random_question_count and exam.random_question_count > 0:
        return exam.random_question_count
    
    # ✅ Əks halda, bütün sualların sayını qaytar
    return exam.questions.count()



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






def generate_random_questions_for_attempt(attempt, *, force_rebuild: bool = False):
    """
    Yeni attempt üçün sualları random seçir və ExamAnswer yaradır.
    - default: 10 sual
    - 0: hamısı (amma random order)
    - blok varsa: bərabər pay + çatışmayanı digər suallardan doldurur
    - refresh edəndə dəyişməsin deyə ExamAnswer-da sabitlənir
    """
    exam = attempt.exam

    # Əgər artıq suallar yaradılıbsa:
    if attempt.answers.exists():
        if not force_rebuild:
            return
        # force rebuild istənirsə, amma tələbə cavab yazıbsa toxunmuruq
        if _attempt_has_any_answer(attempt):
            return
        attempt.answers.all().delete()

    total_needed = _effective_needed_count(exam)

    # bütün sualları al (DB hit az olsun)
    all_qs = list(exam.questions.all())

    if not all_qs:
        return

    # Əgər tələb olunan say hamısından çoxdursa -> hamısını götür
    if total_needed >= len(all_qs):
        selected_qs = all_qs[:]
        random.shuffle(selected_qs)  # “hamısı” olsa belə random sıra
    else:
        selected_qs = []
        blocks = list(exam.question_blocks.all())

        if blocks:
            blocks_count = len(blocks)
            base = total_needed // blocks_count
            rem = total_needed % blocks_count

            random.shuffle(blocks)

            picked_ids = set()

            # bloklardan payla
            for i, block in enumerate(blocks):
                take = base + (1 if i < rem else 0)

                block_qs = list(block.questions.all())
                random.shuffle(block_qs)

                for q in block_qs:
                    if len(selected_qs) >= total_needed:
                        break
                    if q.id in picked_ids:
                        continue
                    selected_qs.append(q)
                    picked_ids.add(q.id)
                    if len(selected_qs) >= total_needed or len(selected_qs) - len(picked_ids) >= take:
                        # yuxarıdakı “take” limitini yumşaq saxlayırıq,
                        # əsas məqsəd total_needed-ə çatmaqdır
                        pass

                # blokda sual çatmadısa, problem deyil – aşağıda fill edəcəyik

            # çatmayanı digər suallardan doldur
            if len(selected_qs) < total_needed:
                remaining = [q for q in all_qs if q.id not in picked_ids]
                random.shuffle(remaining)
                selected_qs.extend(remaining[: (total_needed - len(selected_qs))])

            # son dəfə də ümumi sıranı qarışdır (blok “izləri” qalmasın)
            random.shuffle(selected_qs)

        else:
            # blok yoxdursa — ümumi pool-dan random seç
            random.shuffle(all_qs)
            selected_qs = all_qs[:total_needed]

    # ExamAnswer-ları bulk yarat
    ExamAnswer.objects.bulk_create(
        [ExamAnswer(attempt=attempt, question=q) for q in selected_qs],
        ignore_conflicts=True
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

    # Sualları Attempt-ə bağlanmış cavablardan götürürük
    answers_qs = (
        attempt.answers
        .select_related("question")
        .prefetch_related("question__options", "selected_options", "files")
        .order_by("id")
    )

    if not answers_qs.exists():
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers
            .select_related("question")
            .prefetch_related("question__options", "selected_options","files")
            .order_by("id")
        )

    if not answers_qs.exists():
        answers_qs = attempt.answers.select_related("question").prefetch_related("question__options", "selected_options","files").order_by("id")

    questions = [a.question for a in answers_qs]
    
    # ✅ Hər cavab üçün seçilmiş option ID-lərini set olaraq saxla
    answers_by_qid = {}
    for a in answers_qs:
        answers_by_qid[a.question_id] = {
            'answer': a,
            'selected_option_ids': set(a.selected_options.values_list('id', flat=True))
        }

    # q_payload yaradırıq
    q_payload = []
    for q in questions:
        opts = []
        if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
            opts = build_shuffled_options(attempt.id, q)
        q_payload.append({"q": q, "opts": opts})

    # Server tərəfli Vaxt Hesablaması
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

        # ✅ KRİTİK: Hər sual üçün cavabı yenilə
        for q in questions:
            ans, _ = ExamAnswer.objects.get_or_create(attempt=attempt, question=q)

            if exam.exam_type == "test" and q.answer_mode in ("single", "multiple"):
                # ✅ Əvvəlcə mövcud seçimləri təmizlə
                ans.selected_options.clear()

                if q.answer_mode == "single":
                    opt_id = request.POST.get(f"q_{q.id}")
                    if opt_id:
                        opt = ExamQuestionOption.objects.filter(id=opt_id, question=q).first()
                        if opt:
                            ans.selected_options.add(opt)

                else:  # multiple
                    opt_ids = request.POST.getlist(f"q_{q.id}")
                    if opt_ids:
                        opts = list(ExamQuestionOption.objects.filter(question=q, id__in=opt_ids))
                        if opts:
                            ans.selected_options.add(*opts)

                # ✅ Test cavabları üçün text_answer-ı boşalt
                ans.text_answer = ""
                ans.has_paint = False
                if getattr(ans, "paint_image", None):
                    _clear_paint_from_answer(ans)
                
                # ✅ Auto-evaluate et
                ans.auto_evaluate()
                ans.save()

            else:  # Yazılı sual
                text = request.POST.get(f"q_{q.id}", "").strip()
                ans.text_answer = text
                ans.is_correct = False
                ans.save()

                files = request.FILES.getlist(f"file_{q.id}[]")
                if files:
                    ans.files.all().delete()
                    for f in files:
                        ExamAnswerFile.objects.create(answer=ans, file=f)
                
                # Paint hissəsi
                paint_enabled = (request.POST.get(f"paint_enabled_{q.id}") == "1")
                paint_clear = (request.POST.get(f"paint_clear_{q.id}") == "1")
                paint_data_url = (request.POST.get(f"paint_data_{q.id}") or "").strip()

                if paint_clear:
                    _clear_paint_from_answer(ans)

                if paint_enabled and paint_data_url.startswith("data:image/png;base64,"):
                    _save_paint_png_to_answer(ans, paint_data_url)
                elif not paint_enabled:
                    pass
                
                ans.save()

        # ✅ Test imtahanı üçün score-u yenilə
        if exam.exam_type == "test":
            attempt.recalculate_score()

        # ✅ Finish və ya time up
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

        # ✅ Draft olaraq saxla (autosave və ya manual save_draft)
        if action in ("autosave", "save_draft"):
            attempt.status = "draft"
            attempt.save(update_fields=["status"])
            
        if is_ajax:
            return JsonResponse({"success": True, "finished": False})
        
        # ✅ Normal POST (AJAX deyilsə) - səhifəni yenilə
        return redirect("take_exam", slug=exam.slug, attempt_id=attempt.id)

    # GET sorğusu
    context = {
        "exam": exam,
        "attempt": attempt,
        "questions": questions,
        "q_payload": q_payload,
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

