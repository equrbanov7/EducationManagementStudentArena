#!/usr/bin/env python3
"""
EMSArena i18n — fill empty catalog entries that leaked from third-party
libraries. Idempotent.

The project django.po files contain ~292 empty entries whose msgids are
ENGLISH strings from third-party libraries (Django core validators/forms,
Click CLI messages, Celery/qpid, Haystack, Django debug pages, plus the
"abbrev. month" / "alt. month" / truncation msgctxt entries) — picked up
by a makemessages run that scanned site-packages. Because empty entries
are dropped by msgfmt, runtime already falls back to Django's own bundled
catalogs, so nothing user-facing is broken; this fill just makes the
catalogs report 100% translated without changing behavior:

  * if the (msgctxt, msgid) pair exists, translated, in the installed
    Django's own catalogs (django/conf/locale first, then
    django/contrib/*/locale) for that language, copy Django's official
    msgstr (and plural forms — the Plural-Forms headers match);
  * otherwise fill msgstr = msgid, which is byte-identical to what the
    gettext fallback chain renders today.

IMPORTANT: do NOT blanket-fill az with msgid for these entries — the
msgids are English, and that would shadow Django's official Azerbaijani
translations of its validation messages.

The handful of genuinely project-specific empty entries
(msgctxt "accounts.first_login" / "brand" — empty only in az, where the
msgid IS the Azerbaijani source text — and the "ad.soyad@qku.edu.az"
e-mail placeholder, which stays literal in every locale) are correctly
covered by the msgstr = msgid rule.

Only entries whose msgstr (and every plural slot) is empty are touched.
Files are read/written with polib at the default wrap width, which
round-trips the existing files byte-identically, so the diff contains
only the filled lines. Location comments are absent (--no-location) and
are never introduced.
"""

import glob
import os
import re

import polib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = ["az", "en", "ru", "tr"]


def po_path(lang):
    return os.path.join(BASE, "locale", lang, "LC_MESSAGES", "django.po")


def django_catalog_paths(lang):
    """Django's own .po files for a language: conf/locale first (highest
    priority), then contrib app catalogs in sorted order."""
    import django

    root = os.path.dirname(os.path.abspath(django.__file__))
    paths = [os.path.join(root, "conf", "locale", lang, "LC_MESSAGES", "django.po")]
    paths += sorted(glob.glob(os.path.join(root, "contrib", "*", "locale", lang, "LC_MESSAGES", "django.po")))
    return [p for p in paths if os.path.isfile(p)]


def build_official_lookup(lang):
    """(msgctxt, msgid) -> polib entry from Django's bundled catalogs.
    First (highest-priority) catalog wins; fuzzy/empty entries skipped."""
    lookup = {}
    for path in django_catalog_paths(lang):
        for e in polib.pofile(path, wrapwidth=0):
            if e.obsolete or "fuzzy" in e.flags:
                continue
            if not (e.msgstr or any(e.msgstr_plural.values())):
                continue
            lookup.setdefault((e.msgctxt, e.msgid), e)
    return lookup


def nplurals_of(po):
    m = re.search(r"nplurals\s*=\s*(\d+)", po.metadata.get("Plural-Forms", ""))
    return int(m.group(1)) if m else 2


def is_empty(entry):
    if entry.msgid_plural:
        return not any(entry.msgstr_plural.values())
    return not entry.msgstr


def fill_entry(entry, official, nplurals):
    """Fill one empty entry. Returns 'official' or 'msgid' (source used)."""
    if entry.msgid_plural:
        if official is not None and official.msgid_plural and len(official.msgstr_plural) == nplurals:
            entry.msgstr_plural = dict(official.msgstr_plural)
            return "official"
        entry.msgstr_plural = {i: (entry.msgid if i == 0 else entry.msgid_plural) for i in range(nplurals)}
        return "msgid"
    if official is not None and not official.msgid_plural:
        entry.msgstr = official.msgstr
        return "official"
    entry.msgstr = entry.msgid
    return "msgid"


def run():
    report = []
    for lang in LOCALES:
        lookup = build_official_lookup(lang)
        po = polib.pofile(po_path(lang))  # default wrapwidth: matches file
        nplurals = nplurals_of(po)
        counts = {"official": 0, "msgid": 0}
        for entry in po:
            if entry.obsolete or not entry.msgid or not is_empty(entry):
                continue
            counts[fill_entry(entry, lookup.get((entry.msgctxt, entry.msgid)), nplurals)] += 1
        if sum(counts.values()):
            po.save()
        report.append("  %s: filled_from_django=%d filled_msgid=%d" % (lang, counts["official"], counts["msgid"]))
    return report


if __name__ == "__main__":
    for line in run():
        print(line)
    print("done")
