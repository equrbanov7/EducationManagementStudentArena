"""``Organization.settings`` — ATOMİK açar-səviyyəli yazı (lost update-in qarşısı, 2026-10-07).

Problem: ``settings`` JSON-unda bir-birindən asılı olmayan bir neçə yazıçı yaşayır
(elanların / sorğu qapısının sıfır-sorğulu xülasələri, modul görünürlüyü, hərf şkalası,
korpus xəritəsi, rəy anonimliyi …). Köhnə yol — təşkilatı əvvəlcədən yükləyib bütöv
dict-i Python-da dəyişmək və ``save(update_fields=["settings"])`` — arada başqa yolla
yazılmış açarları SƏSSİZCƏ əzirdi (məs. elan xülasəsi → popup/sayğac səhv qalırdı).

Burada üç qat var:

* :func:`set_settings_keys` — YALNIZ verilmiş üst-səviyyə açarları bir SQL ifadəsində
  birləşdirir (``(settings - silinənlər) || yenilər``); qalan açarlara toxunmur.
  Nüsxənin ``settings``-i DB-dən qayıdan TAM dəyərlə yenilənir.
* :func:`update_settings_key` — bir açarın İÇİNİ dəyişən (read-modify-write) yazıçılar
  üçün: sətir ``select_for_update`` ilə kilidlənir, açarın TƏZƏ dəyəri oxunur, dəyişdirilir
  və eyni tranzaksiyada yazılır (iç-içə lost update də olmur).
* :class:`ManagedSettingsSaveMixin` — ``Organization.save()`` (admin, formalar, köhnə kod)
  :func:`register_managed_settings_key` ilə qeydə alınmış TÖRƏMƏ açarları (xülasələr) HEÇ
  VAXT yaddaşdakı köhnə nüsxədən yazmır: yazıdan əvvəl kilidli sətirdən götürür. Bu
  açarların yeganə yazıçısı öz ``sync_*`` funksiyalarıdır.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable

from django.apps import apps as django_apps
from django.db import connections, router, transaction
from django.utils import timezone

#: ``mutate`` funksiyası bunu qaytarsa açar silinir.
REMOVE = object()
#: ``mutate`` funksiyası bunu qaytarsa heç nə yazılmır.
UNCHANGED = object()

_MANAGED_KEYS: set[str] = set()


def register_managed_settings_key(key: str) -> None:
    """Açarın yeganə yazıçısı öz atomik ``sync`` funksiyasıdır — ``save()`` ona toxunmasın."""
    _MANAGED_KEYS.add(str(key))


def managed_settings_keys() -> frozenset:
    return frozenset(_MANAGED_KEYS)


def _as_dict(value) -> dict:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _model():
    return django_apps.get_model("organizations", "Organization")


def _locked_settings(model, using, pk):
    """Sətri ``FOR UPDATE`` kilidləyir; ``(sətir var?, settings dict)`` (çağıran ``atomic`` içindədir)."""
    rows = list(
        model._base_manager.using(using).select_for_update().filter(pk=pk).values_list("settings", flat=True)[:1]
    )
    return bool(rows), (_as_dict(rows[0]) if rows else {})


def set_settings_keys(organization, updates: dict | None = None, remove: Iterable = (), *, touch: bool = True) -> dict:
    """Üst-səviyyə açarları ATOMİK birləşdirir; ``remove`` açarları silinir. Yeni ``settings`` qaytarılır.

    ``touch=False`` — ``updated_at`` dəyişmir (törəmə xülasələr üçün). Sətir DB-də yoxdursa
    (yadda saxlanmamış nüsxə) birləşmə yalnız yaddaşda olur — sonrakı ``save()`` onu yazır.
    """
    updates = {str(key): value for key, value in (updates or {}).items()}
    dropped = sorted({str(key) for key in remove} - set(updates))
    if not updates and not dropped:
        return _as_dict(organization.settings)
    Organization = _model()
    using = router.db_for_write(Organization, instance=organization)
    connection = connections[using]
    now = timezone.now()
    if connection.vendor == "postgresql":
        meta, quote = Organization._meta, connection.ops.quote_name
        column = quote(meta.get_field("settings").column)
        assignments = (
            f"{column} = (CASE WHEN jsonb_typeof({column}) = 'object' THEN {column} ELSE '{{}}'::jsonb END"
            " - %s::text[]) || %s::jsonb"
        )
        params = [dropped, json.dumps(updates)]
        if touch:
            assignments += f", {quote(meta.get_field('updated_at').column)} = %s"
            params.append(now)
        params.append(str(organization.pk))
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {quote(meta.db_table)} SET {assignments} "  # noqa: S608 — ad modeldən, dəyər parametr
                f"WHERE {quote(meta.pk.column)} = %s RETURNING {column}",
                params,
            )
            row = cursor.fetchone()
        fresh = _as_dict(row[0]) if row else None
    else:  # pragma: no cover — yalnız PostgreSQL olmayan lokal baza
        with transaction.atomic(using=using):
            exists, stored = _locked_settings(Organization, using, organization.pk)
            fresh = None
            if exists:
                fresh = {key: value for key, value in stored.items() if key not in dropped}
                fresh.update(updates)
                values = {"settings": fresh, **({"updated_at": now} if touch else {})}
                Organization._base_manager.using(using).filter(pk=organization.pk).update(**values)
    if fresh is None:
        fresh = {key: value for key, value in _as_dict(organization.settings).items() if key not in dropped}
        fresh.update(updates)
    elif touch:
        organization.updated_at = now
    organization.settings = fresh
    return fresh


def update_settings_key(organization, key: str, mutate: Callable, *, touch: bool = True) -> dict:
    """Açarın TƏZƏ dəyərini kilid altında oxuyur, ``mutate(dəyər)`` nəticəsini yazır.

    ``mutate`` dəyərin surətini alır (açar yoxdursa ``None``) və yeni dəyəri və ya
    :data:`REMOVE` / :data:`UNCHANGED` qaytarır. Paralel iki yazıçı eyni açarın FƏRQLİ alt-açarlarını
    dəyişsə, hər ikisinin dəyişikliyi qalır. Dəyər dəyişmirsə heç nə yazılmır
    (nüsxə yenə də DB-dəki təzə ``settings``-i alır).
    """
    Organization = _model()
    using = router.db_for_write(Organization, instance=organization)
    with transaction.atomic(using=using):
        exists, stored = _locked_settings(Organization, using, organization.pk)
        source = stored if exists else _as_dict(organization.settings)
        original = source.get(key)
        value = mutate(copy.deepcopy(original))
        if value is REMOVE:
            unchanged = key not in source
        else:
            unchanged = value is UNCHANGED or (key in source and value == original)
        if unchanged:
            organization.settings = source
            return source
        if value is REMOVE:
            return set_settings_keys(organization, remove=[key], touch=touch)
        return set_settings_keys(organization, {key: value}, touch=touch)


def _with_stored_managed_keys(current, stored) -> dict:
    merged, stored = _as_dict(current), _as_dict(stored)
    for key in _MANAGED_KEYS:
        if key in stored:
            merged[key] = stored[key]
        else:
            merged.pop(key, None)
    return merged


class ManagedSettingsSaveMixin:
    """``save()`` törəmə açarları köhnə nüsxədən yazmasın — kilidli sətirdəki dəyər qalır."""

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        writes_settings = update_fields is None or "settings" in update_fields
        if not writes_settings or not _MANAGED_KEYS or self._state.adding or self.pk is None:
            return super().save(*args, **kwargs)
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            exists, stored = _locked_settings(type(self), using, self.pk)
            if exists:
                self.settings = _with_stored_managed_keys(self.settings, stored)
            return super().save(*args, **kwargs)


__all__ = [
    "REMOVE",
    "UNCHANGED",
    "ManagedSettingsSaveMixin",
    "managed_settings_keys",
    "register_managed_settings_key",
    "set_settings_keys",
    "update_settings_key",
]
