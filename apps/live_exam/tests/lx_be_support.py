"""LX-BE test köməkçiləri — təşkilat, host müəllim, imtahan, sessiya, oyunçular."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamQuestion, ExamQuestionOption
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.constants import PLAYER_GET_READY_SECONDS, PLAYER_QUESTION_INTRO_SECONDS
from apps.live_exam.models import LivePlayer, LiveSession
from apps.organizations.models import Membership, Organization, Role
from core import rate_limit as rate_limit_module
from core.constants import OrganizationType, RoleScopeType

PASSWORD = "LxBePass123!"
ORIGIN = (b"origin", b"http://testserver")
IN_MEMORY_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def reset_rate_limits() -> None:
    rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()


def make_host(slug: str):
    user = get_user_model().objects.create_user(f"{slug}_host", f"{slug}@example.com", PASSWORD)
    user.profile.role = ProfileRole.TEACHER
    user.profile.save(update_fields=["role", "updated_at"])
    org = Organization.objects.create(
        name=f"{slug} Org",
        slug=f"{slug}-org",
        org_type=OrganizationType.SCHOOL,
        owner=user,
        status="active",
        is_active=True,
    )
    user.profile.organization = org
    user.profile.organization_type = org.org_type
    user.profile.save(update_fields=["organization", "organization_type", "updated_at"])
    role, _ = Role.objects.update_or_create(
        organization=org,
        name="instructor",
        defaults={
            "display_name": "Instructor",
            "level": 50,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["exam.host", "exam.manage"],
            "is_system": False,
            "is_active": True,
        },
    )
    Membership.objects.create(user=user, organization=org, role=role, is_active=True, is_primary=True)
    return user, org


def grant_host_permission(client, user, org) -> None:
    """Mövcud istifadəçiyə ``exam.host`` rolu + aktiv təşkilat (host RBAC testləri üçün)."""
    role, _ = Role.objects.update_or_create(
        organization=org,
        name="instructor",
        defaults={
            "display_name": "Instructor",
            "level": 50,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["exam.host", "exam.manage"],
            "is_system": False,
            "is_active": True,
        },
    )
    Membership.objects.update_or_create(
        user=user, organization=org, defaults={"role": role, "is_active": True, "is_primary": True}
    )
    session = client.session
    session["active_organization"] = org.slug
    session.save()


def host_client(user, org) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def make_exam(user, org, title: str = "LX-BE exam") -> Exam:
    return Exam.objects.create(title=title, author=user, organization=org, is_active=True)


def add_question(exam, text, options, *, order=1, points=1000, answer_mode="single", correct_answer=""):
    """``options`` — ``[(mətn, düzgün?), ...]`` (boş siyahı → variantsız sual)."""
    question = ExamQuestion.objects.create(
        exam=exam, text=text, order=order, points=points, answer_mode=answer_mode, correct_answer=correct_answer
    )
    created = [
        ExamQuestionOption.objects.create(question=question, text=option_text, is_correct=correct)
        for option_text, correct in options
    ]
    return question, created


def make_session(exam, host, **fields) -> LiveSession:
    session = LiveSession.objects.create(exam=exam, host_user=host)
    for key, value in fields.items():
        setattr(session, key, value)
    if fields:
        session.save(update_fields=list(fields))
    return session


def open_question(session, question, *, index=0, answer_window_seconds=20, opened_seconds_ago=1.0):
    """Sualı «cavab pəncərəsi açıqdır» vəziyyətinə gətirir (host nəşri olmadan)."""
    now = timezone.now()
    answer_starts_at = now - timedelta(seconds=opened_seconds_ago)
    started_at = answer_starts_at - timedelta(
        seconds=(PLAYER_GET_READY_SECONDS if index == 0 else 0) + PLAYER_QUESTION_INTRO_SECONDS
    )
    session.state = LiveSession.STATE_QUESTION
    session.current_index = index
    session.current_question_id = question.id
    session.question_started_at = started_at
    session.question_ends_at = answer_starts_at + timedelta(seconds=answer_window_seconds)
    session.save(
        update_fields=["state", "current_index", "current_question_id", "question_started_at", "question_ends_at"]
    )
    return answer_starts_at


def make_players(session, count: int, prefix: str = "P"):
    return [
        LivePlayer.objects.create(
            session=session,
            nickname=f"{prefix}{index:03d}",
            avatar_key="avatar_1",
            client_id=f"{prefix}-client-{index}",
        )
        for index in range(count)
    ]


def player_cookie_header(session, player):
    token = build_player_token(pin=session.pin, player_id=player.id, client_id=player.client_id)
    return (b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode())


def player_client(session, player) -> Client:
    client = Client()
    client.cookies["live_client_id"] = player.client_id
    client.cookies[PLAYER_COOKIE_NAME] = build_player_token(
        pin=session.pin, player_id=player.id, client_id=player.client_id
    )
    return client
