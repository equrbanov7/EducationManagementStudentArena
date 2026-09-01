#!/usr/bin/env python3
"""MƏNBƏ KODUNDAN tərcümə msgid-lərini çıxaran skaner.

Niyə lazımdır
-------------
``check_i18n_catalogs.py`` kataloqları YALNIZ bir-biri ilə tutuşdururdu. Ona
görə **heç bir kataloqda olmayan** mətn qapıya ümumiyyətlə görünmürdü: dörd
kataloq da eyni dərəcədə naqis olduğu üçün «drift» yox idi və qapı yaşıl qalırdı.
Bu kor nöqtə bir gündə İKİ dəfə dişlədi (286 sillabus + 67 tələbə-idarəetmə
mətni kodda işlənirdi, kataloqların heç birində yox idi).

Bu modul həmin boşluğu bağlayır: kodda ÇAĞIRILAN msgid-ləri toplayır, qapı isə
onları AZ kataloqu ilə tutuşdurur.

Dizayn qərarları
----------------
1. **Şablonlar üçün Django-nun ÖZ ekstraktoru** (``templatize``) işlədilir —
   ``makemessages``-in içindəki funksiyanın eynisi. Əl ilə yazılmış regex
   ``{% trans %}`` / ``{% translate %}`` / ``{% blocktrans %}``, hər iki dırnaq
   forması, ``trimmed``, ``with a=b`` bağlamaları (``{{ n }}`` → ``%(n)s``),
   ``context "…"`` və ``{% plural %}`` variantlarını gec-tez səhv salır;
   Django-nun ekstraktoru isə tərifən `makemessages` ilə eyni nəticəni verir.
2. **Python üçün AST** — regex DEYİL. Çoxsətirli implicit string birləşməsi
   (``_("uzun " \n "mətn")``) regex-də iki ayrı parça kimi görünür; AST-də isə
   parser onu VAHİD ``ast.Constant``-a yığır. Məhz bu fərq 2026-08-30-da 17
   girişdə yanlış nəticə vermişdi.
3. **Dinamik arqument yoxlanmır** — ``_(variable)`` və ya f-string msgid-i
   statik olaraq bilinmir; belə çağırışlar sükutla buraxılır (yalançı siqnal
   vermək qapını faydasız edərdi).

İstifadə::

    from scripts.i18n_source_scan import collect_source_msgids
    found = collect_source_msgids(BASE)   # {"django": {(ctx, msgid), …}, …}
"""

from __future__ import annotations

import ast
import os
import re

#: Skan olunan kök qovluqlar.
SOURCE_ROOTS = ("apps", "core", "config", "templates", "static")

#: DİQQƏT: `.claude` MÜTLƏQ xaric olmalıdır — orada paralel agentlərin TAM repo
#: worktree kopyaları yaşayır; skan onları da gəzsə başqa şaxələrin mətnləri
#: bu şaxənin borcu kimi görünərdi.
EXCLUDE_DIRS = {
    ".claude",
    ".git",
    "__pycache__",
    "htmlcov",
    "locale",
    "node_modules",
    "staticfiles",
    "venv",
    ".venv",
}
EXCLUDE_FILE_SUFFIXES = (".min.js", ".bundle.js", ".map")

#: Python tərcümə funksiyaları. `*pgettext*` ailəsində BİRİNCİ arqument kontekst.
PY_FUNCS = {
    "_",
    "gettext",
    "gettext_lazy",
    "gettext_noop",
    "ngettext",
    "ngettext_lazy",
    "npgettext",
    "npgettext_lazy",
    "pgettext",
    "pgettext_lazy",
    "ugettext",
    "ugettext_lazy",
}
CTX_FIRST = {"npgettext", "npgettext_lazy", "pgettext", "pgettext_lazy"}

#: `templatize` çıxışındakı çağırışlar (Django həmişə bu dörd addan birini yazır).
PSEUDO_CALL_RE = re.compile(r"\b(npgettext|pgettext|ngettext|gettext)\(")
JS_CALL_RE = re.compile(r"\b(npgettext|pgettext|ngettext|gettext)\s*\(")


# ── ümumi köməkçilər ─────────────────────────────────────────────────────────


def _const_str(node):
    """Yalnız STATİK string sabiti qaytar; dinamikdirsə ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _func_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _pair_from_call(name, args):
    """``(msgctxt, msgid)`` — statik deyilsə ``None``."""
    if name in CTX_FIRST:
        if len(args) < 2:
            return None
        ctx, msg = _const_str(args[0]), _const_str(args[1])
    else:
        if not args:
            return None
        ctx, msg = "", _const_str(args[0])
    if ctx is None or msg is None:
        return None
    return (ctx, msg)


def _balanced_slice(text, open_index):
    """``(`` mövqeyindən başlayaraq bağlanan mötərizəyə qədər kəs.

    Sadə sayğac kifayətdir: `templatize` çıxışında da, JS-də də arqumentlər
    string sabitləridir və içlərindəki mötərizə dırnaq daxilində olur, ona görə
    dırnaq vəziyyəti izlənir.
    """
    depth = 0
    quote = None
    escaped = False
    for i in range(open_index, len(text)):
        ch = text[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_index : i + 1]
        elif ch == "\n" and depth == 0:
            break
    return None


# ── Python ───────────────────────────────────────────────────────────────────


def python_msgids(source: str) -> set:
    """AST ilə çıxarış — çoxsətirli implicit birləşmə DÜZGÜN oxunur."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _func_name(node.func)
        if name not in PY_FUNCS:
            continue
        pair = _pair_from_call(name, node.args)
        if pair and pair[1]:
            found.add(pair)
    return found


# ── Şablonlar ────────────────────────────────────────────────────────────────


def _pseudo_python_msgids(text: str) -> set:
    """``templatize`` çıxışındakı ``gettext(...)`` çağırışlarını oxu.

    Çıxış tam Python DEYİL (aralarda `XXXX` dolğusu var), ona görə hər çağırış
    ayrıca kəsilib `ast` ilə oxunur — dırnaq/escape məsələləri parser-in üzərində
    qalır.
    """
    found = set()
    for match in PSEUDO_CALL_RE.finditer(text):
        expr = _balanced_slice(text, match.end() - 1)
        if not expr:
            continue
        try:
            call = ast.parse(match.group(1) + expr, mode="eval").body
        except SyntaxError:
            continue
        if not isinstance(call, ast.Call):
            continue
        pair = _pair_from_call(match.group(1), call.args)
        if pair and pair[1]:
            found.add(pair)
    return found


def template_msgids(source: str, origin: str = "template.html") -> set:
    """Django-nun öz ``templatize``-i ilə şablon msgid-ləri."""
    try:
        from django.utils.translation.template import templatize
    except Exception:  # pragma: no cover — Django yoxdursa qapı ötürülür
        return set()
    try:
        pseudo = templatize(source, origin=origin)
    except Exception:
        # Sınıq/qeyri-adi şablon qapını qırmamalıdır — sadəcə skan olunmur.
        return set()
    return _pseudo_python_msgids(pseudo)


# ── JavaScript ───────────────────────────────────────────────────────────────


def _js_string(text, start):
    """`start` mövqeyindəki JS string sabitini oxu (`'`/`"`); yoxdursa None."""
    while start < len(text) and text[start] in " \t\r\n":
        start += 1
    if start >= len(text) or text[start] not in "\"'":
        return None, start  # template literal / dəyişən → statik deyil
    quote = text[start]
    out = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
            continue
        if ch == quote:
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None, start


def js_msgids(source: str) -> set:
    """JS ``gettext``/``pgettext`` çağırışları (Django `djangojs` domeni)."""
    found = set()
    for match in JS_CALL_RE.finditer(source):
        name = match.group(1)
        first, after = _js_string(source, match.end())
        if first is None:
            continue
        if name in CTX_FIRST:
            while after < len(source) and source[after] in " \t\r\n":
                after += 1
            if after >= len(source) or source[after] != ",":
                continue
            second, _ = _js_string(source, after + 1)
            if second is None:
                continue
            found.add((first, second))
        else:
            found.add(("", first))
    return {pair for pair in found if pair[1]}


# ── toplama ──────────────────────────────────────────────────────────────────


def _walk_files(base):
    for root_name in SOURCE_ROOTS:
        root = os.path.join(base, root_name)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for filename in filenames:
                if filename.endswith(EXCLUDE_FILE_SUFFIXES):
                    continue
                if filename.endswith((".py", ".html", ".js")):
                    yield os.path.join(dirpath, filename)


def collect_source_msgids(base: str) -> dict:
    """``{domen: {(msgctxt, msgid), …}}`` — kodda ÇAĞIRILAN mətnlər.

    `.py` və `.html` → ``django`` domeni, `.js` → ``djangojs`` (Django-nun
    domen bölgüsünün eynisi).
    """
    result = {"django": set(), "djangojs": set()}
    for path in _walk_files(base):
        try:
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        if path.endswith(".py"):
            result["django"] |= python_msgids(source)
        elif path.endswith(".html"):
            result["django"] |= template_msgids(source, origin=path)
        else:
            result["djangojs"] |= js_msgids(source)
    return result
