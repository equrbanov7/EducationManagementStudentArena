"""``level-merge/1`` planı — köhnə sistemin BİR səviyyə jurnalı yeni sistemdə qruplar üzrə bir neçə jurnala bölünübsə,
tələbələri bir «ev» jurnalına qonaq kimi yığmaq üçün (``merge_level_journals``; sahib 2026-10-27).

Köhnə sistemdə «Xarici dildə … -1(intermediate)» jurnalı 2–7 qrupun YALNIZ həmin səviyyədəki tələbələrini bir
müəllimdə birləşdirirdi; yeni sistemdə hər qrupun öz səviyyə jurnalı var və eyni dərs 2–5 jurnalda təkrarlanır.

Qayda:

* yalnız səviyyə fənləri (:func:`apps.registrar.language_levels.level_of`), həll olunmuş müəllim + fənn;
* jurnalın tələbələri ≥2 açılışdadırsa — ev (host): müəllimin ÖZ (``instructor``) aktiv açılışlarından ən çox dərsi,
  sonra ən çox xanası, sonra ən çox həmin jurnal tələbəsi olan; bir açılış yalnız bir jurnalın evi ola bilər (böyük
  jurnallar əvvəl seçir); uyğun açılış yoxdursa — sayılır (``host_none_owned``: açılışların sahibi dərs yükünə görə
  BAŞQA müəllimdir, köhnə sistemin müəllimi paylarla işləyir — kafedra qərarı). ``host_via_share=True`` (əmrdə
  ``--host-via-share``) — belə jurnalda ev müəllimin PAYI olan açılışlardan seçilir (``"via": "share"``; tətbiqdə pay
  yoxlanılır və köçənlər həmin paya əlavə olunur);
* köçürülən: evdən kənar açılışlardakı həmin jurnal tələbələrinin qeydiyyatları; bir qeydiyyat iki jurnalın
  siyahısındadırsa — köçürülmür (``moves_ambiguous``).

Plan YALNIZ id-lərdir::

    {"format": "level-merge/1", "period": uuid, "journals": [{"legacy_journal": int, "teacher": int, "host": uuid,
      "via": "owner" | "share", "moves": [{"enrollment": uuid, "student": int}]}]}
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db.models import Count

FORMAT = "level-merge/1"


def _levels():
    from apps.registrar.public import language_levels

    return language_levels


class LevelMergePlan:
    def __init__(self, index, *, host_via_share: bool = False):
        self.index = index
        self.host_via_share = host_via_share
        self.counts: Counter = Counter()

    def build(self) -> dict:
        levels = _levels()
        journals = [entry for entry in self.index.resolved_journals() if levels.level_of(entry.subject_name)]
        self.counts["level_journals"] = len(journals)
        split = [entry for entry in journals if len(entry.hits) >= 2]
        self.counts["level_single_offering"] = sum(1 for entry in journals if len(entry.hits) == 1)
        self.counts["level_no_offering"] = sum(1 for entry in journals if not entry.hits)
        self.counts["level_split"] = len(split)
        claims = Counter(pk for entry in journals for ids in entry.hits.values() for pk in ids)
        weights = self._weights({offering for entry in split for offering in entry.hits})
        used: set = set()
        items = []
        # Öz açılışı olan jurnallar əvvəl (pay yolu onların evini «tutmasın»), sonra böyükdən kiçiyə.
        order = sorted(
            split,
            key=lambda entry: (
                not any(self._owned(entry, pk) for pk in entry.hits),
                -sum(len(ids) for ids in entry.hits.values()),
                entry.legacy_id,
            ),
        )
        for entry in order:
            host, via = self._host(entry, weights, used)
            if host is None:
                continue
            used.add(host)
            moves = []
            for offering_id in sorted(entry.hits, key=str):
                if offering_id == host:
                    continue
                for pk in sorted(entry.hits[offering_id], key=str):
                    if claims[pk] > 1:
                        self.counts["moves_ambiguous"] += 1
                        continue
                    moves.append({"enrollment": str(pk), "student": self.index.enrolled[pk]["student_id"]})
            if not moves:
                self.counts["host_nothing_to_move"] += 1
                continue
            self.counts["host_chosen"] += 1
            self.counts[f"host_via_{via}"] += 1
            self.counts["moves"] += len(moves)
            self.counts["source_offerings"] += len(entry.hits) - 1
            items.append(
                {
                    "legacy_journal": entry.legacy_id,
                    "teacher": entry.teacher_id,
                    "host": str(host),
                    "via": via,
                    "moves": moves,
                }
            )
        return {"format": FORMAT, "period": str(self.index.period.pk), "journals": items}

    def _weights(self, offering_ids) -> dict:
        Lesson = django_apps.get_model("registrar", "Lesson")
        LessonMark = django_apps.get_model("registrar", "LessonMark")
        ids = list(offering_ids)
        lessons = dict(
            Lesson.objects.filter(offering_id__in=ids)
            .values("offering_id")
            .annotate(n=Count("id"))
            .values_list("offering_id", "n")
        )
        marks = dict(
            LessonMark.objects.filter(lesson__offering_id__in=ids)
            .values("lesson__offering_id")
            .annotate(n=Count("id"))
            .values_list("lesson__offering_id", "n")
        )
        return {pk: (lessons.get(pk, 0), marks.get(pk, 0)) for pk in ids}

    def _owned(self, entry, offering_id) -> bool:
        offering = self.index.offerings.get(offering_id) or {}
        return bool(offering.get("is_active")) and offering.get("instructor_id") == entry.teacher_id

    def _host(self, entry, weights, used) -> tuple:
        active = [pk for pk in entry.hits if (self.index.offerings.get(pk) or {}).get("is_active")]
        candidates = [pk for pk in active if self._owned(entry, pk)]
        via = "owner"
        if not candidates:
            self.counts["host_none_owned"] += 1
            if not self.host_via_share:
                return None, ""
            # Müəllimin bu açılışlarda payı var (``journal-shares/1`` hər «sahib deyil» müəllimə pay yazır).
            candidates, via = active, "share"
        free = [offering_id for offering_id in candidates if offering_id not in used]
        if not free:
            self.counts["host_taken"] += 1
            return None, ""
        return max(free, key=lambda pk: (*weights.get(pk, (0, 0)), len(entry.hits[pk]), str(pk))), via


__all__ = ["FORMAT", "LevelMergePlan"]
