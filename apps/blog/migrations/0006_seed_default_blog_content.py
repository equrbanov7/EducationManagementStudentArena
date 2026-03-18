from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


DEMO_USERS = [
    {
        "username": "learnhub_editor",
        "email": "editor@learnhub.local",
        "first_name": "LearnHub",
        "last_name": "Editor",
    },
    {
        "username": "learnhub_coach",
        "email": "coach@learnhub.local",
        "first_name": "LearnHub",
        "last_name": "Coach",
    },
    {
        "username": "learnhub_reader",
        "email": "reader@learnhub.local",
        "first_name": "LearnHub",
        "last_name": "Reader",
    },
    {
        "username": "learnhub_feedback",
        "email": "feedback@learnhub.local",
        "first_name": "LearnHub",
        "last_name": "Feedback",
    },
]


DEMO_POSTS = [
    {
        "slug": "python-ucun-praktik-roadmap",
        "author": "learnhub_editor",
        "category_slug": "programming",
        "title": "Python üçün praktik roadmap",
        "excerpt": "Yeni başlayanlar üçün nəzəriyyə yox, layihə üzərindən gedən sadə və davamlı öyrənmə planı.",
        "content": (
            "Python öyrənərkən ilk məqsəd yalnız sintaksisi əzbərləmək olmamalıdır. "
            "Daha yaxşı yol kiçik problemləri həll edib nəticəni tez görməkdir.\n\n"
            "İlk həftədə dəyişənlər, şərtlər və dövrlər kimi əsas anlayışlara baxın. "
            "Sonra sadə kalkulyator, fayl oxuyan mini skript və kiçik data təmizləmə nümunəsi hazırlayın.\n\n"
            "Üçüncü mərhələdə Django və ya FastAPI ilə balaca bir servis qurmaq motivasiyanı ciddi artırır. "
            "Yol xəritəsinin məqsədi mükəmməl olmaq yox, ardıcıl məşq etməkdir."
        ),
        "published_at": datetime(2026, 3, 12, 9, 0, tzinfo=dt_timezone.utc),
    },
    {
        "slug": "backend-modullari-nece-qurulur",
        "author": "learnhub_coach",
        "category_slug": "programming",
        "title": "Backend modulları necə qurulur",
        "excerpt": "Böyüyən layihələrdə faylları mövzuya görə ayırmaq, sonradan texniki borcu ciddi azaldır.",
        "content": (
            "Backend layihəsində ən böyük problemlərdən biri kodun tək bir faylda yığılmasıdır. "
            "Yaxşı başlanğıc üçün view, selector, service və form məntiqini ayrı saxlamaq kifayətdir.\n\n"
            "Bu bölgü komanda daxilində kodu tapmağı asanlaşdırır, test yazmağı sürətləndirir və təkrar istifadəni artırır. "
            "Xüsusilə approval, filtering və notification kimi qaydalar ayrıca service qatında olduqda dəyişikliklər daha təhlükəsiz olur."
        ),
        "published_at": datetime(2026, 3, 10, 10, 30, tzinfo=dt_timezone.utc),
    },
    {
        "slug": "ai-saglamliq-analizinde-nece-komek-edir",
        "author": "learnhub_editor",
        "category_slug": "data-ai",
        "title": "AI sağlamlıq analizində necə kömək edir",
        "excerpt": "Süni intellekt təkcə sürət üçün yox, qərarların keyfiyyətini artırmaq üçün də istifadə olunur.",
        "content": (
            "Sağlamlıq dataları çox vaxt müxtəlif formatlarda və böyük həcmdə olur. "
            "AI alətləri bu məlumatları qruplaşdırmaq, anomaliyaları tapmaq və ilkin risk siqnalları yaratmaq üçün faydalıdır.\n\n"
            "Ən yaxşı nəticə AI sistemləri həkim qərarını əvəz edəndə yox, onu dəstəkləyəndə alınır. "
            "İnsan yoxlaması, şəffaflıq və məxfilik bu mövzuda əsas şərtlərdir."
        ),
        "published_at": datetime(2026, 3, 9, 14, 15, tzinfo=dt_timezone.utc),
    },
    {
        "slug": "effektiv-ders-plani-qurmaq",
        "author": "learnhub_coach",
        "category_slug": "study-tips",
        "title": "Effektiv dərs planı qurmaq",
        "excerpt": "Oxu planı nə qədər sadə və təkrarlana biləndirsə, onun davamlı qalma ehtimalı da o qədər yüksək olur.",
        "content": (
            "Dərs planını həddindən artıq böyük qurmaq çox vaxt ilk həftədə motivasiyanı söndürür. "
            "Bunun əvəzinə 25-40 dəqiqəlik bloklarla başlamaq daha yaxşı nəticə verir.\n\n"
            "Hər blokun sonunda kiçik qeyd yazmaq, nəyin çətin gəldiyini anlamağa kömək edir. "
            "Beləliklə plan yalnız siyahı olmur, real öyrənmə sistemi kimi işləyir."
        ),
        "published_at": datetime(2026, 3, 8, 8, 45, tzinfo=dt_timezone.utc),
    },
    {
        "slug": "kicik-biznes-ucun-dashboard-metrikalari",
        "author": "learnhub_editor",
        "category_slug": "entrepreneurship",
        "title": "Kiçik biznes üçün dashboard metrikaları",
        "excerpt": "Yalnız çox data yox, düzgün seçilmiş 4-5 əsas metrika biznes qərarlarını daha sürətli edir.",
        "content": (
            "Kiçik komandalarda bütün datanı eyni anda izləmək əvəzinə əsas göstəriciləri prioritetləşdirmək lazımdır. "
            "Satış dönüşümü, müştəri saxlama faizi, gəlir axını və əməliyyat gecikməsi ilk baxılacaq sahələrdəndir.\n\n"
            "Dashboard nə qədər aydın olsa, komanda gündəlik qərarları bir o qədər rahat verir. "
            "Çox qrafikdən çox, düzgün şərh edilən az sayda siqnal daha faydalıdır."
        ),
        "published_at": datetime(2026, 3, 6, 11, 0, tzinfo=dt_timezone.utc),
    },
    {
        "slug": "vizual-iyerxiya-dizaynda-niye-vacibdir",
        "author": "learnhub_coach",
        "category_slug": "design",
        "title": "Vizual iyerarxiya dizaynda niyə vacibdir",
        "excerpt": "İstifadəçi ilk baxışda nəyi oxumalı olduğunu başa düşmürsə, ən yaxşı məzmun belə təsirini itirir.",
        "content": (
            "Dizaynda iyerarxiya ölçü, boşluq, kontrast və ritm vasitəsilə qurulur. "
            "Başlıq, təsvir və əməliyyat düyməsi bir-biri ilə rəqabət aparmamalıdır.\n\n"
            "Yaxşı iyerarxiya istifadəçini məcbur etmədən istiqamətləndirir. "
            "Bu da həm conversion, həm də ümumi istifadə rahatlığını artırır."
        ),
        "published_at": datetime(2026, 3, 4, 16, 20, tzinfo=dt_timezone.utc),
    },
]


DEMO_COMMENTS = [
    {
        "post_slug": "ai-saglamliq-analizinde-nece-komek-edir",
        "username": "learnhub_reader",
        "rating": 5,
        "text": "Mövzu çox aydın izah olunub. Xüsusilə AI-nin qərarı əvəz etməməsi hissəsi faydalı idi.",
        "created_at": datetime(2026, 3, 9, 16, 30, tzinfo=dt_timezone.utc),
    },
    {
        "post_slug": "ai-saglamliq-analizinde-nece-komek-edir",
        "username": "learnhub_feedback",
        "rating": 4,
        "text": "Praktik nümunələr bir az da çox olsa əla olardı, amma ümumi istiqamət çox düzgündür.",
        "created_at": datetime(2026, 3, 9, 18, 10, tzinfo=dt_timezone.utc),
    },
    {
        "post_slug": "effektiv-ders-plani-qurmaq",
        "username": "learnhub_reader",
        "rating": 5,
        "text": "Qısa bloklarla plan qurmaq məsləhəti həqiqətən işə yarayır. Sadə və praktik yazıdır.",
        "created_at": datetime(2026, 3, 8, 12, 5, tzinfo=dt_timezone.utc),
    },
    {
        "post_slug": "kicik-biznes-ucun-dashboard-metrikalari",
        "username": "learnhub_feedback",
        "rating": 4,
        "text": "Ən faydalı tərəfi metrikaların sayını az tutmağın vurğulanması oldu. Fokus itmir.",
        "created_at": datetime(2026, 3, 6, 13, 0, tzinfo=dt_timezone.utc),
    },
    {
        "post_slug": "vizual-iyerxiya-dizaynda-niye-vacibdir",
        "username": "learnhub_reader",
        "rating": 5,
        "text": "UI tərəfdə işləyənlər üçün çox yerində feedback-dir. Kontrast və boşluq hissəsi xüsusilə yaxşıdır.",
        "created_at": datetime(2026, 3, 4, 18, 40, tzinfo=dt_timezone.utc),
    },
]


def _get_user_model(apps):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    return apps.get_model(app_label, model_name)


def seed_default_blog_content(apps, schema_editor):
    User = _get_user_model(apps)
    UserProfile = apps.get_model("accounts", "UserProfile")
    Category = apps.get_model("blog", "Category")
    Post = apps.get_model("blog", "Post")
    Comment = apps.get_model("blog", "Comment")

    users = {}
    for user_data in DEMO_USERS:
        user, _ = User.objects.get_or_create(
            username=user_data["username"],
            defaults={
                "email": user_data["email"],
                "first_name": user_data["first_name"],
                "last_name": user_data["last_name"],
                "is_active": True,
                "password": make_password("LearnHubDemo123!"),
            },
        )
        UserProfile.objects.get_or_create(user_id=user.pk)
        users[user.username] = user

    categories = {category.slug: category for category in Category.objects.filter(slug__in=[p["category_slug"] for p in DEMO_POSTS])}

    posts = {}
    for post_data in DEMO_POSTS:
        author = users.get(post_data["author"])
        category = categories.get(post_data["category_slug"])
        if not author or not category:
            continue

        defaults = {
            "author_id": author.pk,
            "category_id": category.pk,
            "title": post_data["title"],
            "excerpt": post_data["excerpt"],
            "content": post_data["content"],
            "image_url": None,
            "is_published": True,
            "requires_approval": False,
            "approval_status": "approved",
            "approval_feedback": "",
            "approved_by_id": None,
            "approved_at": post_data["published_at"] + timedelta(minutes=5),
            "approval_requested_at": None,
        }
        post, created = Post.objects.get_or_create(slug=post_data["slug"], defaults=defaults)

        if not created:
            changed_fields = []
            for field_name, value in defaults.items():
                if getattr(post, field_name) != value:
                    setattr(post, field_name, value)
                    changed_fields.append(field_name)
            if changed_fields:
                post.save(update_fields=changed_fields)

        Post.objects.filter(pk=post.pk).update(
            created_at=post_data["published_at"],
            updated_at=post_data["published_at"],
        )
        posts[post.slug] = post

    for comment_data in DEMO_COMMENTS:
        post = posts.get(comment_data["post_slug"])
        user = users.get(comment_data["username"])
        if not post or not user:
            continue

        comment, _ = Comment.objects.get_or_create(
            post_id=post.pk,
            user_id=user.pk,
            text=comment_data["text"],
            defaults={"rating": comment_data["rating"]},
        )
        updates = {}
        if comment.rating != comment_data["rating"]:
            updates["rating"] = comment_data["rating"]
        if updates:
            Comment.objects.filter(pk=comment.pk).update(**updates)
        Comment.objects.filter(pk=comment.pk).update(created_at=comment_data["created_at"])


def unseed_default_blog_content(apps, schema_editor):
    User = _get_user_model(apps)
    UserProfile = apps.get_model("accounts", "UserProfile")
    Post = apps.get_model("blog", "Post")
    Comment = apps.get_model("blog", "Comment")

    demo_post_slugs = [post["slug"] for post in DEMO_POSTS]
    demo_usernames = [user["username"] for user in DEMO_USERS]

    Comment.objects.filter(post__slug__in=demo_post_slugs).delete()
    Post.objects.filter(slug__in=demo_post_slugs).delete()
    UserProfile.objects.filter(user__username__in=demo_usernames).delete()
    User.objects.filter(username__in=demo_usernames).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0009_emailotp"),
        ("blog", "0005_category_hierarchy_and_defaults"),
    ]

    operations = [
        migrations.RunPython(seed_default_blog_content, unseed_default_blog_content),
    ]
