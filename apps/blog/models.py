# blog/models.py
import itertools

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import slugify

from .taxonomy import get_category_placeholder_static_path, get_localized_category_name

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    sort_order = models.PositiveIntegerField(default=0)
    show_in_navbar = models.BooleanField(default=False, db_index=True)
    is_default = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Kateqoriya"
        verbose_name_plural = "Kateqoriyalar"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def localized_name(self):
        return get_localized_category_name(self.slug, self.name) if self.is_default else self.name

    @property
    def full_name(self):
        names = [self.name]
        current = self.parent
        visited_ids = {self.pk}

        while current and current.pk not in visited_ids:
            names.append(current.name)
            visited_ids.add(current.pk)
            current = current.parent

        return " / ".join(reversed(names))

    @property
    def localized_full_name(self):
        names = [self.localized_name]
        current = self.parent
        visited_ids = {self.pk}

        while current and current.pk not in visited_ids:
            names.append(current.localized_name)
            visited_ids.add(current.pk)
            current = current.parent

        return " / ".join(reversed(names))

    def get_root(self):
        current = self
        visited_ids = {self.pk}

        while current.parent and current.parent.pk not in visited_ids:
            current = current.parent
            visited_ids.add(current.pk)

        return current

    def get_ancestors(self, include_self=False):
        ancestors = [self] if include_self else []
        current = self.parent
        visited_ids = {self.pk}

        while current and current.pk not in visited_ids:
            ancestors.append(current)
            visited_ids.add(current.pk)
            current = current.parent

        return list(reversed(ancestors))

    def get_descendant_ids(self, include_self=True):
        category_rows = Category.objects.values_list("id", "parent_id")
        children_by_parent = {}
        for category_id, parent_id in category_rows:
            children_by_parent.setdefault(parent_id, []).append(category_id)

        descendant_ids = [self.pk] if include_self else []
        pending_ids = list(children_by_parent.get(self.pk, []))

        while pending_ids:
            current_id = pending_ids.pop()
            descendant_ids.append(current_id)
            pending_ids.extend(children_by_parent.get(current_id, []))

        return descendant_ids

    def clean(self):
        super().clean()

        if self.parent_id and self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "Kateqoriya özü-özünün valideyni ola bilməz."})

        if self.parent_id and self.pk and self.pk in self.parent.get_descendant_ids(include_self=True):
            raise ValidationError({"parent": "Kateqoriya öz övladlarından birinin altına köçürülə bilməz."})

    def save(self, *args, **kwargs):
        # Slug boşdursa və ya dəyişdirilibsə yenilə
        if not self.slug:
            self.slug = slugify(self.name)

            # Əgər bu slug artıq varsa, sonuna rəqəm artır (nadir halda)
            original_slug = self.slug
            for x in itertools.count(1):
                if not Category.objects.filter(slug=self.slug).exists():
                    break
                self.slug = "%s-%d" % (original_slug, x)

        self.full_clean()
        super().save(*args, **kwargs)


# ---- Post Model ----


class Post(models.Model):
    class ApprovalStatus(models.TextChoices):
        APPROVED = "approved", "Approved"
        PENDING = "pending", "Pending approval"
        NEEDS_CHANGES = "needs_changes", "Needs changes"

    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    # Burada related_name="posts" qalsa yaxşıdır, kateqoriyadan postları çağırmaq üçün
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,  # Kateqoriya silinsə, məqalə silinməsin, kategoriyasız qalsın
        null=True,
        blank=True,
        related_name="posts",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=220, unique=True, blank=True
    )  # Blank=True qoyduq ki, admin paneldə məcburi istəməsin
    excerpt = models.TextField(blank=True)
    content = models.TextField()

    image_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    requires_approval = models.BooleanField(default=False, db_index=True)
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        db_index=True,
    )
    approval_feedback = models.TextField(blank=True, default="")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_blog_posts",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_requested_at = models.DateTimeField(null=True, blank=True)
    image = models.ImageField(upload_to="post_images/", blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # 1. Slug yarat (əgər yoxdursa)
        if not self.slug:
            self.slug = slugify(self.title)

        # 2. Unikallığı yoxla (Eyni adlı məqalə varsa xəta verməsin, sonuna rəqəm atsın)
        # Məsələn: "python-dersleri" varsa, "python-dersleri-1" olsun.
        original_slug = self.slug
        for x in itertools.count(1):
            if not Post.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                break
            self.slug = "%s-%d" % (original_slug, x)

        if not self.requires_approval and self.approval_status != self.ApprovalStatus.APPROVED:
            self.approval_status = self.ApprovalStatus.APPROVED

        if self.approval_status == self.ApprovalStatus.PENDING and not self.approval_requested_at:
            self.approval_requested_at = timezone.now()

        if self.approval_status != self.ApprovalStatus.APPROVED:
            self.is_published = False
            self.approved_by = None
            self.approved_at = None

        super().save(*args, **kwargs)

    @property
    def average_rating(self):
        # Comments modelin varsa bu işləyəcək
        agg = self.comments.aggregate(models.Avg("rating"))
        return agg["rating__avg"] or 0

    @property
    def get_image(self):
        """
        Bu metod yoxlayır:
        1. Fayl yüklənib? -> Faylın yolunu qaytar.
        2. URL var? -> URL-i qaytar.
        3. Heç biri yoxdur? -> Default şəkli qaytar.
        """
        if self.image:
            return self.image.url
        elif self.image_url:
            return self.image_url
        else:
            category_slug = None
            if self.category_id and self.category:
                category_slug = self.category.get_root().slug

            return static(get_category_placeholder_static_path(category_slug))

    @property
    def is_pending_approval(self):
        return self.requires_approval and self.approval_status == self.ApprovalStatus.PENDING

    @property
    def needs_approval_changes(self):
        return self.requires_approval and self.approval_status == self.ApprovalStatus.NEEDS_CHANGES

    @property
    def latest_feedback_text(self):
        current_feedback = (self.approval_feedback or "").strip()
        if current_feedback:
            return current_feedback

        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("approval_logs")
        if prefetched is not None:
            for log in prefetched:
                feedback_text = (getattr(log, "feedback", "") or "").strip()
                if feedback_text:
                    return feedback_text
            return ""

        latest_log = self.approval_logs.exclude(feedback__isnull=True).exclude(feedback__exact="").first()
        if latest_log:
            return (latest_log.feedback or "").strip()
        return ""


class PostApprovalLog(models.Model):
    class Action(models.TextChoices):
        APPROVED = "approved", "Approved"
        NEEDS_CHANGES = "needs_changes", "Needs changes"
        FEEDBACK = "feedback", "Feedback"

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="approval_logs",
    )
    reviewer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="post_approval_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    feedback = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.post_id}:{self.action}"


# ---- Models for Comment functionality ----


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    text = models.TextField()
    rating = models.PositiveSmallIntegerField(
        default=5,
        choices=[(i, f"{i} ulduz") for i in range(1, 6)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        # Diqqət: burada artıq unique_together və ya constraint YOXDUR,
        # yəni eyni user eyni post üçün bir neçə şərh yaza bilər.

    def __str__(self):
        return f"{self.user.username} → {self.post.title} ({self.rating})"


# ---- Models for Subscription functionality ----


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    conf_token = models.CharField(max_length=64, blank=True, null=True)  # Təsdiq linki üçün token
    is_active = models.BooleanField(default=False)  # Təsdiq olunmayıbsa passivdir
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


# ---- Models for Question functionality ----


class Question(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="questions", verbose_name="Müəllif")
    question_text = models.TextField("Sual")
    answer_text = models.TextField("Cavab", blank=True, null=True)

    # Hamı görə bilsin?
    visible_to_all = models.BooleanField("Hamı görə bilər", default=False)

    # Yalnız seçilmiş user-lər görə bilsin deyirsə:
    visible_users = models.ManyToManyField(
        User,
        related_name="questions_can_see",
        blank=True,
        verbose_name="Görə bilən istifadəçilər",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sual"
        verbose_name_plural = "Suallar"

    def __str__(self):
        return self.question_text[:50]

    def can_user_see(self, user):
        """
        Bu funksiya ilə şablonda və view-lərdə yoxlaya bilərik:
        bu user bu sualı görməlidirmi, yoxsa yox.
        """
        if self.visible_to_all:
            return True
        if not user.is_authenticated:
            return False
        if user == self.author:
            return True
        return self.visible_users.filter(id=user.id).exists()
