#!/usr/bin/env python3
"""EMSArena i18n — 2026-09-15: superadmin təşkilat cədvəlinin EN başlıqları.

Sahibin serverdə gördüyü: EN dilində «Table organization», «Detail code» kimi xam
açar-mətnlər (auto-doldurulmuş msgstr). Yalnız EN msgstr-ləri düzəldir; AZ/RU/TR
düzgündür. `makemessages` İŞLƏDİLMİR; sonra `compilemessages`.

İstifadə:  python scripts/i18n_fix_superadmin_orgs_en_2026_09_15.py
"""

import os

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = "profile.superadmin_orgs"
EN = {
    "table_organization": "Organization",
    "table_type": "Type",
    "table_owner": "Owner",
    "table_status": "Status",
    "table_active_members": "Active members",
    "table_details": "Details",
    "table_manage": "Manage",
    "detail_code": "Code",
    "detail_license": "License / TIN",
    "detail_suspend_reason": "Suspension reason",
}


def main():
    path = os.path.join(BASE, "locale", "en", "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    changed = 0
    for entry in po:
        if entry.msgctxt == CTX and entry.msgid in EN and entry.msgstr != EN[entry.msgid]:
            entry.msgstr = EN[entry.msgid]
            changed += 1
    po.save(path)
    print(f"en: {changed} msgstr düzəldildi")


if __name__ == "__main__":
    main()
