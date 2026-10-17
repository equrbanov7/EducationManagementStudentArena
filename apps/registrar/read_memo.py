"""Request-ömürlü OXU memo-su: eyni toplu girişlər bir səhifədə bir dəfə oxunur (PERF-1 F-05/F-06, 2026-10-17).

PROBLEM
-------
Tələbənin «Fənlərim» bölməsi və jurnalın «Yekun» tabı eyni girişləri bir request-də 3–4 dəfə
qururdu: donma dəsti (sxem statusu + köçürmə möhürü), dərs saatı cəmi, idmançı istisnası,
tələbə həddi (``StudentAcademicRecord``), açılış həddi və komponent dəsti. Hər səth onları
öz açılış/tələbə dəsti ilə yenidən oxuyurdu (``services`` → ``analytics`` → ``cabinet_policy``
→ ``finals_batch``; jurnalda ``gradebook`` → ``finals`` → ``journal_extras``).

HƏLL
----
* :func:`scope` / :func:`scoped` / :func:`scoped_get` — memo YALNIZ açıq sahədə işləyir (contextvar;
  request bitəndə sıfırlanır). Sahə yoxdursa bəzənmiş funksiyalar əvvəlki kimi birbaşa sorğu edir —
  servis, POST, test, Celery yolları dəyişmir.
* :func:`per_id` — id kolleksiyası alan toplu funksiyanı id-başına memo-layır: yalnız hələ görülməmiş
  id-lər sorğuya gedir (məs. «Fənlərim»: cari dövr → bütün yazılışlar → digər dövrlər → hamısı;
  ikinci və sonrakı çağırışlar ya yalnız fərqi, ya heç nə oxumur). Nəticənin forması eynidir.
  Bu yalnız id-başına müstəqil nəticələr üçündür (donma, saat cəmi, istisna, həddi).
* :func:`per_key` — tək dəyərli funksiya (açılış həddi) üçün açar-başına memo.
* :func:`bucket` — xüsusi forma (komponent dəsti, ``finals_batch``) üçün xam yaddaş.

TƏZƏLİK
-------
GET yolunda yazı nadirdir, amma var: ``interim_components.ensure_kollokviums`` komponent yaradır /
silir, ``ensure_assessment_scheme`` sxem yaradır. Ona görə ``AssessmentComponent`` (save + delete),
``AssessmentScheme``, ``Lesson``, ``StudentAcademicRecord``, ``ComponentScore``, ``Enrollment`` (save) yazısı açıq sahəni TAM təmizləyir
(:func:`clear`; sahə yoxdursa heç nə etmir). ``Lesson``/sxem/qeyd üçün ``post_delete`` QƏSDƏN
qoşulmur — o, Django-nun toplu (fast) silməsini söndürərdi; GET yolunda onlar silinmir.
Memo request-in tək tenant kontekstindədir: id-lər həmin tenantın sətirləridir.
"""

from __future__ import annotations

import functools
import inspect
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models.signals import post_delete, post_save

_SCOPE: ContextVar = ContextVar("ems_registrar_read_memo", default=None)
_ABSENT = object()
_KEY_TYPES = (int, uuid.UUID)
_COLLECTIONS = (list, tuple, set, frozenset)


def active() -> bool:
    return _SCOPE.get() is not None


@contextmanager
def scope():
    """Memo sahəsi; iç-içə çağırış xarici sahəni işlədir (yenisini açmır)."""
    if _SCOPE.get() is not None:
        yield
        return
    token = _SCOPE.set({})
    try:
        yield
    finally:
        _SCOPE.reset(token)


def scoped(func):
    """Funksiyanın bütün çağırışı bir memo sahəsində (oxu səthi — məs. «Fənlərim» bölməsi)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with scope():
            return func(*args, **kwargs)

    return wrapper


def scoped_get(view):
    """View dekoratoru: yalnız GET/HEAD memo sahəsində; POST əvvəlki kimi (memo-suz)."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method not in ("GET", "HEAD"):
            return view(request, *args, **kwargs)
        with scope():
            return view(request, *args, **kwargs)

    return wrapper


def clear(*_args, **_kwargs) -> None:
    """Açıq sahəni təmizlə (siqnal qəbuledicisi kimi də işləyir)."""
    store = _SCOPE.get()
    if store is not None:
        store.clear()


def bucket(kind):
    """Açıq sahədə ``kind`` üçün xam lüğət; sahə yoxdursa ``None``."""
    store = _SCOPE.get()
    return None if store is None else store.setdefault(kind, {})


def plain_ids(values) -> list | None:
    """Memo-lana bilən id siyahısı (``None``-suz) — kolleksiya deyilsə / tip qarışıqdırsa ``None``."""
    if not isinstance(values, _COLLECTIONS):
        return None
    ids = [value for value in values if value is not None]
    if not all(isinstance(value, _KEY_TYPES) and not isinstance(value, bool) for value in ids):
        return None
    return ids


def per_id(kind, *, ids_arg, result, namespace_arg=None):
    """Toplu funksiyanı id-başına memo-la. ``result`` — ``"set"`` (frozenset qaytarır) və ya ``"dict"``.

    ``namespace_arg`` — nəticəni ayıran əlavə arqument (təşkilat; obyekt və ya pk). Sahə yoxdursa,
    giriş queryset-dirsə və ya id tipi qarışıqdırsa funksiya OLDUĞU KİMİ çağırılır."""

    def decorate(func):
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            store = _SCOPE.get()
            if store is None:
                return func(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            ids = plain_ids(bound.arguments.get(ids_arg))
            namespace = None
            if namespace_arg is not None:
                raw = bound.arguments.get(namespace_arg)
                namespace = getattr(raw, "pk", raw)
            if not ids or (namespace_arg is not None and namespace is None):
                return func(*args, **kwargs)
            memo = store.setdefault((kind, namespace), {})
            missing = [value for value in dict.fromkeys(ids) if value not in memo]
            if missing:
                bound.arguments[ids_arg] = missing
                fresh = func(*bound.args, **bound.kwargs)
                for value in missing:
                    memo[value] = (value in fresh) if result == "set" else fresh.get(value, _ABSENT)
            if result == "set":
                return frozenset(value for value in ids if memo[value])
            return {value: memo[value] for value in ids if memo[value] is not _ABSENT}

        return wrapper

    return decorate


def per_key(kind, key):
    """Tək dəyərli funksiyanı ``key(*args, **kwargs)`` açarı ilə memo-la (açar ``None`` → birbaşa çağırış)."""

    def decorate(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            store = _SCOPE.get()
            memo_key = key(*args, **kwargs) if store is not None else None
            if memo_key is None:
                return func(*args, **kwargs)
            memo = store.setdefault((kind, None), {})
            if memo_key not in memo:
                memo[memo_key] = func(*args, **kwargs)
            return memo[memo_key]

        return wrapper

    return decorate


def enrolled_roster(offering) -> list:
    """Açılışın ``ENROLLED`` yazılışları (soyad, login sırası) — jurnalın bütün tabları üçün TƏK forma.

    Əvvəl qrid, kurs işi, «Yekun» nəticələri, yekun bölgü, sərbəst iş lövhəsi və aralıq qiymətləndirmə
    eyni sorğunu ayrı-ayrı atırdı (fərq yalnız ``select_related``-də idi; burada hamısının birləşməsi).
    Açıq sahədə açılış başına bir dəfə; hər çağırış öz siyahı NÜSXƏSİNİ alır."""
    from apps.registrar.models import Enrollment

    memo = bucket("roster")
    if memo is not None and offering.pk in memo:
        return list(memo[offering.pk])
    rows = list(
        offering.enrollments.filter(status=Enrollment.Status.ENROLLED)
        .select_related("student", "student__profile", "source_group")
        .order_by("student__last_name", "student__username")
    )
    if memo is not None:
        memo[offering.pk] = rows
    return list(rows)


_SAVE_SENDERS = (
    "registrar.AssessmentComponent",
    "registrar.AssessmentScheme",
    "registrar.Lesson",
    "registrar.StudentAcademicRecord",
    "registrar.ComponentScore",
    "registrar.Enrollment",
)
for _model in _SAVE_SENDERS:
    post_save.connect(clear, sender=_model, dispatch_uid=f"registrar_read_memo_save_{_model}")
post_delete.connect(clear, sender="registrar.AssessmentComponent", dispatch_uid="registrar_read_memo_del_comp")


__all__ = [
    "active",
    "bucket",
    "clear",
    "enrolled_roster",
    "per_id",
    "per_key",
    "plain_ids",
    "scope",
    "scoped",
    "scoped_get",
]
