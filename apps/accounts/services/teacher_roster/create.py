"""«Hesab yoxdur» sətirlərinə FİN-SİZ müəllim hesabı (``--create-missing``, sahib 2026-10-11).

Sahib: «FİN-i keç, onları əlavə et; FİN-i sonra həll edəcəyik.» Forma 7-də FİN sütunu yoxdur, ona görə
RİM-in tək-tək səthi (FİN məcburi) yox, heyət siyahısının (``seed_staff_roster``) FİN-siz yolu işlədilir:
``intake.create.create_account(kind="teacher", fin=None)`` — eyni ``User`` + ``UserProfile`` + ``Membership``
nüvəsi, eyni ``password_change_required`` müqaviləsi, eyni audit sətri.

QAYDALAR

* YALNIZ ``not_found`` sətirlər. Çox mənalı / ata adı fərqli / oxşar / yalnız tələbə — əl ilə həll olunur.
  Eyni ad + ata adı faylda bir neçə sətirdədirsə (iki kafedra, ştat + saathesabı) — BİR hesab
  (uyğun hesablardakı ``multi_row`` qaydası ilə eyni: ştat cəmlənir, hər kafedraya müəllim üzvlüyü).
* İstifadəçi adı ``ad.soyad`` (``staff_roster.username_seed``); tutulubsa ``ad.soyad2``, ``ad.soyad3`` …
  (``username_repair`` qaydası). E-poçt: ``roster.<istifadəçi adı>@placeholder.invalid`` (RFC 2606 — poçt
  getmir, parol bərpası RİM-ə yönləndirir; istifadəçi ilk girişdə real e-poçtunu yazır). FİN ``NULL``
  (sahə unikal və nullable-dır — boş sətir toqquşardı, ``NULL`` toqquşmur).
* Parol: ``--credentials-out`` verilməyibsə hesab parolsuz yaranır (``set_unusable_password`` — köçürülmüş
  hesablar kimi); birdəfəlik parolu RİM «Parol təyin et» ilə verir. Verilibsə birdəfəlik parollar YALNIZ o
  fayla (0600) yazılır — stdout/hesabat/audit-ə heç vaxt düşmür. Hər iki halda ilk girişdə öz parolu məcburidir.
* İdempotentlik: yaradılan hesab növbəti qaçışda ad + ata adı ilə ``matched`` olur → yenidən yaradılmır.
* Geri qaytarma (``undo``): hesab HEÇ GİRMƏYİBSƏ və bu paketin yazdığından (hesab, profil, üzvlük) başqa
  heç bir sətri yoxdursa — SİLİNİR; əks halda (giriş edib, dərs/jurnal/sillabus bağlanıb …) silinmir,
  mövcud «Hesabı dayandır» servisi ilə BLOKLANIR (məlumat itməsin). Hər iki hal auditdədir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import DatabaseError, router, transaction
from django.db.models.deletion import Collector, ProtectedError

from core.audit import log_action
from core.constants import AuditAction

from ...identity import PLACEHOLDER_EMAIL_DOMAIN
from ..staff_roster import username_seed
from .matching import STATUS_NOT_FOUND
from .parsing import DEGREE_RANK, TITLE_RANK
from .plan import TITLE_TO_POSITION, aggregate_rate, best_value

EMAIL_PREFIX = "roster"
#: Yaradılmış hesabın «öz» sətirləri — undo zamanı bunlardan başqa bağlı sətir varsa hesab SİLİNMİR.
OWN_MODELS = frozenset({"auth.user", "accounts.userprofile", "organizations.membership"})
UNDO_BLOCK_REASON_CODE = "other"
UNDO_BLOCK_CONTACT_CODE = "rim"


@dataclass
class NewAccount:
    last: str
    first: str
    patronymic: str
    rows: list = field(default_factory=list)
    chair_ids: list = field(default_factory=list)  # sıra ilə, təkrarsız (birincisi əsas üzvlük)
    title: str | None = None
    degree: str | None = None
    position: str | None = None
    staff_fraction: object = None
    is_external: bool | None = None
    username: str = ""  # önizləmə (dry-run) / yaradılan ad (apply)

    @property
    def display(self) -> str:
        return " ".join(part for part in (self.last, self.first, self.patronymic) if part)


def claim_name_username(base: str, *, taken=()) -> str:
    """``ad.soyad`` → boş ad: tutulubsa ``ad.soyad2``, ``ad.soyad3`` … (``username_repair`` qaydası).

    Giriş «istifadəçi adı VƏ YA e-poçt» qəbul edir — ona görə e-poçt sahəsi də yoxlanılır
    (``intake.create.claim_username`` ilə eyni ehtiyat).
    """
    users = get_user_model().objects
    taken = {name.lower() for name in taken}
    candidate, suffix = base, 1
    while (
        candidate.lower() in taken
        or users.filter(username__iexact=candidate).exists()
        or users.filter(email__iexact=candidate).exists()
    ):
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


def plan_new_accounts(plan) -> list:
    """``not_found`` sətirləri → ``[NewAccount]`` (YAZMIR; istifadəçi adı yalnız önizləmədir)."""
    chair_by_name = {chair: (mapped.get("unit") or (None,))[0] for chair, mapped in plan.chair_map.items()}
    grouped: dict = {}
    for match in plan.matches:
        if match.status != STATUS_NOT_FOUND:
            continue
        name = match.row.name
        bucket = grouped.setdefault(
            (name.last_key, name.first_key, name.patronymic_key),
            NewAccount(last=name.last, first=name.first, patronymic=name.patronymic),
        )
        bucket.rows.append(match.row)
        chair_id = chair_by_name.get(match.row.chair)
        if chair_id is not None and chair_id not in bucket.chair_ids:
            bucket.chair_ids.append(chair_id)
    taken: set = set()
    for item in grouped.values():
        item.title = best_value([row.title for row in item.rows], TITLE_RANK)
        item.degree = best_value([row.degree for row in item.rows], DEGREE_RANK)
        item.position = TITLE_TO_POSITION.get(item.title or "")
        item.staff_fraction, item.is_external = aggregate_rate(item.rows)
        item.username = claim_name_username(username_seed(f"{item.last} {item.first}"), taken=taken)
        taken.add(item.username)
    return list(grouped.values())


def _open_private(path: str):
    """0600 rejimli fayl (parollar) — mövcud faylın rejimi də daraldılır."""
    fd = os.open(os.path.expanduser(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="")


def write_credentials(path: str, credentials: list) -> None:
    import csv

    with _open_private(path) as handle:
        writer = csv.writer(handle)
        writer.writerow(["username", "ad", "kafedra", "birdəfəlik_parol"])
        writer.writerows(credentials)


def create_accounts(new_accounts, *, plan, actor, tag: str, keep_passwords: bool):
    """Hesabları yaradır. Qaytarır: ``(manifest sətirləri, workload sətirləri, parollar)``.

    Çağıran ``rls_worker_atomic`` + RLS konteksti içindədir (bir tranzaksiya, xətada hamısı geri).
    """
    from apps.organizations.models import Membership, OrgUnit
    from apps.workload.public import sync_roster_profile

    from ..intake.create import IntakeApplyError, create_account, teacher_role
    from .apply import RosterError

    organization = plan.organization
    try:
        role = teacher_role(organization)
    except IntakeApplyError as exc:
        raise RosterError(exc.code, exc.message) from None
    units = OrgUnit.objects.in_bulk([chair for item in new_accounts for chair in item.chair_ids])
    created, workload, credentials, taken = [], [], [], set()
    for item in new_accounts:
        username = claim_name_username(username_seed(f"{item.last} {item.first}"), taken=taken)
        taken.add(username)
        chairs = [units[chair_id] for chair_id in item.chair_ids if chair_id in units]
        primary = chairs[0] if chairs else None
        user, password = create_account(
            organization=organization,
            kind="teacher",
            values={
                "username": username,
                "first_name": item.first,
                "last_name": item.last,
                "email": f"{EMAIL_PREFIX}.{username}@{PLACEHOLDER_EMAIL_DOMAIN}",
                "fin": None,  # Forma 7-də FİN yoxdur; sahə unikal + nullable — boş sətir toqquşardı
                "patronymic": item.patronymic,
                "gender": "",
                "birth_date": None,
                "phone": "",
                "student_code": "",
                "academic_title": item.title or "",
                "academic_degree": item.degree or "",
                "department": primary.name if primary else "",
            },
            role=role,
            actor=actor,
            scope_unit=primary,
            audit_reason=f"teacher_roster_created {tag}",
        )
        if keep_passwords:
            credentials.append((username, item.display, primary.name if primary else "", password))
        else:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        for unit in chairs[1:]:
            Membership.objects.get_or_create(
                user=user,
                organization=organization,
                role=role,
                scope_unit=unit,
                defaults={"is_active": True, "assigned_by": actor},
            )
        created.append({"user": user.pk, "username": username, "rows": [row.row_no for row in item.rows]})
        item.username = username
        if item.position is None and item.staff_fraction is None:
            continue
        result = sync_roster_profile(
            organization=organization,
            teacher=user,
            academic_year=plan.academic_year,
            position=item.position,
            staff_fraction=item.staff_fraction,
            is_external=item.is_external,
            actor=actor,
            reason=f"Forma 7 tutuşdurması {tag}",
            dry_run=False,
        )
        if result["changed"]:
            workload.append({"user": user.pk, "before": result["before"], "after": result["after"]})
    return created, workload, credentials


def _foreign_rows(user) -> set:
    """Hesabı silsək Django-nun aparacağı, «öz» sətirlərdən KƏNAR modellər (boş = təhlükəsiz silinir)."""
    collector = Collector(using=router.db_for_write(type(user)))
    try:
        collector.collect([user])
    except ProtectedError:
        return {"protected"}
    labels = {model._meta.label_lower for model, objects in collector.data.items() if objects}
    labels |= {qs.model._meta.label_lower for qs in collector.fast_deletes if qs.exists()}
    return labels - OWN_MODELS


def undo_created(entries, *, actor, organization, tag: str, note: str) -> dict:
    """Paketin yaratdığı hesablar: toxunulmamışsa SİL, istifadə olunubsa BLOKLA (məlumat itmir)."""
    from ..account_deletion import AccountDeletionError, block_account

    users = get_user_model().objects.select_related("profile").in_bulk([entry["user"] for entry in entries])
    result = {"deleted": [], "deactivated": [], "kept": []}
    for entry in entries:
        user = users.get(entry["user"])
        if user is None:
            continue  # artıq silinib (təkrar undo)
        foreign = _foreign_rows(user) if user.last_login is None else {"logged_in"}
        if not foreign:
            try:
                with transaction.atomic():
                    log_action(
                        AuditAction.DELETE,
                        user=actor,
                        organization=organization,
                        changes={"username": user.username, "batch": tag},
                        reason=note,
                        resource_type="User",
                        resource_id=str(user.pk),
                        resource_repr=user.username,
                    )
                    user.delete()
            except (ProtectedError, DatabaseError):
                foreign = {"delete_failed"}
            else:
                result["deleted"].append(entry["user"])
                continue
        if not user.is_active:
            result["kept"].append(entry["user"])
            continue
        try:
            block_account(
                user,
                actor=actor,
                reason=f"{note} — yaradılmış hesab istifadə olunub ({', '.join(sorted(foreign))}) {tag}"[:300],
                reason_code=UNDO_BLOCK_REASON_CODE,
                contact_code=UNDO_BLOCK_CONTACT_CODE,
            )
        except AccountDeletionError:
            result["kept"].append(entry["user"])
            continue
        result["deactivated"].append(entry["user"])
    return result


__all__ = [
    "NewAccount",
    "claim_name_username",
    "create_accounts",
    "plan_new_accounts",
    "undo_created",
    "write_credentials",
]
