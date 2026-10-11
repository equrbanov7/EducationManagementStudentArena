"""Yük sənədinin sətrini mövcud ``TeachingTaskRow``-a tutuşdurma (sahib 2026-10-12).

Oktyabr kitabçası sentyabrda idxal olunmuş sətirlərin xana mətnini bir az dəyişə bilər
(«+», qalın şrift, boşluq) — yalnız xam mətnlə tutuşdurma dublikat yaradardı. Açarlar
(ardıcıl yoxlanılır, hər DB sətri bir dəfə istifadə olunur):

1. ``raw``      — (semestr, fənn xanası, qrup xanası) — xam mətn (köhnə idxal açarı);
2. ``subject``  — (semestr, həll olunmuş fənn, qrup adlarının normal açarları);
3. ``units``    — (semestr, həll olunmuş fənn, qrup vahidlərinin id-ləri);
4. ``text``     — (semestr, fənn xanasının slug-ı — «+»/boşluq/şrift fərqsiz, qrup açarları).

Fənn uyğunluğu: DB sətrinin fənni boşdursa və ya eynidirsə uyğundur. Xam/slug açarı
tutub fənn FƏRQLİDİRSƏ (bənd seçimi dəyişib) sətir yaradılmır — ``subject_changed``.
Heç bir açar tutmursa, amma eyni semestr + eyni fənn (və ya eyni xana mətni) ilə qrupları
KƏSİŞƏN istifadə olunmamış sətir varsa — ``groups_changed`` (qrup tərkibi dəyişib; sətir
yaradılmır, mövcud sətir toxunulmaz qalır, hesabatda əl ilə düzəliş üçün).
"""

from __future__ import annotations

from .task_workbook_parsing import _key, slug_name, split_tokens

NEW = "new"
SUBJECT_CHANGED = "subject_changed"
GROUPS_CHANGED = "groups_changed"


def groups_key(text: str) -> frozenset:
    tokens = split_tokens(text)
    return frozenset(_key(token) for token in tokens) if tokens else frozenset({_key(text)})


def _subject_key(subject):
    if subject is None:
        return None
    return subject.pk if subject.pk else ("new", slug_name(subject.name))


class RowMatcher:
    def __init__(self, rows):
        self.rows = list(rows)
        self.used: set = set()
        self.index: dict = {}
        for row in self.rows:
            unit_ids = frozenset(row.groups.values_list("pk", flat=True))
            gkey = groups_key(row.groups_text)
            self._add(("raw", row.season, row.subject_text, row.groups_text), row)
            self._add(("text", row.season, slug_name(row.subject_text), gkey), row)
            if row.subject_id:
                self._add(("subject", row.season, row.subject_id, gkey), row)
                if unit_ids:
                    self._add(("units", row.season, row.subject_id, unit_ids), row)

    def _add(self, key, row):
        self.index.setdefault(key, []).append(row)

    def match(self, *, season, subject_text, groups_text, subject=None, group_ids=()) -> tuple:
        """→ ``(sətir|None, açar|"new"|"subject_changed")``."""
        subject_key = _subject_key(subject)
        gkey = groups_key(groups_text)
        keys = [("raw", ("raw", season, subject_text[:255], groups_text[:255]))]
        if subject_key is not None and not isinstance(subject_key, tuple):
            keys.append(("subject", ("subject", season, subject_key, gkey)))
            if group_ids:
                keys.append(("units", ("units", season, subject_key, frozenset(group_ids))))
        keys.append(("text", ("text", season, slug_name(subject_text), gkey)))
        conflict = None
        for how, key in keys:
            candidates = [row for row in self.index.get(key, []) if row.pk not in self.used]
            compatible = [row for row in candidates if subject_key is None or row.subject_id in (None, subject_key)]
            exact = [row for row in compatible if subject_key is not None and row.subject_id == subject_key]
            chosen = (exact or compatible or [None])[0]
            if chosen is not None:
                self.used.add(chosen.pk)
                return chosen, how
            if candidates and conflict is None:
                conflict = candidates[0]
        if conflict is not None:
            return conflict, SUBJECT_CHANGED
        overlap = self._overlapping(season, subject_key, slug_name(subject_text), gkey)
        if overlap is not None:
            self.used.add(overlap.pk)
            return overlap, GROUPS_CHANGED
        return None, NEW

    def _overlapping(self, season, subject_key, text_slug, gkey):
        for row in self.rows:
            if row.pk in self.used or row.season != season or not (groups_key(row.groups_text) & gkey):
                continue
            same_subject = subject_key is not None and row.subject_id == subject_key
            if same_subject or slug_name(row.subject_text) == text_slug:
                return row
        return None

    def unmatched(self) -> list:
        return [row for row in self.rows if row.pk not in self.used]


__all__ = ["GROUPS_CHANGED", "NEW", "SUBJECT_CHANGED", "RowMatcher", "groups_key"]
