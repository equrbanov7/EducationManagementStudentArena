"""``create_quiz_test_accounts_20261120`` — quiz üçün 30 MÜVƏQQƏTİ test tələbə hesabı (sahib 2026-11-20).

Sahib: ``testuser1`` … ``testuser30``, hamısının parolu ``12345678`` (sahibin açıq istəyi ilə koddadır), hamısı yeni
``TestQrup`` qrupunda (``qku``); dərhal girib quiz yazsınlar. Sabitlər: ``apps/accounts/quiz_test_accounts.py``.

YAZILANLAR (apply):

* ``User`` (ad «Test», soyad «User N», e-poçt ``testuserN@quiz-test-20261120.invalid`` — real ünvan deyil, məktub
  getmir; FİN / telefon / şəxsi data YOXDUR) + ``UserProfile`` (tələbə, ``access_state=active``,
  ``password_change_required=False``, ``email_verified=True`` — ilk-giriş / OTP qapısı yoxdur; profil tamamlama
  qapısı bu hesabları ``profile_completion.is_exempt_user`` ilə buraxır) + təşkilatın ``student`` üzvlüyü.
* ``TestQrup`` — kök səviyyəli reyestr qrupu (``OrgUnit`` GROUP, ``settings[GROUP_MARKER_KEY]`` işarəsi ilə).
* Arxiv (``is_active=False``) test proqramı ``QUIZ-TEST-20261120`` + onun 2026 kurikulumu və hər hesaba ``enrolled``
  akademik qeyd (``group=TestQrup``) — imtahan sehrbazında «TestQrup» seçilən quiz bu tələbələrə görünür
  (``Exam.allowed_units`` → cari aktiv qeydin qrupu). Qeyd YARANARKƏN qrupla yazılır (köçürmə deyil).
* Paket audit sətri (``resource_type=accounts.quiz_test_accounts_batch``, hesab id-ləri — parol yox).

İDEMPOTENT: təkrar apply dublikat yaratmır — parolu yenidən ``12345678`` edir, hesabı / profili / üzvlüyü / qeydi
aktivləşdirir, ilk-giriş bayraqlarını düşürür və hesabın login bloku (rate-limit vedrəsi) təmizlənir.

QORUNMA: siyahıdakı ad BAŞQA (işarəsiz) hesabdadırsa, eyni adda işarəsiz qrup varsa və ya istifadəçi adı başqa
hesabın e-poçtudursa — heç nə yazılmır (``CommandError``).

``--undo`` (``--apply`` ilə yazır): YALNIZ bu əmrin audit paketlərində olan VƏ işarəli (ad + e-poçt) hesablar silinir
(qeyd, üzvlük, profil kaskadla), sonra işarəli ``TestQrup`` və test proqramı. Silinə bilməyən (qorunan istinad)
hesab bağlanır (``is_active=False``, parol yararsız), qrup / proqram arxivlənir — sayı xülasədə görünür.

DEFOLT DRY-RUN (hər şey tranzaksiyada icra olunub geri alınır). Stdout-a YALNIZ ``quiz_test: açar=dəyər`` saylar —
parol heç vaxt çap olunmur.

    manage.py create_quiz_test_accounts_20261120 --org qku --actor <superadmin> [--apply] [--undo]
"""

from __future__ import annotations

import re
import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts import quiz_test_accounts as spec
from core.audit import log_action
from core.constants import AuditAction, OrgUnitType
from core.rls import apply_rls_request_context, bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

PREFIX = "quiz_test:"
RESOURCE = "accounts.quiz_test_accounts_batch"
REASON = "Quiz üçün müvəqqəti test hesabları — sahibin 2026-11-20 tapşırığı"
UNDO_REASON = "Quiz test hesabları silindi — sahibin 2026-11-20 tapşırığı (create_quiz_test_accounts_20261120 --undo)"


class _DryRunRollback(Exception):
    pass


def new_batch() -> str:
    return f"quiztest-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _models():
    get = django_apps.get_model
    return {
        "profile": get("accounts", "UserProfile"),
        "membership": get("organizations", "Membership"),
        "unit": get("organizations", "OrgUnit"),
        "program": get("registrar", "Program"),
        "curriculum": get("registrar", "Curriculum"),
        "record": get("registrar", "StudentAcademicRecord"),
        "audit": get("audit", "AuditLog"),
    }


def _guard_conflicts(user_model, unit_model, organization) -> dict:
    """Siyahıdakı adlar: ``{ad: işarəli hesab}``; başqasına aid ad / qrup varsa ``CommandError``."""
    ours = {}
    for user in user_model.objects.filter(username__in=spec.USERNAMES):
        if not spec.is_quiz_test_account(user):
            raise CommandError("username_taken_by_other_account")
        ours[user.username] = user
    if user_model.objects.filter(email__in=spec.USERNAMES).exists():
        raise CommandError("username_is_other_account_email")
    for name in spec.USERNAMES:
        if name not in ours and user_model.objects.filter(username__iexact=name).exists():
            raise CommandError("username_taken_by_other_account")
    foreign = unit_model.objects.filter(
        organization=organization, unit_type=OrgUnitType.GROUP, name__iexact=spec.GROUP_NAME
    ).exclude(settings__has_key=spec.GROUP_MARKER_KEY)
    if foreign.exists():
        raise CommandError("group_name_taken")
    return ours


def _ensure_group(unit_model, organization, *, batch, counts):
    group = unit_model.objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        settings__has_key=spec.GROUP_MARKER_KEY,
    ).first()
    if group is None:
        if unit_model.objects.filter(organization=organization, slug=spec.GROUP_SLUG).exists():
            raise CommandError("group_slug_taken")
        counts["group_created"] += 1
        return unit_model.objects.create(
            organization=organization,
            parent=None,
            unit_type=OrgUnitType.GROUP,
            name=spec.GROUP_NAME,
            slug=spec.GROUP_SLUG,
            settings={"capacity": spec.COUNT, "language_sector": "", spec.GROUP_MARKER_KEY: batch},
            is_active=True,
        )
    counts["group_existing"] += 1
    if not group.is_active or group.name != spec.GROUP_NAME:
        group.is_active = True
        group.name = spec.GROUP_NAME
        group.save(update_fields=["is_active", "name", "updated_at"])
        counts["group_reactivated"] += 1
    return group


def _ensure_program(models, organization, counts):
    from apps.accounts.services.intake.create import ensure_curriculum

    program = models["program"].objects.filter(organization=organization, code=spec.PROGRAM_CODE).first()
    if program is None:
        # Arxiv proqram: real qəbul / kataloq seçicilərində görünmür, yalnız test qeydləri ona bağlıdır.
        program = models["program"].objects.create(
            organization=organization, code=spec.PROGRAM_CODE, name=spec.PROGRAM_NAME, is_active=False
        )
        counts["program_created"] += 1
    curriculum = ensure_curriculum(organization, program, spec.ADMISSION_YEAR)
    return program, curriculum


def _ensure_user(user_model, username, existing, counts):
    user = existing.get(username)
    if user is None:
        user = user_model.objects.create_user(username=username, email=spec.email_for(username), password=spec.PASSWORD)
        counts["users_created"] += 1
    else:
        counts["users_existing"] += 1
        if not user.check_password(spec.PASSWORD):
            user.set_password(spec.PASSWORD)
            counts["passwords_reset"] += 1
    if not user.is_active:
        counts["users_unblocked"] += 1
    user.first_name = spec.FIRST_NAME
    user.last_name = spec.last_name_for(username)
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
    user.save()
    return user


def _ensure_profile(models, user, organization, counts):
    profile, _created = models["profile"].objects.get_or_create(user=user)
    if profile.access_state != models["profile"].AccessState.ACTIVE:
        counts["access_reopened"] += 1
    if profile.password_change_required or not profile.email_verified:
        counts["first_login_cleared"] += 1
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = ProfileRole.STUDENT
    profile.access_state = models["profile"].AccessState.ACTIVE
    profile.password_change_required = False
    profile.email_verified = True
    profile.is_deleted = False
    profile.deleted_at = None
    profile.student_group_number = spec.GROUP_NAME
    profile.save()


def _ensure_membership(models, user, organization, role, actor, counts):
    membership = models["membership"].objects.filter(user=user, organization=organization, role=role).first()
    if membership is None:
        models["membership"].objects.create(
            user=user, organization=organization, role=role, assigned_by=actor, is_primary=True, is_active=True
        )
        counts["memberships_created"] += 1
        return
    if not membership.is_active or not membership.is_primary:
        membership.is_active = True
        membership.is_primary = True
        membership.save(update_fields=["is_active", "is_primary"])
        counts["memberships_reactivated"] += 1


def _ensure_record(models, user, organization, *, group, program, curriculum, counts):
    record = models["record"].objects.filter(organization=organization, student=user, program=program).first()
    if record is None:
        models["record"].objects.create(
            organization=organization,
            student=user,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=spec.ADMISSION_YEAR,
            status="enrolled",
            is_active=True,
        )
        counts["records_created"] += 1
        return
    if record.group_id != group.pk:
        # Qrup yalnız rəsmi köçürmə ilə dəyişir — test hesabında bu olmamalıdır; sayılır, toxunulmur.
        counts["records_other_group"] += 1
    if record.status != "enrolled" or not record.is_active:
        record.status = "enrolled"
        record.is_active = True
        record.save(update_fields=["status", "is_active", "updated_at"])
        counts["records_reactivated"] += 1


def _clear_login_limits(usernames) -> None:
    from apps.accounts.identity import login_rate_identity
    from apps.accounts.views.auth.constants import LOGIN_LIMIT_SCOPE_ACCOUNT
    from core.rate_limit import clear_rate_limit

    for username in usernames:
        clear_rate_limit(LOGIN_LIMIT_SCOPE_ACCOUNT, login_rate_identity(username))


def ensure_accounts(organization, *, actor, batch) -> tuple[Counter, list]:
    from apps.accounts.services.intake.create import student_role

    models = _models()
    user_model = get_user_model()
    counts = Counter()
    existing = _guard_conflicts(user_model, models["unit"], organization)
    group = _ensure_group(models["unit"], organization, batch=batch, counts=counts)
    program, curriculum = _ensure_program(models, organization, counts)
    role = student_role(organization)
    user_ids = []
    for username in spec.USERNAMES:
        user = _ensure_user(user_model, username, existing, counts)
        _ensure_profile(models, user, organization, counts)
        _ensure_membership(models, user, organization, role, actor, counts)
        _ensure_record(models, user, organization, group=group, program=program, curriculum=curriculum, counts=counts)
        user_ids.append(user.pk)
    counts["accounts"] = len(user_ids)
    counts["group_students"] = (
        models["record"]
        .objects.filter(organization=organization, group=group, is_active=True, status="enrolled")
        .count()
    )
    log_action(
        AuditAction.CREATE if counts["users_created"] else AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={
            "users": user_ids,
            "group": str(group.pk),
            "program": str(program.pk),
            "created": counts["users_created"],
        },
        reason=f"{REASON} [{batch}]",
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
    )
    return counts, user_ids


def _audited_user_ids(models) -> set:
    ids = set()
    for values in models["audit"].objects.filter(resource_type=RESOURCE).values_list("new_values", flat=True):
        ids.update(int(pk) for pk in (values or {}).get("users", []) if str(pk).isdigit())
    return ids


def _delete_or_close_user(models, user, organization, counts) -> None:
    try:
        with transaction.atomic():
            user.delete()
        counts["users_deleted"] += 1
        return
    except Exception:  # noqa: BLE001 — qorunan istinad (PROTECT / trigger): hesab bağlanır, silinmir
        counts["users_closed_not_deleted"] += 1
    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=["is_active", "password"])
    models["membership"].objects.filter(user=user, organization=organization).update(is_active=False)


def _delete_or_archive(instance, field_updates, counts, *, deleted_key, kept_key) -> None:
    try:
        with transaction.atomic():
            instance.delete()
        counts[deleted_key] += 1
        return
    except Exception:  # noqa: BLE001 — qorunan istinad: arxivlənir
        counts[kept_key] += 1
    for field, value in field_updates.items():
        setattr(instance, field, value)
    instance.save(update_fields=[*field_updates, "updated_at"])


def undo_accounts(organization, *, actor, batch) -> Counter:
    models = _models()
    user_model = get_user_model()
    counts = Counter(users_deleted=0)
    audited = _audited_user_ids(models)
    deleted_ids = []
    for user in user_model.objects.filter(username__in=spec.USERNAMES).order_by("pk"):
        if not spec.is_quiz_test_account(user) or user.pk not in audited:
            counts["skipped_not_created_by_command"] += 1
            continue
        deleted_ids.append(user.pk)
        _delete_or_close_user(models, user, organization, counts)
    group = (
        models["unit"]
        .objects.filter(
            organization=organization,
            unit_type=OrgUnitType.GROUP,
            settings__has_key=spec.GROUP_MARKER_KEY,
        )
        .first()
    )
    if group is not None:
        if models["record"].objects.filter(group=group).exists():
            counts["group_kept_has_other_records"] += 1
            group.is_active = False
            group.save(update_fields=["is_active", "updated_at"])
        else:
            _delete_or_archive(
                group, {"is_active": False}, counts, deleted_key="group_deleted", kept_key="group_archived"
            )
    program = models["program"].objects.filter(organization=organization, code=spec.PROGRAM_CODE).first()
    if program is not None:
        if models["record"].objects.filter(program=program).exists():
            counts["program_kept_has_records"] += 1
        else:
            _delete_or_archive(
                program, {"is_active": False}, counts, deleted_key="program_deleted", kept_key="program_archived"
            )
    log_action(
        AuditAction.DELETE,
        user=actor,
        organization=organization,
        new_values={"users": deleted_ids, "undo": True},
        reason=f"{UNDO_REASON} [{batch}]",
        resource_type=f"{RESOURCE}_undo",
        resource_id=batch,
        resource_repr=batch,
    )
    return counts


def failure_code(exc) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", f"{type(exc).__name__}_{exc}".lower()).strip("_")
    return f"quiz_test_failed_{text}"[:120]


class Command(BaseCommand):
    help = "Quiz üçün 30 müvəqqəti test tələbə hesabı (testuser1..30, TestQrup) — dry-run defolt; --undo silir."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="qku")
        parser.add_argument("--actor", required=True, help="Aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="Faktiki yaz (defolt: dry-run)")
        parser.add_argument("--undo", action="store_true", help="Bu əmrin yaratdıqlarını sil")

    def handle(self, *args, **options):
        with bypass_rls():
            organization = (
                django_apps.get_model("organizations", "Organization").objects.filter(slug=options["org"]).first()
            )
            actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if organization is None:
            raise CommandError("organization_not_found")
        if actor is None or not actor.is_superuser:
            raise CommandError("actor_must_be_active_superuser")
        apply, undo = bool(options["apply"]), bool(options["undo"])
        batch = new_batch()
        counts = Counter()
        try:
            with transaction.atomic(), rls_worker_atomic(), bypass_rls():
                apply_rls_request_context(user_id=actor.pk, org_id=organization.pk, bypass=True)
                if undo:
                    counts = undo_accounts(organization, actor=actor, batch=batch)
                else:
                    counts, _user_ids = ensure_accounts(organization, actor=actor, batch=batch)
                if not apply:
                    raise _DryRunRollback()
        except _DryRunRollback:
            pass
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001 — prod-data-ops yalnız kodu göstərir
            raise CommandError(failure_code(exc)) from exc
        if apply and not undo:
            _clear_login_limits(spec.USERNAMES)
        mode = ("undo_" if undo else "") + ("apply" if apply else "dry_run")
        shown = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        self.stdout.write(f"{PREFIX} mode={mode} {shown}".rstrip())
        if apply:
            self.stdout.write(f"{PREFIX} batch={batch}")
