#!/usr/bin/env python3
"""EMSArena i18n — 2026-10-05: «Sistem Monitorinqi» → «Təhlükəsizlik» tabının IP filtri (sahib).

Əlavə olunan mətnlər (hamısı `django.po`-dadır; `djangojs` kataloquna yeni mətn YOXDUR):
  * `monitoring.ui`       — JS mətn adası (`_system_monitoring_i18n.html`, JS `t()`/`fmt()`):
                            IP sahəsi, «Bu IP-dən uğurlu girişlər» bloku, boş vəziyyətlər;
                            yer tutucular `{name}` formasındadır — `%` işlədilmir;
  * `monitoring.security` — API-nin 400 mesajları (`apps/monitoring/security_ip.py`).

⚠️ `makemessages` İŞLƏDİLMİR. İdempotentdir; sonra `.mo` faylları yenidən qurulur.
İstifadə:  python scripts/i18n_fill_2026_10_05_security_ip.py
"""

import os
import subprocess

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("az", "en", "ru", "tr")

UI = "monitoring.ui"
SEC = "monitoring.security"

# (kontekst, az, en, ru, tr)
ROWS = [
    # ── monitoring.ui ─────────────────────────────────────────────────────
    (UI, "IP ünvanı və ya şəbəkə", "IP address or network", "IP-адрес или сеть", "IP adresi veya ağ"),
    (UI, "IP və ya şəbəkə, məs. 5.191.0.0/16", "IP or network, e.g. 5.191.0.0/16",
     "IP или сеть, напр. 5.191.0.0/16", "IP veya ağ, örn. 5.191.0.0/16"),
    (UI, "IP filtrini təmizlə", "Clear the IP filter", "Сбросить фильтр по IP", "IP filtresini temizle"),
    (UI, "Yalnız bu IP: {ip}", "Only this IP: {ip}", "Только этот IP: {ip}", "Yalnızca bu IP: {ip}"),
    (UI, "Bu IP-dən uğurlu girişlər", "Successful logins from this IP", "Успешные входы с этого IP",
     "Bu IP'den başarılı girişler"),
    (UI, "Bu şəbəkədən uğurlu girişlər", "Successful logins from this network", "Успешные входы из этой сети",
     "Bu ağdan başarılı girişler"),
    (UI, "Bu IP-dən uğurlu giriş yoxdur", "No successful logins from this IP", "С этого IP успешных входов нет",
     "Bu IP'den başarılı giriş yok"),
    (UI, "Bu şəbəkədən uğurlu giriş yoxdur", "No successful logins from this network",
     "Из этой сети успешных входов нет", "Bu ağdan başarılı giriş yok"),
    (UI, "Girişlər: {logins} · Hesablar: {accounts}", "Logins: {logins} · Accounts: {accounts}",
     "Входов: {logins} · Аккаунтов: {accounts}", "Giriş: {logins} · Hesap: {accounts}"),
    (UI, "Ən son {limit} qeyd göstərilir (hesab və cihaz üzrə qruplaşdırılıb).",
     "Showing the latest {limit} entries (grouped by account and device).",
     "Показаны последние {limit} записей (сгруппированы по аккаунту и устройству).",
     "Son {limit} kayıt gösteriliyor (hesap ve cihaza göre gruplandı)."),
    (UI, "Yalnız təşkilatınızın üzvlərinin girişləri göstərilir.",
     "Only logins of your organisation's members are shown.",
     "Показаны только входы участников вашей организации.",
     "Yalnızca kuruluşunuzun üyelerinin girişleri gösteriliyor."),
    (UI, "Son giriş", "Last login", "Последний вход", "En son giriş"),
    (UI, "Cihaz / brauzer", "Device / browser", "Устройство / браузер", "Cihaz / tarayıcı"),
    (UI, "ilk: {time}", "first: {time}", "первый: {time}", "ilk kez: {time}"),
    (UI, "Bu IP üzrə təhlükəsizlik hadisəsi yoxdur", "No security events for this IP",
     "Для этого IP нет событий безопасности", "Bu IP için güvenlik olayı yok"),
    # ── monitoring.security ───────────────────────────────────────────────
    (SEC, "IP ünvanı düzgün deyil. Tək IP (məs. 192.168.1.10) və ya şəbəkə (məs. 10.0.0.0/24) daxil edin.",
     "The IP address is not valid. Enter a single IP (e.g. 192.168.1.10) or a network (e.g. 10.0.0.0/24).",
     "Неверный IP-адрес. Введите один IP (например, 192.168.1.10) или сеть (например, 10.0.0.0/24).",
     "IP adresi geçerli değil. Tek bir IP (örn. 192.168.1.10) veya ağ (örn. 10.0.0.0/24) girin."),
    (SEC, "Şəbəkə (CIDR) filtri bu bazada dəstəklənmir — tək IP ünvanı daxil edin.",
     "Network (CIDR) filtering is not supported by this database — enter a single IP address.",
     "Фильтр по сети (CIDR) не поддерживается этой базой данных — введите один IP-адрес.",
     "Ağ (CIDR) filtresi bu veritabanında desteklenmiyor — tek bir IP adresi girin."),
]  # fmt: skip

# ctx → msgid → {az, en, ru, tr}
ENTRIES: dict = {}
for ctx, az, en, ru, tr in ROWS:
    ENTRIES.setdefault(ctx, {})[az] = {"az": az, "en": en, "ru": ru, "tr": tr}

FORCE = set()


def fill(lang):
    path = os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")
    po = polib.pofile(path)
    index = {(e.msgctxt or "", e.msgid): e for e in po}
    added = changed = 0
    for ctx, items in ENTRIES.items():
        for msgid, values in items.items():
            want = values[lang]
            entry = index.get((ctx, msgid))
            if entry is None:
                entry = polib.POEntry(msgctxt=ctx or None, msgid=msgid, msgstr=want)
                po.append(entry)
                index[(ctx, msgid)] = entry
                added += 1
                continue
            stale = not entry.msgstr or "fuzzy" in entry.flags or entry.obsolete
            if ((ctx, msgid) in FORCE or stale) and entry.msgstr != want:
                entry.msgstr = want
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                entry.obsolete = False
                changed += 1
    if added or changed:
        po.save(path)
        subprocess.check_call(["msgfmt", "-o", path[:-3] + ".mo", path])
    print(f"{lang}: +{added} yeni, {changed} düzəliş")


def main():
    for lang in LANGS:
        fill(lang)


if __name__ == "__main__":
    main()
