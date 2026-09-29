"""LX-SEC (Audit 2026-09-28 canlı imtahan pentest) — testlər üçün ortaq fabriklər.

Pytest bu modulu toplamır (``test_*.py`` deyil); ``test_lx_sec_*.py`` faylları
buradan istifadəçi / təşkilat / imtahan / oyunçu fiksturlarını qurur.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import LIVE_CLIENT_ID_COOKIE_NAME, PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.models import LivePlayer, LiveSession
from apps.organizations.models import Membership, Organization, Role
from core import rate_limit as rate_limit_module
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()
PASSWORD = "StrongPass123!"


def reset_rate_limits() -> None:
    """Test ayarlarında DummyCache var — limitlər proses-lokal fallback keşdədir."""
    rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()


def make_org(name: str, owner) -> Organization:
    return Organization.objects.create(
        name=name,
        org_type=OrganizationType.SCHOOL,
        owner=owner,
        status="active",
        is_active=True,
    )


def add_member(user, org, *, role_name: str, level: int, permissions=()) -> Membership:
    role, _created = Role.objects.update_or_create(
        organization=org,
        name=role_name,
        defaults={
            "display_name": role_name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": list(permissions),
            "is_system": False,
            "is_active": True,
        },
    )
    return Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": role, "is_active": True, "is_primary": True},
    )[0]


def make_user(username: str, org, *, profile_role: str, role_name: str, level: int, permissions=()):
    user = User.objects.create_user(username, f"{username}@example.com", PASSWORD)
    user.profile.role = profile_role
    user.profile.organization = org
    user.profile.organization_type = org.org_type
    user.profile.save(update_fields=["role", "organization", "organization_type", "updated_at"])
    add_member(user, org, role_name=role_name, level=level, permissions=permissions)
    return user


def make_teacher(username: str, org, *, permissions=("exam.host", "exam.manage")):
    return make_user(
        username, org, profile_role=ProfileRole.TEACHER, role_name="professor", level=60, permissions=permissions
    )


def make_student(username: str, org):
    return make_user(username, org, profile_role=ProfileRole.STUDENT, role_name=ProfileRole.STUDENT, level=10)


def login_client(user, org=None, **client_kwargs) -> Client:
    client = Client(**client_kwargs)
    client.force_login(user)
    if org is not None:
        session = client.session
        session["active_organization"] = org.slug
        session.save()
    return client


def make_exam(author, org, slug: str, *, questions: int = 1) -> Exam:
    exam = Exam.objects.create(title=f"LX-SEC {slug}", slug=slug, author=author, organization=org, is_active=True)
    for index in range(questions):
        question = ExamQuestion.objects.create(exam=exam, text=f"Sual {index + 1}?", order=index + 1)
        ExamQuestionOption.objects.create(question=question, text="Düz", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="Səhv", is_correct=False)
    return exam


def make_session(exam, host, **fields) -> LiveSession:
    return LiveSession.objects.create(exam=exam, host_user=host, **fields)


def player_client(session, nickname: str, client_id: str, **client_kwargs):
    """Bazada oyunçu yaradır və onun cookie-ləri ilə ``Client`` qaytarır."""
    player = LivePlayer.objects.create(session=session, nickname=nickname, avatar_key="avatar_1", client_id=client_id)
    client = Client(**client_kwargs)
    client.cookies[LIVE_CLIENT_ID_COOKIE_NAME] = client_id
    client.cookies[PLAYER_COOKIE_NAME] = build_player_token(pin=session.pin, player_id=player.id, client_id=client_id)
    return player, client
