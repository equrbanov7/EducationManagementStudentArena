/* ═══════════════════════════════════════════════════════════════════════════
   EMSSearch — klient tərəfi axtarışın KANONİK qatlama/uyğunluq funksiyası
   (sahib 2026-09-26: «bütün search yerlərində az hərfləri ilə yazanda en
   nəticə də gəlsin; «234king» «234 K ing»i tapsın»).

   Server əkizi: core/search_text.py (fold_regex / tolerant_match) — qaydalar
   EYNİDİR, paritet testi core/tests/test_search_text_js_parity.py.

     i/ı/İ/I · e/ə · ə/a («Aliyev» → «Əliyev») · s/ş, «sh» ↔ ş · c/ç, «ch» ↔ ç
     g/ğ, «gh» ↔ ğ · o/ö · u/ü · x ↔ «kh»

   compact (kod rejimi: qrup adı, fənn kodu, otaq…): sorğudakı ayırıcılar
   (boşluq - _ . /) atılır, simvollar arasında ixtiyari ayırıcıya icazə var.
   Klientdə DEFAULT compact=true — etiketlər qısadır, compact normal rejimin
   üst çoxluğudur (sıfır ayırıcı da uyğundur). Serverlə eyni: kod rejimi yalnız
   rəqəmli və ya ≥ 4 simvollu tokenə («PA» «Qrup A»nı tapmasın); çox tokenli
   sorğu həm də bitişdirilmiş halda yoxlanır. Mətndəki U+0307 (``"İ".toLowerCase()``
   → «i̇») atılır.

   API
     EMSSearch.tokens(query)                  → ["tok", …] (≤ 4, hər biri ≤ 40)
     EMSSearch.pattern(token, {compact})      → RegExp mənbəyi
     EMSSearch.codePattern(token)             → kod sahəsi şablonu (≥4 / rəqəm → compact)
     EMSSearch.matcher(query, {compact})      → function(text, …) → bool
                                                (bir dəfə qurulur, çox dəfə işlədilir)
     EMSSearch.matches(query, text, {compact}) → bool (boş sorğu → true)
     EMSSearch.fold(text)                     → sadə kanonik forma (sıralama/
                                                vurğulama üçün; ə↔a və «sh»
                                                bilmir — uyğunluq üçün matches)
   Asılılıq yoxdur, DOM-a toxunmur; təkrar yüklənsə mövcud obyekti saxlayır.
   ═══════════════════════════════════════════════════════════════════════════ */
(function (root) {
  "use strict";
  if (root.EMSSearch && root.EMSSearch.__v === 1) return;

  var MAX_TOKENS = 4;
  var MAX_QUERY_LENGTH = 120;
  var MAX_TOKEN_LENGTH = 40;
  var COMPACT_MIN_CHARS = 4;
  var SEP = "[\\s._/-]";
  var SEPARATORS = " \t\r\n\f\v._/-";

  var SINGLE = {
    "a": "[aAəƏ]",
    "ə": "[əƏeEaA]",
    "e": "[eEəƏ]",
    "i": "[iıİI]",
    "ı": "[iıİI]",
    "s": "[sSşŞ]",
    "ş": "(?:[sS][hH]|[sSşŞ])",
    "c": "[cCçÇ]",
    "ç": "(?:[cC][hH]|[cCçÇ])",
    "g": "[gGğĞ]",
    "ğ": "(?:[gG][hH]|[gGğĞ])",
    "o": "[oOöÖ]",
    "ö": "[oOöÖ]",
    "u": "[uUüÜ]",
    "ü": "[uUüÜ]",
    "x": "(?:[xX]|[kK][hH])"
  };
  var DIGRAPHS = {
    "sh": "(?:[sS][hH]|[şŞ])",
    "ch": "(?:[cC][hH]|[çÇ])",
    "gh": "(?:[gG][hH]|[ğĞ])",
    "kh": "(?:[kK][hH]|[xX])"
  };
  var LOWER = { "İ": "i", "I": "i", "Ə": "ə", "Ş": "ş", "Ç": "ç", "Ğ": "ğ", "Ö": "ö", "Ü": "ü" };
  var FOLD = { "ı": "i", "ə": "e", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u" };

  function low(ch) {
    if (LOWER[ch]) return LOWER[ch];
    var l = ch.toLowerCase();
    return l.length === 1 ? l : ch;
  }

  function escapeChar(ch) {
    return /[\\^$.*+?()[\]{}|\/-]/.test(ch) ? "\\" + ch : ch;
  }

  function charPattern(ch) {
    var l = low(ch);
    if (Object.prototype.hasOwnProperty.call(SINGLE, l)) return SINGLE[l];
    var u = l.toUpperCase();
    if (u.length === 1 && u !== l) return "[" + l + u + "]";
    return escapeChar(ch);
  }

  function tokens(query) {
    var text = String(query == null ? "" : query).trim().slice(0, MAX_QUERY_LENGTH);
    if (!text) return [];
    return text.split(/\s+/).filter(Boolean).slice(0, MAX_TOKENS).map(function (t) {
      return t.slice(0, MAX_TOKEN_LENGTH);
    });
  }

  function pattern(token, opts) {
    var compact = !!(opts && opts.compact);
    var chars = Array.from(String(token == null ? "" : token)).slice(0, MAX_TOKEN_LENGTH);
    if (compact) chars = chars.filter(function (ch) { return SEPARATORS.indexOf(ch) === -1; });
    var parts = [];
    var i = 0;
    while (i < chars.length) {
      var pair = i + 1 < chars.length ? low(chars[i]) + low(chars[i + 1]) : "";
      if (pair && Object.prototype.hasOwnProperty.call(DIGRAPHS, pair)) {
        parts.push(DIGRAPHS[pair]);
        i += 2;
        continue;
      }
      parts.push(charPattern(chars[i]));
      i += 1;
    }
    return parts.join(compact ? SEP + "*" : "");
  }

  function compactOf(opts) {
    return !(opts && opts.compact === false);
  }

  function compactEligible(token) {
    var chars = Array.from(String(token)).filter(function (ch) { return SEPARATORS.indexOf(ch) === -1; });
    return chars.some(function (ch) { return /[0-9]/.test(ch); }) || chars.length >= COMPACT_MIN_CHARS;
  }

  function codePattern(token) {
    return pattern(token, { compact: compactEligible(token) });
  }

  function matcher(query, opts) {
    var compact = compactOf(opts);
    var toks = tokens(query);
    var regexes = toks.map(function (t) {
      return new RegExp(compact ? codePattern(t) : pattern(t), "i");
    });
    var glued = null;
    if (compact && toks.length > 1) {
      var joined = Array.from(toks.join("")).slice(0, MAX_TOKEN_LENGTH).join("");
      if (compactEligible(joined)) glued = new RegExp(pattern(joined, { compact: true }), "i");
    }
    return function () {
      if (!regexes.length) return true;
      var hay = [];
      for (var a = 0; a < arguments.length; a += 1) {
        if (arguments[a] != null && arguments[a] !== "") hay.push(String(arguments[a]).replace(/\u0307/g, ""));
      }
      var hitAny = function (rx) {
        return hay.some(function (text) { return rx.test(text); });
      };
      return regexes.every(hitAny) || (!!glued && hitAny(glued));
    };
  }

  function matches(query, text, opts) {
    return matcher(query, opts)(text);
  }

  function fold(text) {
    return Array.from(String(text == null ? "" : text)).map(function (ch) {
      var l = low(ch);
      return FOLD[l] || l;
    }).join("");
  }

  root.EMSSearch = {
    __v: 1,
    tokens: tokens,
    pattern: pattern,
    codePattern: codePattern,
    matcher: matcher,
    matches: matches,
    fold: fold
  };
})(typeof window !== "undefined" ? window : globalThis);
