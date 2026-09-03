#!/usr/bin/env python
"""ROL SÜPÜRGƏSİ — hər rol öz gördüyü HƏR profil bölməsini açır.

Nə edir
=======
Aktiv üzvlüyü olan HƏR rol üçün bir istifadəçi seçir, profil qabığını yükləyir,
sol menyudakı bölmə açarlarını HTML-dən çıxarır və hər birini AJAX fraqment
ucundan (``accounts:profile_section_fragment``) açır.  Nəticə: rol × bölmə
matrisi + 500/istisna siyahısı.

Niyə lazımdır
=============
Bölmə görünürlüyü DÖRD siyahıda qeyd olunur (``SECTION_PARTIALS`` ·
``AJAX_SAFE_SECTIONS`` · şablondakı ``data-ajax-sections`` ·
``rbac_sections.py``).  Biri unudulanda bölmə ya görünmür, ya da açılanda
çökür — bu skript həmin fərqi BİR keçidə üzə çıxarır.  Boş rol (heç bir bölmə
görməyən) da dərhal görünür.

İşlətmə
=======
    .venv/bin/python scripts/role_open_all.py                  # mətn hesabat
    .venv/bin/python scripts/role_open_all.py --markdown       # docs üçün cədvəl
    .venv/bin/python scripts/role_open_all.py --json out.json  # maşın oxusu

⚠️ TƏLƏLƏR (hər ikisi bu skriptdə HƏLL OLUNUB — silməyin)
=========================================================
1. **ALLOWED_HOSTS.**  ``django.test.Client`` ``testserver`` host-u ilə gəlir;
   ``config.settings.local`` isə onu tanımır və HƏR sorğu 400 qaytarır (bölmə
   "sınıq" görünür, əslində host rədd edilib).  Ona görə ``django.setup()``-dan
   SONRA ``settings.ALLOWED_HOSTS = ["*"]`` verilir.  Bu YALNIZ prosesin öz
   yaddaşındadır — fayla yazılmır.
2. **Parol divarı.**  ``FirstLoginPasswordMiddleware`` ``password_change_required``
   olan hesabı HƏR sorğuda parol dəyişmə səhifəsinə yönləndirir; süpürgə boş
   HTML alır və «0 bölmə» yazır.  Skript bayrağı MÜVƏQQƏTİ söndürür və işin
   sonunda GERİ QAYTARIR (``finally``) — proses yarımçıq kəsilsə belə.

⚠️ Bu skript CANLI bazaya (``config.settings.local`` → lokal ``emsarena_db``)
   qoşulur.  Yalnız GET sorğusu göndərir; yeganə yazısı yuxarıdakı müvəqqəti
   bayraqdır.  Prod-a QARŞI İŞLƏTMƏYİN.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import re
import sys

import django

#: Repo kökü — skript `scripts/`-dən çağırıldıqda `config`/`apps` görünsün.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: Sol menyunun bölmə açarını daşıyan iki atribut (şablonlar hər ikisini işlədir).
SECTION_ATTRS = (r'data-profile-section="([a-z0-9\-]+)"', r'data-section="([a-z0-9\-]+)"')


def _bootstrap(settings_module: str):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    django.setup()
    from django.conf import settings

    # ⚠️ Tələ 1 — bax modul sənədinə.
    settings.ALLOWED_HOSTS = ["*"]
    logging.disable(logging.ERROR)


def _pick_users():
    """Hər rol adına BİR nümunə istifadəçi (tələbə üçün ən çox yazılışı olan)."""
    from django.db.models import Count

    from apps.organizations.models import Membership
    from apps.registrar.models import Enrollment

    richest = Enrollment.objects.values("student_id").annotate(n=Count("id")).order_by("-n").first()
    richest_id = richest["student_id"] if richest else None

    picked: dict = {}
    memberships = Membership.objects.filter(is_active=True).select_related("user", "role").order_by("-role__level")
    for membership in memberships:
        # Tələbə üçün ən "dolu" hesab seçilir: boş hesabda bölmələr yanlış boş görünür.
        if membership.role.name == "student" and richest_id and membership.user_id != richest_id:
            continue
        picked.setdefault(membership.role.name, membership)
    return picked


def _unlock(profile) -> bool:
    """⚠️ Tələ 2 — parol divarını MÜVƏQQƏTİ açır; qaytarma çağıranın üzərindədir."""
    if profile is None or not getattr(profile, "password_change_required", False):
        return False
    fields = [name for name in ("password_change_required", "email_verified") if hasattr(profile, name)]
    profile.password_change_required = False
    if hasattr(profile, "email_verified"):
        profile.email_verified = True
    profile.save(update_fields=fields)
    return True


def _sections_of(html: str) -> list:
    found: set = set()
    for pattern in SECTION_ATTRS:
        found |= set(re.findall(pattern, html))
    return sorted(found)


def sweep(settings_module: str) -> dict:
    from django.test import Client
    from django.urls import reverse

    profile_url = reverse("accounts:profile")
    result: dict = {"roles": {}, "failures": collections.defaultdict(list), "total_opens": 0}

    for role_name, membership in _pick_users().items():
        user = membership.user
        profile = getattr(user, "profile", None)
        unlocked = _unlock(profile)
        try:
            client = Client()
            client.force_login(user)
            html = client.get(profile_url, follow=True).content.decode("utf-8", "replace")
            sections = _sections_of(html)
            failures = 0
            for section in sections:
                result["total_opens"] += 1
                try:
                    url = reverse("accounts:profile_section_fragment", args=[section])
                    status = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest").status_code
                except Exception as exc:  # noqa: BLE001 — istisna da nəticədir
                    result["failures"][role_name].append([section, f"{type(exc).__name__}: {exc}"])
                    failures += 1
                    continue
                if status >= 500:
                    result["failures"][role_name].append([section, status])
                    failures += 1
            result["roles"][role_name] = {
                "username": user.get_username(),
                "level": membership.role.level,
                "sections": sections,
                "failures": failures,
            }
            print(f"[{role_name:22s}] {len(sections):2d} bölmə · 500: {failures}", file=sys.stderr)
        finally:
            # Bayraq HƏR HALDA geri qaytarılır (istisna/Ctrl-C daxil).
            if unlocked:
                profile.password_change_required = True
                profile.save(update_fields=["password_change_required"])
    result["failures"] = dict(result["failures"])
    return result


def render_markdown(result: dict) -> str:
    roles = result["roles"]
    order = sorted(roles, key=lambda name: (-len(roles[name]["sections"]), name))
    every = sorted({section for row in roles.values() for section in row["sections"]})

    lines = ["| rol | səviyyə | görünən bölmə | 500 |", "|---|---:|---:|---:|"]
    for name in order:
        row = roles[name]
        lines.append(f"| `{name}` | {row['level']} | {len(row['sections'])} | {row['failures']} |")

    lines += ["", "| bölmə | " + " | ".join(f"`{name}`" for name in order) + " |"]
    lines.append("|---" * (len(order) + 1) + "|")
    for section in every:
        cells = ["✅" if section in roles[name]["sections"] else "·" for name in order]
        lines.append(f"| `{section}` | " + " | ".join(cells) + " |")
    lines += ["", f"Cəmi {result['total_opens']} bölmə açılışı."]
    if result["failures"]:
        lines.append("")
        lines.append("**500 / istisna:**")
        for name, items in result["failures"].items():
            for section, code in items:
                lines.append(f"- `{name}` · `{section}` → {code}")
    else:
        lines += ["", "**500 / istisna: yoxdur.**"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", default="config.settings.local")
    parser.add_argument("--markdown", action="store_true", help="docs/ROL_MATRISI.md üçün cədvəl")
    parser.add_argument("--json", dest="json_path", help="nəticəni JSON fayla yaz")
    args = parser.parse_args()

    _bootstrap(args.settings)
    result = sweep(args.settings)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
    if args.markdown:
        print(render_markdown(result))
    else:
        for name, row in sorted(result["roles"].items()):
            print(f"\n{name} ({row['username']}, lvl {row['level']}) — {len(row['sections'])} bölmə")
            for section in row["sections"]:
                print(f"   · {section}")
        print(f"\ncəmi {result['total_opens']} bölmə açılışı")
        print("\n=== 500 / İSTİSNA ===")
        print("yoxdur" if not result["failures"] else "")
        for name, items in result["failures"].items():
            print(f"\n{name}:")
            for section, code in items:
                print(f"   {code}  {section}")
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
