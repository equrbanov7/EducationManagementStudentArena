"""TAPŞIRIQ kitabçası idxalı: müəllim sütunundakı ad işarələrinin («QORXMAZ»,
«AYDIN-MİNAYƏ») istifadəçilərə həlli — :class:`~.task_workbook_import.Importer`-in mixin-i.

Sahibin qərarları: 2026-09-19 — tapılmayan müəllim yarım məlumatla YARADILIR, qeyri-müəyyən
olan vakant qalır. 2026-10-12 — ``--no-create-teachers`` (prod workflow həmişə ötürür):
heç bir hesab/üzvlük yaradılmır, YALNIZ bu kafedranın aktiv müəllim üzvlüklərində axtarılır;
tapılmayan / qeyri-müəyyən / başqa kafedradakı namizəd yalnız hesabata düşür.
Operator qeyri-müəyyən adı açıq göstərə bilər: ``--teacher "MURAD=istifadəçi.adı"``
(``self.teacher_map``: ad işarəsinin slug-ı → istifadəçi adı) — hesab aktiv olmalıdır.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.organizations.models import Membership, Role
from apps.workload.services.people import chair_teacher_memberships
from apps.workload.services.task_workbook_parsing import _title_az, slug_name

#: Ad işarəsi → istifadəçi həllinin nəticə kodları (hesabatda ``action``).
TEACHER_NOT_FOUND = "not_found"
TEACHER_OUTSIDE_CHAIR = "outside_chair"


class TeacherResolverMixin:
    """Tələb edir: ``self.org``, ``self.apply``, ``self.actor_user``, ``self.counters``,
    ``self.teacher_cache``, ``self.created_teachers``, ``self.ambiguous_teachers``,
    ``self.create_teachers``."""

    def _teacher_candidates(self, token: str, chair, *, org_wide: bool = True) -> list:
        """Ad (böyük hərflə, bəzən soyad inisialı ilə) → kafedra, sonra təşkilat üzrə müəllimlər."""
        parts = token.replace("I", "İ").split()
        first = slug_name(parts[0]) if parts else ""
        initial = slug_name(parts[1])[:1] if len(parts) > 1 else ""
        if not first:
            return []

        def pick(memberships):
            seen = {}
            for membership in memberships:
                user = membership.user
                if user is None or not user.is_active or user.pk in seen:
                    continue
                if slug_name(user.first_name) != first:
                    continue
                if initial and slug_name(user.last_name)[:1] != initial:
                    continue
                seen[user.pk] = user
            return list(seen.values())

        found = pick(chair_teacher_memberships(self.org, chair, include_unscoped=False))
        if found or not org_wide:
            return found
        org_wide_qs = Membership.objects.filter(
            Q(organization=self.org, is_active=True, role__is_active=True),
            role__name__in=("teacher", "assistant"),
        ).select_related("user")
        return pick(org_wide_qs)

    def resolve_teacher(self, token: str, chair) -> tuple:
        """→ (User|None, action). Eyni ad-soyadlı dublikatlar ən köhnə hesaba yığılır."""
        token = token.strip()
        cache_key = (slug_name(token), chair.pk)
        if cache_key in self.teacher_cache:
            return self.teacher_cache[cache_key]
        strict = not self.create_teachers
        mapped = getattr(self, "teacher_map", {}).get(slug_name(token))
        if mapped:
            user = get_user_model().objects.filter(username=mapped, is_active=True).first()
            result = (user, "mapped") if user is not None else (None, "mapped_user_not_found")
            self.teacher_cache[cache_key] = result
            return result
        candidates = self._teacher_candidates(token, chair, org_wide=not strict)
        by_full = {}
        for user in candidates:
            by_full.setdefault(f"{slug_name(user.first_name)}.{slug_name(user.last_name)}", []).append(user)
        result: tuple
        if len(by_full) > 1:
            # Eyni ad, fərqli soyad: keçən illərdə bu kafedranın fənlərini kim aparıb?
            preferred = self._prefer_by_history(chair, [users for users in by_full.values()])
            if preferred is not None:
                by_full = {k: v for k, v in by_full.items() if preferred in v}
        if len(by_full) == 1:
            users = self._order_duplicates(next(iter(by_full.values())))
            result = (users[0], "matched" if len(users) == 1 else "matched_duplicate_accounts")
        elif len(by_full) > 1:
            result = (None, "ambiguous:" + " / ".join(sorted(by_full)))
            self.ambiguous_teachers.append(f"{token} → {' / '.join(sorted(by_full))}")
        elif strict:
            outside = self._teacher_candidates(token, chair, org_wide=True)
            result = (None, TEACHER_OUTSIDE_CHAIR if outside else TEACHER_NOT_FOUND)
            self.counters[f"teacher_{result[1]}"] += 1
        else:
            result = (self._create_teacher(token, chair), "created")
        if (
            not strict
            and result[0] is not None
            and result[0].pk
            and not chair_teacher_memberships(self.org, chair).filter(user=result[0]).exists()
        ):
            self.counters["membership_added"] += 1
            if self.apply:
                role = Role.objects.get(organization=self.org, name="teacher")
                Membership.objects.get_or_create(
                    organization=self.org,
                    user=result[0],
                    role=role,
                    scope_unit=chair,
                    defaults={"is_active": True, "assigned_by": self.actor_user},
                )
            result = (result[0], result[1] + "+chair_membership")
        self.teacher_cache[cache_key] = result
        return result

    def _order_duplicates(self, users):
        """Dublikat hesablar: RİM rəhbəri üzvlüyü / son giriş / e-poçt olan hesab önə."""

        def rank(user):
            is_head = Membership.objects.filter(
                organization=self.org, user=user, is_active=True, role__name="ikt_rehber"
            ).exists()
            return (not is_head, user.last_login is None, not bool(user.email), user.pk)

        return sorted(users, key=rank)

    def _prefer_by_history(self, chair, groups_of_users):
        """Fərqli soyadlı namizədlərdən kafedranın fənlərini əvvəl aparanı seçir (yeganə olsa)."""
        from django.apps import apps as django_apps

        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        scores = []
        for users in groups_of_users:
            count = CourseOffering.objects.filter(
                organization=self.org, instructor__in=users, subject__chair_unit=chair
            ).count()
            scores.append((count, users[0]))
        scores.sort(key=lambda item: -item[0])
        if scores and scores[0][0] > 0 and (len(scores) == 1 or scores[1][0] == 0):
            return scores[0][1]
        return None

    def _create_teacher(self, token: str, chair):
        User = get_user_model()
        first = _title_az(token.replace("I", "İ").split()[0])
        base = slug_name(first) or "muellim"
        username, suffix = base, 2
        while User.objects.filter(username__iexact=username).exists():
            username, suffix = f"{base}{suffix}", suffix + 1
        self.counters["teacher_created"] += 1
        self.created_teachers.append(f"{first} ({username})")
        if not self.apply:
            return User(username=username, first_name=first, is_active=True)
        user = User.objects.create_user(
            username=username, email="", password=secrets.token_urlsafe(12), first_name=first
        )
        profile = getattr(user, "profile", None)
        if profile is not None:
            profile.organization = self.org
            profile.password_change_required = True
            profile.email_verified = False
            profile.save(update_fields=["organization", "password_change_required", "email_verified", "updated_at"])
        role = Role.objects.get(organization=self.org, name="teacher")
        Membership.objects.create(
            organization=self.org, user=user, role=role, scope_unit=chair, is_active=True, assigned_by=self.actor_user
        )
        return user


__all__ = ["TEACHER_NOT_FOUND", "TEACHER_OUTSIDE_CHAIR", "TeacherResolverMixin"]
