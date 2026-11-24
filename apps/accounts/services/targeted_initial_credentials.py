"""Dəqiq siyahı üzrə ilkin parol (sahib 2026-11-20: «tək-tək edə bilmirəm, çıxar ver, copy edib qoyum»).

``issue_staff_credentials --target-users FAYL`` üçün köməkçi. Fayl sətirlərində istifadəçi id-si və ya istifadəçi
adı (sətirdə bir; ``#`` ilə başlayan sətirlər şərhdir). Fakültə/rol seçimi YOXDUR — yalnız siyahıdakı hesablar.

Qaydalar ``issue_staff_credentials``-ın digər rejimləri ilə eynidir:

* parol YALNIZ aktivləşməmiş hesaba (e-poçtu təsdiqlənməyib və ya ilk-giriş axını bitməyib) verilir — öz parolu
  ilə işləyən hesabın parolu SIFIRLANMIR;
* superadmin, ``is_staff``, deaktiv, bloklanmış və ya silinmiş hesaba toxunulmur;
* parol serverdə yaradılır (``Command._issue``), ilk girişdə e-poçt + OTP + yeni parol məcburidir.

Hesabat CSV-də parol YOXDUR; parollar yalnız ``--credentials-out`` faylına yazılır.
"""

from __future__ import annotations

import pathlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from core.export_safety import safe_csv_writer

MAX_TARGETS = 500
STATE_SKIPPED = "toxunulmur"


def read_targets(path: str) -> tuple[list[int], list[str]]:
    """Fayl → (id-lər, istifadəçi adları); təkrarlar atılır, sıra saxlanılır."""
    file = pathlib.Path(path)
    if not file.exists():
        raise CommandError("--target-users faylı tapılmadı.")
    ids: list[int] = []
    names: list[str] = []
    for raw in file.read_text(encoding="utf-8").splitlines():
        value = raw.split("\t", 1)[0].strip()
        if not value or value.startswith("#"):
            continue
        if value.isdigit():
            if int(value) not in ids:
                ids.append(int(value))
        elif value.casefold() not in names:
            names.append(value.casefold())
    if not ids and not names:
        raise CommandError("--target-users faylı boşdur.")
    if len(ids) + len(names) > MAX_TARGETS:
        raise CommandError(f"--target-users ən çox {MAX_TARGETS} hesab ola bilər.")
    return ids, names


def _placement_label(command, organization, user) -> str:
    """Tələbə üçün qrup (alt qrup ilə), işçi üçün vəzifə/rol — siyahıda «Qrup/vəzifə» sütunu."""
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    record = (
        Record.objects.filter(organization=organization, student=user, is_active=True)
        .select_related("group__parent__parent__parent__parent__parent")
        .order_by("-created_at")
        .first()
    )
    if record is not None and record.group_id:
        _faculty, group_name, subgroup, _specialty = command._placement(record.group)
        return f"{group_name} ({subgroup})" if subgroup else group_name
    Membership = django_apps.get_model("organizations", "Membership")
    roles = sorted(
        {
            m.role.display_name or m.role.name
            for m in Membership.objects.filter(organization=organization, user=user, is_active=True).select_related(
                "role"
            )
        }
    )
    position = (getattr(getattr(user, "profile", None), "staff_position", "") or "").strip()
    return position or ", ".join(roles)


def collect(command, organization, path: str, *, activated) -> tuple[list[dict], list[dict], int]:
    """Siyahıdakı hesabların sətirləri, parol veriləcəklər və tapılmayanların sayı."""
    ids, names = read_targets(path)
    User = get_user_model()
    found = {
        u.pk: u
        for u in User.objects.filter(pk__in=ids).select_related("profile")
        | User.objects.filter(username__in=names).select_related("profile")
    }
    by_name = {u.username.casefold(): u for u in found.values()}
    ordered, seen = [], set()
    for key in [*ids, *names]:
        user = found.get(key) if isinstance(key, int) else by_name.get(key)
        if user is not None and user.pk not in seen:
            seen.add(user.pk)
            ordered.append(user)
    missing = len(ids) + len(names) - len(ordered)
    Membership = django_apps.get_model("organizations", "Membership")
    members = set(
        Membership.objects.filter(organization=organization, is_active=True, user__in=ordered).values_list(
            "user_id", flat=True
        )
    )
    rows, targets = [], []
    for user in ordered:
        profile = getattr(user, "profile", None)
        in_org = profile is not None and (
            user.pk in members or str(profile.organization_id or "") == str(organization.pk)
        )
        safe = (
            in_org
            and user.is_active
            and not user.is_superuser
            and not user.is_staff
            and getattr(profile, "access_state", "active") == "active"
            and not getattr(profile, "is_deleted", False)
            and getattr(profile, "blocked_at", None) is None
        )
        row = {
            "kind": "target",
            "user_id": user.pk,
            "user": user,
            "faculty": "",
            "placement": _placement_label(command, organization, user) if in_org else "",
            "full_name": (f"{user.last_name} {user.first_name}").strip() or user.username,
            "username": user.username,
        }
        if not safe:
            row["state"], row["action"] = STATE_SKIPPED, "deaktiv / bloklanıb / başqa təşkilat — parol verilmir"
        elif activated(profile):
            row["state"], row["action"] = "aktivləşib", "öz parolu ilə işləyir — parol verilmir"
        else:
            row["state"], row["action"] = "aktivləşməyib", "yeni ilkin parol veriləcək"
            targets.append(row)
        rows.append(row)
    return rows, targets, missing


def write_report(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = safe_csv_writer(fh)
        writer.writerow(["user_id", "ad_soyad", "qrup_vezife", "username", "veziyyet", "emel"])
        for r in rows:
            writer.writerow([r["user_id"], r["full_name"], r["placement"], r["username"], r["state"], r["action"]])


def write_credentials(path: str, issued: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = safe_csv_writer(fh)
        writer.writerow(["user_id", "ad_soyad", "qrup_vezife", "username", "ilkin_parol"])
        for r in issued:
            writer.writerow([r["user_id"], r["full_name"], r["placement"], r["username"], r["password"]])
