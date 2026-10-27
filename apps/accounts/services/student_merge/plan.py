"""Tələbə dublikatı birləşdirmə planı — faylın oxunuşu və cütün QAPILARI (RİM MR-000030.2, 2026-10-27).

Köhnə sistem deltası (10-24/10-25) bəzi tələbələr üçün ikinci hesab yaratdı: real hesab (ATİS, 7 simvollu FİN,
tələbə onunla daxil olur) + delta hesabı (legacy «FİN» sahəsində şəxsiyyət vəsiqəsinin nömrəsi, 6 simvollu FİN və ya
boş → «fərqli FİN = başqa adam» qaydası tutmadı). Legacy xanalar ikinci hesabın sətrindədir.

Plan (``student-merge/1``) YALNIZ sahibin təsdiqlədiyi cütlərdir — ``{"duplicate": id, "keep": id}``; namizəd
siyahısı (FİN, doğum tarixi, qrup, son giriş — adlı) lokal qurulur və repoya düşmür. Hər cüt tətbiqdə yenidən
yoxlanılır (biri pozulsa cüt ATLANIR, səbəb kodu sayılır):

* hər iki hesab mövcud, fərqli, təşkilatın tələbə üzvlüyü var; saxlanılan hesab aktivdir;
* dublikat köhnə sistem deltasının YARATDIĞI hesabdır (``legacy_import.delta_batch`` audit manifesti);
* ad + soyad eynidir (NFKC, böyük/kiçik hərf fərqi nəzərə alınmır);
* dublikat heç vaxt daxil olmayıb (tələbə real hesabla daxil olur) — daxil olubsa hansının «əsl» olduğu sahibin
  qərarıdır, birləşdirilmir;
* ziddiyyət yoxdur: hər ikisində FİN formatlı (7 simvol, hərf + rəqəm) fərqli FİN, fərqli doğum tarixi → atlanır.
"""

from __future__ import annotations

import json
import re
import unicodedata

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

FORMAT = "student-merge/1"
DELTA_BATCH_RESOURCE = "legacy_import.delta_batch"
FIN_RE = re.compile(r"^(?=.*[A-Z])(?=.*[0-9])[0-9A-Z]{7}$")
DOCUMENT_RE = re.compile(r"^(AA|AB|AZE)[0-9]+$")


class MergePlanError(Exception):
    """Plan faylı oxunmadı / formatı səhvdir (kod stdout-a çıxır)."""


def load(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise MergePlanError("file_unreadable") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("pairs"), list):
        raise MergePlanError("bad_format")
    pairs = []
    for row in data["pairs"]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("duplicate"), int)
            or not isinstance(row.get("keep"), int)
        ):
            raise MergePlanError("bad_row")
        pairs.append((row["duplicate"], row["keep"]))
    if len({dup for dup, _keep in pairs}) != len(pairs):
        raise MergePlanError("duplicate_listed_twice")
    return pairs


def _norm(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold().replace("i̇", "i").replace("ı", "i")
    return " ".join(text.split())


def fin_like(value) -> bool:
    value = str(value or "").strip().upper()
    return bool(FIN_RE.match(value)) and not DOCUMENT_RE.match(value)


def delta_created_ids(organization) -> set:
    audit_model = django_apps.get_model("audit", "AuditLog")
    created = set()
    for values in audit_model.objects.filter(organization=organization, resource_type=DELTA_BATCH_RESOURCE).values_list(
        "new_values", flat=True
    ):
        for raw in ((values or {}).get("created") or {}).get("students") or []:
            try:
                created.add(int(raw))
            except (TypeError, ValueError):
                continue
    return created


def check_pair(organization, duplicate, keep, *, created: set) -> str:
    """``""`` — cüt keçdi; yoxsa səbəb kodu."""
    membership_model = django_apps.get_model("organizations", "Membership")
    if duplicate is None or keep is None:
        return "user_missing"
    if duplicate.pk == keep.pk:
        return "same_user"
    if not keep.is_active:
        return "keep_inactive"
    students = set(
        membership_model.objects.filter(
            organization=organization, user_id__in=[duplicate.pk, keep.pk], role__name="student"
        ).values_list("user_id", flat=True)
    )
    if students != {duplicate.pk, keep.pk}:
        return "not_students"
    if duplicate.pk not in created:
        return "duplicate_not_import_created"
    if (_norm(duplicate.first_name), _norm(duplicate.last_name)) != (_norm(keep.first_name), _norm(keep.last_name)):
        return "name_mismatch"
    if duplicate.last_login is not None:
        return "duplicate_has_login"
    dup_profile, keep_profile = getattr(duplicate, "profile", None), getattr(keep, "profile", None)
    dup_fin, keep_fin = (getattr(dup_profile, "fin", "") or "").upper(), (
        getattr(keep_profile, "fin", "") or ""
    ).upper()
    if fin_like(dup_fin) and fin_like(keep_fin) and dup_fin != keep_fin:
        return "fin_conflict"
    dup_birth, keep_birth = getattr(dup_profile, "birth_date", None), getattr(keep_profile, "birth_date", None)
    if dup_birth and keep_birth and dup_birth != keep_birth:
        return "birth_date_conflict"
    return ""


def users(ids) -> dict:
    return {user.pk: user for user in get_user_model().objects.select_related("profile").filter(pk__in=list(ids))}


__all__ = ["FORMAT", "MergePlanError", "check_pair", "delta_created_ids", "fin_like", "load", "users"]
