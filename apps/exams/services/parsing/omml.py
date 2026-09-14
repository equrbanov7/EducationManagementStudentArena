"""OMML (Word ``m:oMath``) → LaTeX çevirici.

W3 2026-09-14. Word düsturları DOCX-də Office MathML (OMML) kimi saxlanır;
python-docx onları çevirmir. Bu modul lxml elementini gəzib KaTeX-in başa
düşdüyü LaTeX qaytarır. Dəstəklənən qovşaqlar: kəsr (``m:f``), alt/üst indeks
(``m:sSub``/``m:sSup``/``m:sSubSup``/``m:sPre``), kök (``m:rad``), n-ar operator
(``m:nary`` — cəm/inteqral/hasil, limitlərlə), ayırıcı (``m:d``), matris
(``m:m``), funksiya (``m:func``), limit (``m:limLow``/``m:limUpp``), vurğu
(``m:acc``), xətt (``m:bar``), qrup mötərizəsi (``m:groupChr``), çərçivə
(``m:borderBox``), tənlik massivi (``m:eqArr``), yunan hərfləri/operatorlar
(Unicode → LaTeX). Naməlum qovşaq SƏSSİZ atılmır: mətni ``\\text{…}`` kimi
qalır və xəbərdarlıq siyahısına düşür (preview-da göstərilir).
"""

from __future__ import annotations

from dataclasses import dataclass, field

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# Unicode simvol → LaTeX makro (math rejimində). Çoxu KaTeX-də birbaşa Unicode
# kimi də işləyir, amma makro forması bazada oxunaqlı və stabil saxlanır.
UNICODE_TO_LATEX = {
    "α": "\\alpha",
    "β": "\\beta",
    "γ": "\\gamma",
    "δ": "\\delta",
    "ε": "\\varepsilon",
    "ϵ": "\\epsilon",
    "ζ": "\\zeta",
    "η": "\\eta",
    "θ": "\\theta",
    "ϑ": "\\vartheta",
    "ι": "\\iota",
    "κ": "\\kappa",
    "λ": "\\lambda",
    "μ": "\\mu",
    "ν": "\\nu",
    "ξ": "\\xi",
    "π": "\\pi",
    "ρ": "\\rho",
    "σ": "\\sigma",
    "ς": "\\varsigma",
    "τ": "\\tau",
    "υ": "\\upsilon",
    "φ": "\\varphi",
    "ϕ": "\\phi",
    "χ": "\\chi",
    "ψ": "\\psi",
    "ω": "\\omega",
    "Γ": "\\Gamma",
    "Δ": "\\Delta",
    "Θ": "\\Theta",
    "Λ": "\\Lambda",
    "Ξ": "\\Xi",
    "Π": "\\Pi",
    "Σ": "\\Sigma",
    "Υ": "\\Upsilon",
    "Φ": "\\Phi",
    "Ψ": "\\Psi",
    "Ω": "\\Omega",
    "×": "\\times",
    "÷": "\\div",
    "·": "\\cdot",
    "⋅": "\\cdot",
    "±": "\\pm",
    "∓": "\\mp",
    "−": "-",
    "≤": "\\le",
    "≥": "\\ge",
    "≠": "\\ne",
    "≈": "\\approx",
    "≡": "\\equiv",
    "∼": "\\sim",
    "≃": "\\simeq",
    "∝": "\\propto",
    "∞": "\\infty",
    "→": "\\to",
    "←": "\\leftarrow",
    "↔": "\\leftrightarrow",
    "⇒": "\\Rightarrow",
    "⇐": "\\Leftarrow",
    "⇔": "\\Leftrightarrow",
    "∈": "\\in",
    "∉": "\\notin",
    "∋": "\\ni",
    "⊂": "\\subset",
    "⊃": "\\supset",
    "⊆": "\\subseteq",
    "⊇": "\\supseteq",
    "∪": "\\cup",
    "∩": "\\cap",
    "∅": "\\emptyset",
    "∀": "\\forall",
    "∃": "\\exists",
    "¬": "\\neg",
    "∧": "\\wedge",
    "∨": "\\vee",
    "∂": "\\partial",
    "∇": "\\nabla",
    "√": "\\surd",
    "°": "^{\\circ}",
    "′": "'",
    "″": "''",
    "…": "\\ldots",
    "⋯": "\\cdots",
    "∠": "\\angle",
    "⊥": "\\perp",
    "∥": "\\parallel",
    "ℝ": "\\mathbb{R}",
    "ℕ": "\\mathbb{N}",
    "ℤ": "\\mathbb{Z}",
    "ℚ": "\\mathbb{Q}",
    "ℂ": "\\mathbb{C}",
    "ℏ": "\\hbar",
    "∘": "\\circ",
    "∗": "\\ast",
    "⊕": "\\oplus",
    "⊗": "\\otimes",
    "∑": "\\sum",
    "∏": "\\prod",
    "∫": "\\int",
    " ": " ",
}

# Mətn içində LaTeX-də xüsusi məna daşıyan simvollar.
_ESCAPES = {
    "\\": "\\backslash ",
    "{": "\\{",
    "}": "\\}",
    "%": "\\%",
    "#": "\\#",
    "&": "\\&",
    "_": "\\_",
    "^": "\\wedge ",
    "~": "\\sim ",
    "$": "\\$",
}

NARY_CHARS = {
    "∑": "\\sum",
    "∏": "\\prod",
    "∐": "\\coprod",
    "∫": "\\int",
    "∬": "\\iint",
    "∭": "\\iiint",
    "∮": "\\oint",
    "⋃": "\\bigcup",
    "⋂": "\\bigcap",
    "⋁": "\\bigvee",
    "⋀": "\\bigwedge",
}

ACCENTS = {
    "̂": "\\hat",
    "̃": "\\tilde",
    "̄": "\\bar",
    "̅": "\\overline",
    "̆": "\\breve",
    "̇": "\\dot",
    "̈": "\\ddot",
    "̌": "\\check",
    "⃗": "\\vec",
    "⃖": "\\overleftarrow",
    "⃡": "\\overleftrightarrow",
    "̀": "\\grave",
    "́": "\\acute",
}

DELIMITERS = {
    "(": "(",
    ")": ")",
    "[": "[",
    "]": "]",
    "{": "\\{",
    "}": "\\}",
    "|": "|",
    "‖": "\\|",
    "⟨": "\\langle",
    "⟩": "\\rangle",
    "〈": "\\langle",
    "〉": "\\rangle",
    "⌊": "\\lfloor",
    "⌋": "\\rfloor",
    "⌈": "\\lceil",
    "⌉": "\\rceil",
    "": ".",
}

KNOWN_FUNCTIONS = {
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "arcsin",
    "arccos",
    "arctan",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "log",
    "ln",
    "lg",
    "exp",
    "lim",
    "max",
    "min",
    "sup",
    "inf",
    "det",
    "dim",
    "gcd",
    "deg",
    "arg",
    "ker",
    "hom",
}


@dataclass
class OmmlContext:
    warnings: list[str] = field(default_factory=list)


def _val(element, tag: str, default: str | None = None) -> str | None:
    """``<m:tag m:val="…"/>`` uşağının dəyəri (yoxdursa ``default``)."""

    if element is None:
        return default
    child = element.find(_m(tag))
    if child is None:
        return default
    value = child.get(_m("val"))
    return default if value is None else value


def _flag(element, tag: str) -> bool:
    """``<m:tag m:val="1"/>`` və ya ``<m:tag/>`` → True (Word "on" konvensiyası)."""

    if element is None:
        return False
    child = element.find(_m(tag))
    if child is None:
        return False
    value = (child.get(_m("val")) or "1").strip().lower()
    return value in ("1", "true", "on")


def _escape_text(text: str) -> str:
    out = []
    for char in text:
        if char in UNICODE_TO_LATEX:
            out.append(UNICODE_TO_LATEX[char] + " ")
        elif char in _ESCAPES:
            out.append(_ESCAPES[char])
        else:
            out.append(char)
    return "".join(out)


def _run_text(run) -> str:
    parts = []
    for node in run.iter():
        if node.tag in (_m("t"), _w("t")):
            parts.append(node.text or "")
    return "".join(parts)


def _convert_run(run, ctx: OmmlContext) -> str:
    text = _run_text(run)
    if not text:
        return ""
    style_props = run.find(_m("rPr"))
    # `m:nor` — "normal text" run: Word onu düz mətn kimi göstərir → \text{…}.
    if style_props is not None and style_props.find(_m("nor")) is not None:
        plain = text.replace("\\", "").replace("{", "\\{").replace("}", "\\}")
        return f"\\text{{{plain}}}"
    stripped = text.strip()
    if stripped in KNOWN_FUNCTIONS:
        # «lim»/«sin» kimi funksiya adı düz run kimi gəlibsə — kursiv olmasın.
        return "\\" + stripped + " "
    # Riyazi rejimdə boşluqlar onsuz da render olunmur; yalnız yığcamlaşdırılır.
    return " ".join(_escape_text(text).split())


def _children_latex(element, ctx: OmmlContext) -> str:
    return "".join(convert_node(child, ctx) for child in element)


def _arg(element, tag: str, ctx: OmmlContext) -> str:
    child = element.find(_m(tag))
    return _children_latex(child, ctx) if child is not None else ""


def _brace(latex: str) -> str:
    return "{" + latex + "}"


def _convert_fraction(node, ctx):
    props = node.find(_m("fPr"))
    kind = _val(props, "type", "bar")
    num, den = _arg(node, "num", ctx), _arg(node, "den", ctx)
    if kind == "noBar":
        return f"{{{num} \\atop {den}}}"
    if kind in ("skw", "lin"):
        return f"{_brace(num)}/{_brace(den)}"
    return f"\\frac{_brace(num)}{_brace(den)}"


def _convert_nary(node, ctx):
    props = node.find(_m("naryPr"))
    chr_value = _val(props, "chr", "∫")
    operator = NARY_CHARS.get(chr_value)
    if operator is None:
        ctx.warnings.append(f"naryPr chr={chr_value!r}")
        operator = "\\operatorname{" + _escape_text(chr_value) + "}"
    lim_loc = _val(props, "limLoc", "subSup")
    sub = "" if _flag(props, "subHide") else _arg(node, "sub", ctx)
    sup = "" if _flag(props, "supHide") else _arg(node, "sup", ctx)
    out = operator
    if lim_loc == "undOvr" and (sub or sup):
        out += "\\limits"
    if sub:
        out += "_" + _brace(sub)
    if sup:
        out += "^" + _brace(sup)
    return out + " " + _arg(node, "e", ctx)


def _convert_delimiter(node, ctx):
    props = node.find(_m("dPr"))
    beg = _val(props, "begChr", "(")
    end = _val(props, "endChr", ")")
    sep = _val(props, "sepChr", "|")
    left = DELIMITERS.get(beg, _escape_text(beg))
    right = DELIMITERS.get(end, _escape_text(end))
    inner = (" " + DELIMITERS.get(sep, sep) + " ").join(_children_latex(child, ctx) for child in node.findall(_m("e")))
    return f"\\left{left} {inner} \\right{right}"


def _convert_matrix(node, ctx):
    rows = []
    for row in node.findall(_m("mr")):
        rows.append(" & ".join(_children_latex(cell, ctx) for cell in row.findall(_m("e"))))
    return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"


def _convert_function(node, ctx):
    name_node = node.find(_m("fName"))
    argument = _arg(node, "e", ctx)
    plain_name = "".join(_run_text(run) for run in name_node.iter(_m("r"))) if name_node is not None else ""
    plain_name = plain_name.strip()
    if name_node is not None and name_node.find(_m("limLow")) is not None:
        # lim_{x→0} kimi: fName özü limLow qovşağıdır.
        return _children_latex(name_node, ctx) + " " + argument
    if plain_name in KNOWN_FUNCTIONS:
        return f"\\{plain_name} {argument}"
    if plain_name:
        return f"\\operatorname{{{plain_name}}} {argument}"
    return _children_latex(name_node, ctx) + " " + argument if name_node is not None else argument


def _convert_accent(node, ctx):
    props = node.find(_m("accPr"))
    chr_value = _val(props, "chr", "̂")
    macro = ACCENTS.get(chr_value)
    if macro is None:
        ctx.warnings.append(f"accPr chr={chr_value!r}")
        macro = "\\hat"
    return f"{macro}{_brace(_arg(node, 'e', ctx))}"


def _convert_bar(node, ctx):
    props = node.find(_m("barPr"))
    position = _val(props, "pos", "top")
    macro = "\\underline" if position == "bot" else "\\overline"
    return f"{macro}{_brace(_arg(node, 'e', ctx))}"


def _convert_group_char(node, ctx):
    props = node.find(_m("groupChrPr"))
    position = _val(props, "pos", "bot")
    macro = "\\overbrace" if position == "top" else "\\underbrace"
    return f"{macro}{_brace(_arg(node, 'e', ctx))}"


def _convert_eq_array(node, ctx):
    rows = [_children_latex(cell, ctx) for cell in node.findall(_m("e"))]
    return "\\begin{aligned} " + " \\\\ ".join(rows) + " \\end{aligned}"


def _convert_sub_sup(node, ctx):
    base = _brace(_arg(node, "e", ctx))
    sub = _arg(node, "sub", ctx)
    sup = _arg(node, "sup", ctx)
    out = base
    if node.tag in (_m("sSub"), _m("sSubSup")):
        out += "_" + _brace(sub)
    if node.tag in (_m("sSup"), _m("sSubSup")):
        out += "^" + _brace(sup)
    return out


def _convert_pre_sub_sup(node, ctx):
    return f"{{}}_{_brace(_arg(node, 'sub', ctx))}^{_brace(_arg(node, 'sup', ctx))}{_brace(_arg(node, 'e', ctx))}"


def _convert_radical(node, ctx):
    props = node.find(_m("radPr"))
    degree = "" if _flag(props, "degHide") else _arg(node, "deg", ctx).strip()
    body = _brace(_arg(node, "e", ctx))
    return f"\\sqrt[{degree}]{body}" if degree else f"\\sqrt{body}"


_HANDLERS = {
    _m("f"): _convert_fraction,
    _m("sSub"): _convert_sub_sup,
    _m("sSup"): _convert_sub_sup,
    _m("sSubSup"): _convert_sub_sup,
    _m("sPre"): _convert_pre_sub_sup,
    _m("rad"): _convert_radical,
    _m("nary"): _convert_nary,
    _m("d"): _convert_delimiter,
    _m("m"): _convert_matrix,
    _m("func"): _convert_function,
    _m("acc"): _convert_accent,
    _m("bar"): _convert_bar,
    _m("groupChr"): _convert_group_char,
    _m("eqArr"): _convert_eq_array,
    _m("limLow"): lambda node, ctx: f"\\underset{_brace(_arg(node, 'lim', ctx))}{_brace(_arg(node, 'e', ctx))}",
    _m("limUpp"): lambda node, ctx: f"\\overset{_brace(_arg(node, 'lim', ctx))}{_brace(_arg(node, 'e', ctx))}",
    _m("borderBox"): lambda node, ctx: f"\\boxed{_brace(_arg(node, 'e', ctx))}",
    _m("box"): lambda node, ctx: _brace(_arg(node, "e", ctx)),
    _m("phant"): lambda node, ctx: f"\\phantom{_brace(_arg(node, 'e', ctx))}",
}

# Xassə (property) qovşaqları çıxışa heç nə vermir.
_PROPERTY_TAGS = {
    _m(tag)
    for tag in (
        "fPr",
        "sSubPr",
        "sSupPr",
        "sSubSupPr",
        "sPrePr",
        "radPr",
        "naryPr",
        "dPr",
        "mPr",
        "funcPr",
        "accPr",
        "barPr",
        "groupChrPr",
        "eqArrPr",
        "limLowPr",
        "limUppPr",
        "borderBoxPr",
        "boxPr",
        "phantPr",
        "oMathParaPr",
        "rPr",
        "ctrlPr",
        "argPr",
    )
}


def convert_node(node, ctx: OmmlContext) -> str:
    """Bir OMML qovşağını LaTeX-ə çevir (rekursiv)."""

    tag = node.tag
    if tag in _PROPERTY_TAGS or tag == _w("rPr") or tag == _w("bookmarkStart") or tag == _w("bookmarkEnd"):
        return ""
    handler = _HANDLERS.get(tag)
    if handler is not None:
        return handler(node, ctx)
    if tag in (_m("r"), _w("r")):
        return _convert_run(node, ctx)
    if tag in (_m("oMath"), _m("e"), _m("num"), _m("den"), _m("sub"), _m("sup"), _m("deg"), _m("lim"), _m("fName")):
        return _children_latex(node, ctx)
    if tag == _m("oMathPara"):
        return " ".join(convert_node(child, ctx) for child in node.findall(_m("oMath")))
    if tag in (_w("hyperlink"), _w("ins"), _w("smartTag"), _w("sdt"), _w("sdtContent")):
        return _children_latex(node, ctx)
    # Naməlum qovşaq — səssiz atılmır: mətn qalır, xəbərdarlıq düşür.
    local = tag.rsplit("}", 1)[-1]
    ctx.warnings.append(local)
    fallback = "".join(_run_text(run) for run in node.iter(_m("r")))
    if not fallback:
        return ""
    return "\\text{" + fallback.replace("\\", "").replace("{", "\\{").replace("}", "\\}") + "}"


def omml_to_latex(element) -> tuple[str, list[str]]:
    """``m:oMath``/``m:oMathPara`` elementini ``(latex, warnings)`` kimi qaytar.

    ``warnings`` — dəstəklənməyən qovşaq adları (boş siyahı = tam çevrildi).
    Nəticə ayırıcısızdır; çağıran ``\\(…\\)``/``\\[…\\]`` əlavə edir.
    """

    ctx = OmmlContext()
    latex = convert_node(element, ctx)
    latex = " ".join(latex.split())
    return latex, ctx.warnings


__all__ = ["M_NS", "UNICODE_TO_LATEX", "omml_to_latex", "convert_node"]
