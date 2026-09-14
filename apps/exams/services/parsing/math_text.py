"""Sual mətnində LaTeX düsturları — aşkarlama və server tərəfi sanitizasiya.

W3 2026-09-14 (sahibin istəyi: «şəkil və düstur olanda problem yaranmasın —
dünya praktikası»). Moodle/Canvas/QTI kimi LMS-lərdə düstur MƏTN olaraq
(LaTeX, standart ayırıcılarla) saxlanır, HTML deyil: axtarıla bilir, redaktə
olunur, XSS səthi yoxdur. Brauzerdə KaTeX (`static/js/ems_math.js`,
``trust:false``) mətn düyünlərindən render edir.

Bu modul yalnız mətn üzərində işləyir:
  * ``find_formulas`` — ``$$…$$``, ``\\[…\\]``, ``\\(…\\)``, ``$…$`` ayırıcılarını tapır;
  * ``sanitize_math_text`` — uzunluq limiti (2 000 simvol) və qadağan siyahısı
    (``\\href``, ``\\url``, ``\\includegraphics``, ``\\def``/``\\newcommand`` …):
    pozan düsturun ayırıcıları qırılır (mətn olaraq qalır, render olunmur) və
    xəbərdarlıq qaytarılır — HEÇ VAXT səssiz silinmir;
  * ``math_summary`` — preview «inam» nişanı üçün düstur sayı.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMULA_MAX_LEN = 2000

# Qadağan olunan makrolar: URL/şəkil daxil edən, makro təyin edən və KaTeX-in
# `trust` tələb edən HTML-genişlənmələri. Server tərəfi qat KaTeX ``trust:false``
# ilə ikiqat müdafiədir (client JS söndürülsə də mətn zərərsizdir).
DENIED_COMMANDS = (
    "\\href",
    "\\url",
    "\\includegraphics",
    "\\def",
    "\\gdef",
    "\\edef",
    "\\xdef",
    "\\let",
    "\\futurelet",
    "\\newcommand",
    "\\renewcommand",
    "\\providecommand",
    "\\input",
    "\\include",
    "\\write",
    "\\csname",
    "\\catcode",
    "\\htmlClass",
    "\\htmlId",
    "\\htmlStyle",
    "\\htmlData",
)

# Sıra vacibdir: `$$` `$`-dan, `\[`/`\(` isə hər ikisindən əvvəl yoxlanır.
_FORMULA_RE = re.compile(
    r"\$\$(?P<dd>.+?)\$\$"
    r"|\\\[(?P<sb>.+?)\\\]"
    r"|\\\((?P<rp>.+?)\\\)"
    r"|(?<![\\$\w])\$(?P<sd>[^$\n]+?)\$(?![\w$])",
    re.DOTALL,
)

_DENIED_RE = re.compile("|".join(re.escape(cmd) + r"(?![A-Za-z])" for cmd in DENIED_COMMANDS))


@dataclass(frozen=True)
class Formula:
    start: int
    end: int
    body: str
    display: bool

    @property
    def length(self) -> int:
        return len(self.body)


def find_formulas(text: str) -> list[Formula]:
    """Mətndəki bütün düsturları (ayırıcı daxil mövqe ilə) qaytar."""

    found: list[Formula] = []
    for match in _FORMULA_RE.finditer(text or ""):
        kind = match.lastgroup
        body = match.group(kind) or ""
        found.append(
            Formula(
                start=match.start(),
                end=match.end(),
                body=body,
                display=kind in ("dd", "sb"),
            )
        )
    return found


def denied_command(body: str) -> str | None:
    """Düstur gövdəsində qadağan makro varsa onun adını qaytar."""

    match = _DENIED_RE.search(body or "")
    return match.group(0) if match else None


def _neutralised(formula: Formula, original: str) -> str:
    """Ayırıcıları qır: gövdə mətn kimi qalır, KaTeX onu düstur saymır."""

    body = " ".join((formula.body or "").split())
    # Qadağan makronun ters slaşı da çıxarılır ki, brauzerdə `\href` görünüb
    # başqa render qatına düşməsin; mətn oxunaqlı qalır.
    body = body.replace("\\", "")
    return body


def sanitize_math_text(text: str) -> tuple[str, list[dict]]:
    """Düsturları yoxla; pozanları zərərsizləşdir. ``(yeni_mətn, problemlər)``.

    Problem elementi: ``{"type": "formula_too_long" | "formula_denied",
    "command": str | None, "preview": str}``. Düstur içindəki sətir keçidləri
    boşluğa çevrilir — ``linebreaks`` filtri düsturu ``<br>`` ilə bölməsin;
    ``$…$``/``$$…$$`` ayırıcıları ``\\(…\\)``/``\\[…\\]`` kanonik formasına salınır.
    """

    source = text or ""
    if "$" not in source and "\\(" not in source and "\\[" not in source:
        return source, []

    issues: list[dict] = []
    pieces: list[str] = []
    cursor = 0
    for formula in find_formulas(source):
        pieces.append(source[cursor : formula.start])
        raw = source[formula.start : formula.end]
        command = denied_command(formula.body)
        if formula.length > FORMULA_MAX_LEN:
            issues.append(
                {
                    "type": "formula_too_long",
                    "command": None,
                    "preview": formula.body[:40],
                }
            )
            pieces.append(_neutralised(formula, raw))
        elif command:
            issues.append({"type": "formula_denied", "command": command, "preview": formula.body[:40]})
            pieces.append(_neutralised(formula, raw))
        else:
            # Etibarlı düstur: daxili sətir keçidləri boşluğa, ayırıcı isə
            # kanonik LaTeX formasına (`\(…\)` / `\[…\]`) çevrilir — Moodle-un
            # TeX filtri kimi: bazada tək forma, valyuta `$5`-lə qarışıqlıq yox.
            body = " ".join(formula.body.split())
            pieces.append(f"\\[{body}\\]" if formula.display else f"\\({body}\\)")
        cursor = formula.end
    pieces.append(source[cursor:])
    return "".join(pieces), issues


def math_summary(text: str) -> dict:
    """Preview inam nişanı üçün: ``{"count": n, "display": m}``."""

    formulas = find_formulas(text or "")
    return {
        "count": len(formulas),
        "display": sum(1 for formula in formulas if formula.display),
    }


__all__ = [
    "DENIED_COMMANDS",
    "FORMULA_MAX_LEN",
    "Formula",
    "denied_command",
    "find_formulas",
    "math_summary",
    "sanitize_math_text",
]
