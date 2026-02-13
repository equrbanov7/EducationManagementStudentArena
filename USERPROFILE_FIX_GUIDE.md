# UserProfile Django Fix - Complete Implementation Guide

## Problem Statement

The application was experiencing two critical errors:
1. `User.profile.RelatedObjectDoesNotExist` - Some users didn't have Profile objects
2. `TypeError: 'User' object is not subscriptable` - Dictionary-style access in templates
3. Broken navbar profile links

## Root Causes

1. **Missing Profile Auto-Creation**: Profile signals were in models.py but not properly triggered for all users
2. **Unsafe Template Access**: Templates used `user.profile.field` without checking if profile exists
3. **Wrong URL Pattern**: Navbar used old blog-style URL `user_profile` with username parameter

## Solution Implementation

### 1. Signals Architecture (`apps/accounts/signals.py`)

```python
"""
Signals for accounts app.
Handles automatic profile creation and group setup.
"""

from django.apps import apps
from django.conf import settings
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

DEFAULT_GROUPS = ["student", "teacher", "assistant_teacher", "moderator"]


@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    """Create default groups after migration."""
    if sender.name != "apps.accounts":
        return

    Group = apps.get_model("auth", "Group")
    for name in DEFAULT_GROUPS:
        Group.objects.get_or_create(name=name)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a UserProfile when a new User is created."""
    if created:
        from apps.accounts.models import UserProfile
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """
    Automatically save the UserProfile when the User is saved.
    Ensures profile exists even if it wasn't created initially.
    """
    from apps.accounts.models import UserProfile
    
    if hasattr(instance, "profile"):
        instance.profile.save()
    else:
        # Profile doesn't exist, create it now
        UserProfile.objects.get_or_create(user=instance)
```

**Key Features:**
- Uses `get_or_create` instead of `create` for safety
- Double-check in `save_user_profile` ensures profile always exists
- Proper imports inside signal to avoid circular imports

### 2. Model Structure (`apps/accounts/models.py`)

```python
"""
User profile models for EMS Arena.
Extends Django's User model with additional profile information.
"""

from django.conf import settings
from django.db import models
from core.constants import OrganizationType


class UserProfile(models.Model):
    """Extended user profile with organization type and additional information."""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="profile"
    )
    
    organization_type = models.CharField(
        max_length=20,
        choices=OrganizationType.CHOICES,
        default=OrganizationType.INDIVIDUAL,
        verbose_name="Təşkilat tipi"
    )
    
    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Avatar"
    )
    
    phone = models.CharField(max_length=20, blank=True, verbose_name="Telefon")
    bio = models.TextField(blank=True, verbose_name="Haqqında")
    supervisor_code = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=100, blank=True, verbose_name="Yer")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "İstifadəçi profili"
        verbose_name_plural = "İstifadəçi profilləri"
        ordering = ["-created_at"]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_organization_type_display()}"
```

**Note:** Signals removed from models.py to avoid conflicts. All signals in signals.py.

### 3. App Configuration (`apps/accounts/apps.py`)

```python
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        # Import models to register UserProfile signals
        from apps.accounts import models  # noqa
        from apps.accounts import signals  # noqa
```

**Critical:** Both imports are needed:
- `models` import ensures model is registered
- `signals` import triggers signal registration

### 4. View with Safety (`apps/accounts/views.py`)

```python
@login_required
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    """
    from apps.accounts.models import UserProfile

    # Ensure profile exists (get_or_create for safety)
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        # Update user info
        request.user.first_name = request.POST.get("first_name", "")
        request.user.last_name = request.POST.get("last_name", "")
        request.user.email = request.POST.get("email", "")
        request.user.save()

        # Update profile
        profile.phone = request.POST.get("phone", "")
        profile.bio = request.POST.get("bio", "")
        profile.location = request.POST.get("location", "")

        if "avatar" in request.FILES:
            profile.avatar = request.FILES["avatar"]

        if getattr(request.user, "is_admin_level", False):
            profile.supervisor_code = request.POST.get("supervisor_code", "")

        profile.save()
        messages.success(request, "Profil uğurla yeniləndi!")
        return redirect("accounts:profile")

    context = {
        "profile": profile,
        "user_roles": request.user.get_all_roles() if hasattr(request.user, "get_all_roles") else [],
    }

    return render(request, "accounts/profile.html", context)
```

**Key Changes:**
- `get_or_create` ensures profile always exists
- Pass `profile` directly in context (not as `user.profile`)
- Removed conditional checks since profile is guaranteed to exist

### 5. Safe Template Access (`apps/accounts/templates/accounts/profile.html`)

**BEFORE (Unsafe):**
```django
{% if user.profile.avatar %}
    <img src="{{ user.profile.avatar.url }}" alt="Avatar">
{% endif %}

<input value="{{ user.profile.phone }}">
<input value="{{ user.profile.location }}">
<div>{{ user.profile.get_organization_type_display }}</div>
```

**AFTER (Safe):**
```django
{% if profile.avatar %}
    <img src="{{ profile.avatar.url }}" alt="Avatar">
{% endif %}

<input value="{{ profile.phone|default:'' }}">
<input value="{{ profile.location|default:'' }}">
<div>{{ profile.get_organization_type_display|default:'Fərdi' }}</div>
```

**Key Changes:**
- Use `profile` directly (from context)
- Add `|default:''` filter for optional fields
- Add `|default:'Fərdi'` for display fields

### 6. Fixed Navbar Links (`templates/partials/_navbar.html`)

**BEFORE (Broken):**
```django
<a href="{% url 'user_profile' request.user.username %}">Profilim</a>
```

**AFTER (Working):**
```django
<a href="{% url 'accounts:profile' %}">Profilim</a>
```

**Changes:**
- Use namespace `accounts:profile` instead of `user_profile`
- No username parameter needed (view uses `request.user`)

## Testing the Solution

### Manual Test Steps

1. **Test Profile Auto-Creation:**
```python
from django.contrib.auth import get_user_model
from apps.accounts.models import UserProfile

User = get_user_model()

# Create new user
user = User.objects.create_user(
    username='testuser',
    email='test@example.com',
    password='testpass123'
)

# Check profile exists
assert hasattr(user, 'profile')
assert isinstance(user.profile, UserProfile)
print("✅ Profile auto-created")
```

2. **Test Profile Page Access:**
- Log in as any user
- Click "Profilim" in navbar
- Page should load without errors
- All fields should display (even if empty)

3. **Test Profile Updates:**
- Fill in profile fields
- Upload avatar
- Click "Yadda saxla"
- Changes should save successfully

### Expected Behavior

✅ **Every user automatically gets a Profile**
✅ **No `RelatedObjectDoesNotExist` errors**
✅ **No `TypeError` about subscriptable objects**
✅ **Navbar profile link works**
✅ **Profile page renders without crashes**
✅ **Empty fields display gracefully**

## Production Checklist

- [x] Signals in separate file (`signals.py`)
- [x] Signals imported in `apps.py ready()`
- [x] Model clean without signal decorators
- [x] View uses `get_or_create`
- [x] Template uses safe access with `|default`
- [x] Navbar uses correct URL pattern
- [x] No dictionary-style access (`user["profile"]`)
- [x] Django check passes (0 errors)

## Migration Notes

If upgrading existing installation:

```bash
# 1. Migrate models (if not already done)
python manage.py migrate

# 2. Create profiles for existing users
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from apps.accounts.models import UserProfile

User = get_user_model()

# Create profiles for users without them
for user in User.objects.all():
    UserProfile.objects.get_or_create(user=user)
    print(f"✅ Profile ensured for {user.username}")
```

## Common Issues and Solutions

### Issue 1: "Profile doesn't exist" error persists
**Solution:** Check that signals are imported in `apps.py ready()` method.

### Issue 2: Profile not created for new users
**Solution:** Verify `AUTH_USER_MODEL` is correct in settings and signals use it.

### Issue 3: Template still crashes
**Solution:** Ensure template uses `profile` from context, not `user.profile`, and add `|default` filters.

### Issue 4: Navbar link returns 404
**Solution:** Check URL namespace is `accounts:profile` and URL is registered in `apps/accounts/urls.py`.

## Summary

This implementation provides:
- **Robustness**: Multiple safety checks ensure profile always exists
- **Clean Architecture**: Signals in separate file, proper separation of concerns
- **Production-Ready**: Handles edge cases, graceful degradation
- **CI-Friendly**: No warnings, passes all checks

The solution follows Django best practices and is maintainable for long-term use.
