"""Bildiriş mətnlərinin OXUYANIN dilində göstərilməsi (sahib 2026-10-25).

Problem: bildirişin başlığı/mətni yaradılan anda HAZIR mətn kimi (``gettext`` nəticəsi) saxlanırdı — yəni
hadisəni tetikləyən sorğunun dilində. Aktivləşdirən tələbə rus/türk/ingilis interfeysdə idisə, RİM işçisinin
(AZ interfeysli) siyahısında eyni növ bildirişlər müxtəlif dillərdə görünürdü. Sistemdə istifadəçiyə bağlı dil
sahəsi YOXDUR (dil brauzer kukisi/sessiyadır), ona görə düzgün həll yaradılma anında alıcı dilinə yox,
GÖSTƏRMƏ anında oxuyanın cari dilinə render etməkdir.

Necə işləyir:

* Yaradılma (``crud.create_notification*``): mətn (``str`` və ya :class:`LText`) üçün «deskriptor» çıxarılır —
  kataloq açarı (kontekst + msgid) + parametrlər — və ``metadata["i18n"]``-də saxlanır. ``str`` ilə verilən ``title`` /
  ``message`` sütunları OLDUĞU KİMİ qalır; açıq :class:`LText` isə sütuna kanonik dildə (az) yazılır. Deskriptor əlavədir.
  ``str`` üçün deskriptor kataloqun TERS axtarışı ilə tapılır (:func:`describe`) — beləliklə 45 modulda olan
  184 ``create_notification*`` çağırışının heç biri dəyişmədən düzəlir. Mürəkkəb (bir neçə hissədən yığılan)
  mətnlər açıq :class:`LText` / :func:`lformat` ilə verilir.
* Göstərmə (:func:`localize_notification`): deskriptor varsa mətn oxuyanın aktiv dilində yenidən qurulur;
  yoxdursa (tanınmayan/ istifadəçi mətni) saxlanan mətn göstərilir. Obyekt DB-yə YAZILMIR.
* Köhnə sətirlər: ``manage.py backfill_notification_i18n`` (defolt dry-run) eyni ters axtarışla deskriptor əlavə edir.

Deskriptor (JSON): sadə ``{"m": msgid, "c": kontekst, "p": {param: dəyər}, "l": mənbə dili}``; mürəkkəb
``{"t": "{0}. {1}", "a": [deskriptor | sətir, …]}``.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from functools import lru_cache

from django.conf import settings
from django.utils import translation
from django.utils.functional import Promise
from django.utils.translation import gettext, pgettext, trans_real

logger = logging.getLogger(__name__)

META_KEY = "i18n"
_SEP = "\x04"  # gettext kontekst ayırıcısı: «kontekst\x04msgid»

_PCT_RE = re.compile(r"%\((\w+)\)([sd])|%%")
_BRACE_RE = re.compile(r"\{(\w+)\}")
#: Ters axtarışda «yalnız yer tutucu» şablonların (məs. ``{a}: {b}``) hər mətnə uyğun gəlməsinin qarşısı.
_MIN_LITERAL_LETTERS = 3
#: Yer tutuculu şablonun uyğunluğu «etibarlı» sayılması üçün: sabit hissədə ən azı bu qədər hərf VƏ YA sabit hissə
#: mətnin yarısı. Əks halda «Salam, %(name)s» kimi qısa şablon istifadəçinin sərbəst cümləsinə «uyğun gəlir».
_TRUSTED_LETTERS = 8
_TRUSTED_SHARE = 0.5
_MAX_PARAM_VALUE_LEN = 80
#: Sütun uzunluqları (``InAppNotification.title`` 255); mesaj üçün köhnə çağırışların 2000 limiti saxlanıb.
_LIMITS = {"title": 255, "message": 2000, "link_label": 255}


# ───────────────────────────── şablon təhlili ─────────────────────────────


class _Template:
    """Kataloq şablonu: ``plain`` (yer tutucusuz) və ya ``pct`` / ``brace`` + ters axtarış regex-i."""

    __slots__ = ("kind", "regex", "groups", "literal_len", "prefix", "letters")

    def __init__(self, kind, regex=None, groups=None, literal_len=0, prefix="", letters=0):
        self.kind = kind
        self.letters = letters
        self.regex = regex
        self.groups = groups or {}
        self.literal_len = literal_len
        self.prefix = prefix


@lru_cache(maxsize=None)
def _parse(template: str) -> _Template | None:
    """``None`` — dəstəklənməyən şablon (mövqe ``%s``, ``{{``, format spesifikasiyası və s.)."""
    if "%(" in template:
        kind, pattern = "pct", _PCT_RE
        if template.count("%") != sum(1 for _ in re.finditer(r"%\(\w+\)[sd]", template)) + 2 * template.count("%%"):
            return None
    elif "{" in template or "}" in template:
        kind, pattern = "brace", _BRACE_RE
        if "{{" in template or "}}" in template:
            return None
    else:
        return _Template("plain", literal_len=len(template))

    pieces, groups, seen, literal, pos = [], {}, {}, [], 0
    for match in pattern.finditer(template):
        lit = template[pos : match.start()]
        pieces.append(re.escape(lit))
        literal.append(lit)
        pos = match.end()
        if kind == "pct" and match.group(0) == "%%":
            pieces.append("%")
            literal.append("%")
            continue
        name = match.group(1)
        vtype = match.group(2) if kind == "pct" else "s"
        if name in seen:
            pieces.append(f"(?P={seen[name]})")
            continue
        group = f"g{len(seen)}"
        seen[name] = group
        groups[group] = (name, vtype)
        pieces.append(r"(?P<%s>-?\d+)" % group if vtype == "d" else f"(?P<{group}>.*?)")
    tail = template[pos:]
    if kind == "brace" and ("{" in tail or "}" in tail):
        return None
    pieces.append(re.escape(tail))
    literal.append(tail)
    if not groups:
        return _Template("plain", literal_len=len(template))
    text = "".join(literal)
    if sum(1 for ch in text if ch.isalpha()) < _MIN_LITERAL_LETTERS:
        return None
    prefix = literal[0] if literal else ""
    letters = sum(1 for ch in text if ch.isalpha())
    return _Template(kind, re.compile("".join(pieces), re.DOTALL), groups, len(text), prefix, letters)


def _apply(template: str, params: dict) -> str | None:
    """Şablona parametrləri yazır (çağırış yerlərindəki ``%`` / ``.format`` ilə eyni)."""
    try:
        if not params:
            return template
        if "%(" in template:
            return template % params
        if "{" in template:
            return template.format(**params)
        return template
    except (KeyError, IndexError, ValueError, TypeError):
        return None


# ───────────────────────────── kataloq indeksi ─────────────────────────────


def _codes() -> list[str]:
    return [code for code, _name in settings.LANGUAGES]


def _catalog(lang: str):
    try:
        return trans_real.translation(lang)._catalog
    except Exception:  # noqa: BLE001 — kataloq oxunmasa indeks boş qalır, bildiriş yenə yaranır
        logger.warning("Notification i18n: catalog for %r unreadable.", lang, exc_info=True)
        return {}


def _split_key(key: str) -> tuple[str, str]:
    context, sep, msgid = key.partition(_SEP)
    return (context, msgid) if sep else ("", key)


@lru_cache(maxsize=None)
def _universe():
    """Bütün dillərin kataloqlarındakı açarların birləşməsi (``{lang: kataloq}``, açarlar dəsti)."""
    catalogs = {code: _catalog(code) for code in _codes()}
    keys: set = set()
    for catalog in catalogs.values():
        keys.update(key for key in catalog.keys() if isinstance(key, str) and key)
    return catalogs, keys


@lru_cache(maxsize=None)
def _index(lang: str):
    """``(exact, patterns)``: yer tutucusuz mətn → açarlar; yer tutuculu şablonlar (spesifiklik sırası ilə)."""
    catalogs, universe = _universe()
    own = catalogs.get(lang) or {}
    exact: dict = defaultdict(list)
    patterns: list = []
    for key in universe:
        _context, msgid = _split_key(key)
        template = own.get(key) or msgid
        parsed = _parse(template)
        if parsed is None:
            continue
        if parsed.kind == "plain":
            if len(template) >= 2:
                exact[template].append(key)
        else:
            patterns.append((parsed.literal_len, parsed, key))
    patterns.sort(key=lambda item: -item[0])
    return dict(exact), patterns


def _render_key(key: str, params: dict, lang: str) -> str | None:
    context, msgid = _split_key(key)
    with translation.override(lang):
        template = pgettext(context, msgid) if context else gettext(msgid)
    return _apply(template, params)


def _typed(parsed: _Template, match) -> dict:
    values = {}
    for group, (name, vtype) in parsed.groups.items():
        raw = match.group(group)
        values[name] = int(raw) if vtype == "d" else raw
    return values


@lru_cache(maxsize=4096)
def _match(lang: str, text: str):
    """Ən spesifik uyğunluq: ``(açar, parametrlər-tuple)`` və ya ``None`` (uyğunsuz / qeyri-müəyyən)."""
    exact, patterns = _index(lang)
    best_len, found = -1, []
    for key in exact.get(text, ()):
        found.append((len(text), key, ()))
        best_len = len(text)
    for literal_len, parsed, key in patterns:
        if literal_len < best_len:
            break
        if parsed.prefix and not text.startswith(parsed.prefix):
            continue
        match = parsed.regex.fullmatch(text)
        if match is None:
            continue
        if parsed.letters < _TRUSTED_LETTERS and literal_len < len(text) * _TRUSTED_SHARE:
            continue
        found.append((literal_len, key, tuple(sorted(_typed(parsed, match).items()))))
        best_len = max(best_len, literal_len)
    top = {(key, params) for literal_len, key, params in found if literal_len == best_len}
    if not top:
        return None
    if len(top) > 1:
        # Eyni spesifiklikdə bir neçə açar: yalnız bütün dillərdə EYNİ nəticə verirlərsə təhlükəsizdir.
        renders = {tuple(_render_key(key, dict(params), code) for code in _codes()) for key, params in top}
        if len(renders) > 1:
            return None
    return sorted(top)[0]


def all_languages() -> list[str]:
    """Kanonik dil birinci, sonra qalanlar — mənbə dili bilinməyən mətn üçün."""
    return list(dict.fromkeys([settings.LANGUAGE_CODE, *_codes()]))


def describe(text, *, languages=None) -> dict | None:
    """Hazır mətnin deskriptoru (kataloqun ters axtarışı) və ya ``None``.

    ``languages`` — mətnin render olunmuş ola biləcəyi dillər (sıra ilə); defolt: aktiv dil, sonra kanonik dil
    (az). Dili bilinməyən köhnə sətirlər üçün (backfill) :func:`all_languages` verilir.
    Heç vaxt istisna atmır — bildiriş yaradılması bundan asılı olmamalıdır.
    """
    if not isinstance(text, str) or len(text) < 2:
        return None
    try:
        active = translation.get_language() or settings.LANGUAGE_CODE
        order = list(languages) if languages else list(dict.fromkeys([active, settings.LANGUAGE_CODE]))
        for lang in order:
            hit = _match(lang, text)
            if hit is None:
                continue
            key, params = hit
            context, msgid = _split_key(key)
            descriptor = {"m": msgid, "l": lang}
            if context:
                descriptor["c"] = context
            if params:
                descriptor["p"] = {name: value for name, value in params}
            # Dövr yoxlaması: deskriptor mənbə dilində ƏSLİ mətni verməlidir.
            if render(descriptor, lang) != text:
                continue
            return descriptor
    except Exception:  # noqa: BLE001
        logger.debug("Notification i18n: describe failed.", exc_info=True)
    return None


# ───────────────────────────── render ─────────────────────────────


def _localize_value(value, source: str | None, lang: str):
    """Parametr dəyəri kataloq mətnidirsə (məs. rol etiketi «Tələbə») hədəf dilə çevrilir; ad/rəqəm olduğu kimi."""
    if not source or source == lang or not isinstance(value, str) or not (3 <= len(value) <= _MAX_PARAM_VALUE_LEN):
        return value
    keys = _index(source)[0].get(value)
    if not keys:
        return value
    renders = {_render_key(key, {}, lang) for key in keys}
    return renders.pop() if len(renders) == 1 else value


def render(descriptor, language=None) -> str | None:
    """Deskriptoru ``language`` (defolt: aktiv dil) dilində mətnə çevirir; alınmasa ``None``."""
    if not isinstance(descriptor, dict):
        return None
    lang = language or translation.get_language() or settings.LANGUAGE_CODE
    try:
        if "t" in descriptor:
            args = [render(part, lang) if isinstance(part, dict) else str(part) for part in descriptor.get("a") or []]
            if any(arg is None for arg in args):
                return None
            return str(descriptor["t"]).format(*args)
        msgid = descriptor["m"]
        context = descriptor.get("c") or ""
        params = descriptor.get("p") or {}
        source = descriptor.get("l")
        params = {
            name: render(value, lang) if isinstance(value, dict) else _localize_value(value, source, lang)
            for name, value in params.items()
        }
        if any(value is None for value in params.values()):
            return None
        with translation.override(lang):
            template = pgettext(context, msgid) if context else gettext(msgid)
        return _apply(template, params)
    except Exception:  # noqa: BLE001
        logger.debug("Notification i18n: render failed.", exc_info=True)
        return None


class LText:
    """Açıq (tərcümə olunan) bildiriş mətni — ``title`` / ``message`` / ``metadata["link_label"]`` kimi verilir.

    ``str(ltext)`` aktiv dildə render edir (yəni adi ``pgettext(...) % params`` kimi də işləyir); crud isə
    deskriptoru saxlayır ki, oxuyan öz dilində görsün. Mürəkkəb mətn üçün :func:`lformat`.
    """

    __slots__ = ("descriptor",)

    def __init__(self, msgid: str, context: str = "", /, **params):
        descriptor = {"m": msgid, "l": translation.get_language() or settings.LANGUAGE_CODE}
        if context:
            descriptor["c"] = context
        if params:
            descriptor["p"] = {
                name: (
                    value.descriptor if isinstance(value, LText) else (value if isinstance(value, int) else str(value))
                )
                for name, value in params.items()
            }
        self.descriptor = descriptor

    @classmethod
    def _from(cls, descriptor: dict) -> LText:
        obj = cls.__new__(cls)
        obj.descriptor = descriptor
        return obj

    def __str__(self) -> str:
        return render(self.descriptor) or str(self.descriptor.get("m", ""))


def ltext_of(text):
    """Hazır (aktiv dildə render olunmuş) kataloq mətni → :class:`LText`; tanınmasa sətir olduğu kimi qayıdır."""
    found = describe(text)
    return LText._from(found) if found else text


def lformat(template: str, *parts) -> LText:
    """``template.format(*parts)`` — hər hissə :class:`LText` və ya dil-neytral sətirdir (``@istifadəçi``, ad)."""
    return LText._from({"t": template, "a": [p.descriptor if isinstance(p, LText) else str(p) for p in parts]})


# ───────────────────────────── yaradılma / göstərmə ─────────────────────────────


def build_i18n_metadata(title, message, metadata) -> tuple[str, str, dict]:
    """``(title_str, message_str, metadata)`` — ``metadata["i18n"]`` deskriptorlarla doldurulur.

    ``title`` / ``message`` / ``metadata["link_label"]`` ``str`` və ya :class:`LText` ola bilər. ``str`` mətn sütunları
    olduğu kimi qalır (davranış dəyişmir); :class:`LText` sütunları kanonik dildə (az) yazılır. Deskriptor tapılmayan mətn üçün heç nə yazılmır.
    """
    meta = dict(metadata or {})
    i18n = dict(meta.get(META_KEY) or {})

    def prepare(field, value):
        if isinstance(value, Promise):  # gettext_lazy → hazır mətn (sütun üçün də lazımdır)
            value = str(value)
        if isinstance(value, LText):
            i18n[field] = value.descriptor
            # Sütun mətni KANONİK dildə (az): aktiv dil tetikləyənin dilidir, DB-də təsadüfi dil qalmasın.
            text = render(value.descriptor, settings.LANGUAGE_CODE) or str(value)
            return text[: _LIMITS.get(field, 2000)]
        if isinstance(value, str) and value and field not in i18n:
            found = describe(value)
            if found:
                i18n[field] = found
        return value

    title = prepare("title", title)
    message = prepare("message", message)
    if "link_label" in meta:
        meta["link_label"] = prepare("link_label", meta["link_label"])
    if i18n:
        meta[META_KEY] = i18n
    return title, message, meta


def localize_notification(notification, language=None):
    """Bildirişin ``title`` / ``message`` / ``metadata.link_label`` sahələrini oxuyanın dilində (YADDAŞDA) qurur."""
    metadata = getattr(notification, "metadata", None)
    i18n = metadata.get(META_KEY) if isinstance(metadata, dict) else None
    if not isinstance(i18n, dict):
        return notification
    title = render(i18n.get("title"), language) if "title" in i18n else None
    if title:
        notification.title = title
    message = render(i18n.get("message"), language) if "message" in i18n else None
    if message:
        notification.message = message
    label = render(i18n.get("link_label"), language) if "link_label" in i18n else None
    if label:
        notification.metadata = {**metadata, "link_label": label}
    return notification


__all__ = [
    "LText",
    "META_KEY",
    "all_languages",
    "build_i18n_metadata",
    "describe",
    "lformat",
    "localize_notification",
    "ltext_of",
    "render",
]
