"""Bir sahənin sətirlərini bir hesabdan digərinə keçirmək — unikal toqquşma yoxlaması və DB qoruyucusu ehtiyatı.

* :func:`colliding_ids` — sahə unikal məhdudiyyətin içindədirsə, hədəfdə EYNİ açarlı (şərti məhdudiyyətdə şərtə
  uyan) sətri olan mənbə sətirləri. Açarda ``NULL`` varsa toqquşma yoxdur (Postgres ``NULLS DISTINCT``).
* :func:`move` — id-lər 1000-lik hissələrlə, hər hissə öz savepoint-ində yenilənir; DB trigger-i (append-only,
  saat balansı və s.) hissəni rədd edərsə sətirlər TƏK-TƏK yoxlanır — rədd olunan sətir yerində qalır və sayılır
  (``blocked_<sahə>``), heç nə silinmir.
"""

from __future__ import annotations

from django.db import DatabaseError, transaction

CHUNK = 1000


def _chunks(items, size=CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def source_ids(relation, user_id) -> list:
    return list(relation.model._base_manager.filter(**{relation.attname: user_id}).values_list("pk", flat=True))


def colliding_ids(relation, source_id, target_id) -> set:
    base, field, found = relation.model._base_manager, relation.attname, set()
    for others, condition in relation.unique_keys():
        source_rows = base.filter(**{field: source_id})
        target_rows = base.filter(**{field: target_id})
        if condition is not None:
            source_rows, target_rows = source_rows.filter(condition), target_rows.filter(condition)
        names = list(others)
        taken = {tuple(row[1:]) for row in target_rows.values_list("pk", *names)}
        if not taken:
            continue
        for row in source_rows.values_list("pk", *names):
            values = tuple(row[1:])
            if any(value is None for value in values):
                continue
            if values in taken:
                found.add(row[0])
    return found


def _update(relation, pks, from_id, to_id) -> int:
    return relation.model._base_manager.filter(pk__in=pks, **{relation.attname: from_id}).update(
        **{relation.attname: to_id}
    )


def move(relation, ids, from_id, to_id) -> tuple:
    """``ids`` sətirlərini ``from_id`` → ``to_id``. Qaytarır: (keçən id-lər, DB-nin rədd etdiyi id-lər)."""
    moved, failed = [], []
    for chunk in _chunks(list(ids)):
        try:
            with transaction.atomic():
                _update(relation, chunk, from_id, to_id)
            moved.extend(chunk)
            continue
        except DatabaseError:
            pass
        for pk in chunk:
            try:
                with transaction.atomic():
                    _update(relation, [pk], from_id, to_id)
                moved.append(pk)
            except DatabaseError:
                failed.append(pk)
    return moved, failed


__all__ = ["CHUNK", "colliding_ids", "move", "source_ids"]
