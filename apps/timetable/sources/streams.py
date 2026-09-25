"""Mühazirə AXINLARI (potok) — bir neçə qrupun birgə mühazirəsi = BİR hadisə.

Mənbələr (``StreamPolicy``):

* ``task_rows`` (defolt) — kafedra tapşırığının bir sətrində birləşmiş qruplar
  («236 K / 234 İ», ``union_count == 1``) + alt qrup ailələri (birləşik qrup ilə
  alt qrupların eyni fənni; virtual ailədə yalnız EYNİ müəllim olduqda);
* ``same_teacher`` — eyni fənn + eyni mühazirəçi + eyni dil sektoru + eyni pillə;
* ``none`` — axın yoxdur (ailə birləşməsi struktur olduğu üçün yenə tətbiq olunur).

Birləşmə yalnız müəllimlər UYĞUN olduqda (boş olmayan mühazirəçi ən çox bir nəfər)
baş verir — «eyni fənn, eyni müəllim» avtomatik axın demək DEYİL (az/ing qrupları
fərqli dildədir; klonda 234 K az və 234 K ing ayrı-ayrı günlərdədir).
"""

from __future__ import annotations

from ..constants import KIND_LECTURE, StreamPolicy


class _Union:
    """Union-find; komponentin boş olmayan mühazirəçiləri izlənir (keçişli birləşmə
    iki FƏRQLİ müəllimi bir axına salmasın)."""

    def __init__(self, units):
        self.parent = {unit.offering_id: unit.offering_id for unit in units}
        self.teachers = {unit.offering_id: {unit.teachers.get(KIND_LECTURE)} - {None} for unit in units}

    def find(self, key):
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != root:
            self.parent[key], key = root, self.parent[key]
        return root

    def union(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        merged = self.teachers[ra] | self.teachers[rb]
        if len(merged) > 1:
            return False
        if rb < ra:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.teachers[ra] = merged
        return True


def _compatible(units) -> bool:
    teachers = {unit.teachers.get(KIND_LECTURE) for unit in units if unit.teachers.get(KIND_LECTURE)}
    return len(teachers) <= 1


def _same_teacher(units) -> bool:
    teachers = {unit.teachers.get(KIND_LECTURE) for unit in units}
    return len(teachers) == 1 and None not in teachers


def lecture_streams(units, infos, policy) -> list:
    """Mühazirə saatı olan vahidləri axınlara böl → ``[[CourseUnit, …], …]`` (deterministik)."""
    lectures = [unit for unit in units if unit.hours.get(KIND_LECTURE)]
    by_id = {unit.offering_id: unit for unit in lectures}
    union = _Union(sorted(lectures, key=lambda unit: unit.offering_id))

    def merge(bucket, *, strict=False):
        bucket = sorted(bucket, key=lambda unit: unit.offering_id)
        if len(bucket) < 2:
            return
        if not (_same_teacher(bucket) if strict else _compatible(bucket)):
            return
        for unit in bucket[1:]:
            union.union(bucket[0].offering_id, unit.offering_id)

    buckets: dict = {}
    for unit in lectures:
        info = infos[unit.group_id]
        if info.family:
            buckets.setdefault(("family", info.family, unit.subject_id), []).append(unit)
    for (_kind, family, _subject), bucket in sorted(buckets.items()):
        merge(bucket, strict=family.startswith("v:"))

    if policy == StreamPolicy.TASK_ROWS:
        rows: dict = {}
        for unit in lectures:
            if unit.row_id and len(unit.row_groups) > 1 and unit.union_count < len(unit.row_groups):
                rows.setdefault((unit.row_id, unit.union_count), []).append(unit)
        for (_row, union_count), bucket in sorted(rows.items()):
            if union_count <= 1:
                merge(bucket)
    elif policy == StreamPolicy.SAME_TEACHER:
        keys: dict = {}
        for unit in lectures:
            teacher = unit.teachers.get(KIND_LECTURE)
            if not teacher:
                continue
            info = infos[unit.group_id]
            keys.setdefault((unit.subject_id, teacher, info.sector, info.degree), []).append(unit)
        for _key, bucket in sorted(keys.items(), key=lambda item: str(item[0])):
            merge(bucket, strict=True)

    groups: dict = {}
    for offering_id in sorted(by_id):
        groups.setdefault(union.find(offering_id), []).append(by_id[offering_id])
    return [groups[root] for root in sorted(groups)]


__all__ = ["lecture_streams"]
