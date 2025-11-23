from django.shortcuts import render,redirect
from django.http import HttpResponse
from django.http import Http404
from django.contrib import messages # Mesaj göstərmək üçün
from .forms import SubscriptionForm








# Create your views here.

# def home(request):
#     return HttpResponse("Welcome to the Home Page")

posts = [
    {
        "id": 1,
        "title": "JavaScript öyrənməyə necə başlamalı?",
        "excerpt": "Proqramlaşdırma dünyasına yeni başlayanlar üçün JavaScript ən ideal dillərdən biridir. Bu məqalədə yol xəritəsini təqdim edirik.",
        "category": "Proqramlaşdırma",
        "date": "23 Noyabr 2024",
        "image": "https://picsum.photos/id/1/600/400",  # Nümunə şəkil
    },
    {
        "id": 2,
        "title": "Süni İntellektin gələcəyi",
        "excerpt": "AI texnologiyaları sürətlə inkişaf edir. Bəs yaxın 10 ildə bizi nələr gözləyir? Ekspert rəyləri və proqnozlar.",
        "category": "Süni İntellekt",
        "date": "20 Noyabr 2024",
        "image": "https://picsum.photos/id/20/600/400",
    },
    {
        "id": 3,
        "title": "Minimalist Dizayn Prinsipləri",
        "excerpt": "Daha az, daha çoxdur. Veb dizaynda minimalizmin istifadəçi təcrübəsinə təsiri və tətbiq üsulları.",
        "category": "Dizayn",
        "date": "18 Noyabr 2024",
        "image": "https://picsum.photos/id/3/600/400",
    },
    {
        "id": 4,
        "title": "Uzaqdan işləməyin üstünlükləri",
        "excerpt": "Remote iş rejimi həyatımızı necə dəyişir? Məhsuldarlığı artırmaq üçün tövsiyələr.",
        "category": "Karyera",
        "date": "15 Noyabr 2024",
        "image": "https://picsum.photos/id/4/600/400",
    },
    {
        "id": 5,
        "title": "CSS Grid və Flexbox fərqləri",
        "excerpt": "Müasir CSS layout sistemləri arasındakı əsas fərqlər və hansını nə vaxt istifadə etməli olduğunuzu öyrənin.",
        "category": "Proqramlaşdırma",
        "date": "12 Noyabr 2024",
        "image": "https://picsum.photos/id/6/600/400",
    },
    {
        "id": 6,
        "title": "Sağlam həyat tərzi üçün 5 vərdiş",
        "excerpt": "Kompüter arxasında çox vaxt keçirənlər üçün sağlamlığı qorumağın qızıl qaydaları.",
        "category": "Həyat Tərzi",
        "date": "10 Noyabr 2024",
        "image": "https://picsum.photos/id/9/600/400",
    },
]

def home(request):

    return render(request, 'blog/home.html',{'posts':posts})

def about(request):
    # return HttpResponse("About Us Page")
    return render(request, 'blog/about.html')

def technology(request):
    # return HttpResponse("Technology Category Page")
    return render(request, 'blog/technology.html',{'posts':posts})

def contact(request):
    return HttpResponse("Contact Us Page")

def post_detail(request, post_id):
    post = next((post for post in posts if post["id"] == post_id), None)
    if post is None:
        raise Http404("Post tapılmadı")

    return render(request, "blog/postDetail.html", {"post": post})


def subscribe_page(request):
    if request.method == 'POST':
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            
            # --- BURADA EMAİLİ BAZAYA YAZMAQ KODU OLACAQ ---
            # Məsələn:
            # Subscriber.objects.create(email=email)
            # Və ya Mailchimp API-a göndərmək.
            
            # Uğurlu mesajı göstər
            messages.success(request, f'{email} ünvanı uğurla abunə oldu! Təşəkkürlər.')
            return redirect("subscribe") # Formu təmizləmək üçün yenidən yükləyirik
        else:
            messages.error(request, 'Zəhmət olmasa düzgün email ünvanı daxil edin.')
    else:
        form = SubscriptionForm()

    return render(request, "blog/subscribe.html", {'form': form})


#example post detail request http://

def create_post(request):
    return HttpResponse("Create a New Post Page")

def edit_post(request, post_id):
    return HttpResponse(f"Edit Post ID: {post_id}")

def delete_post(request, post_id):
    return HttpResponse(f"Delete Post ID: {post_id}")

def list_posts(request):
    return HttpResponse("List of All Posts")

def search_posts(request):
    return HttpResponse("Search Posts Page")
