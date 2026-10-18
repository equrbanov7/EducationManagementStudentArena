/* code_text.js — sual / variant mətnində KOD NÜMUNƏSİ (sahib 2026-10-19).
 *
 * Sahib: «Kod nümunəsi ora yerləşdirəndə alt-alta görünsün, birləşməsin — necə var o formada göstərək.»
 *
 * Mətn DÜZ mətndir (`ExamQuestion.text`, `\n` ilə). İki qayda:
 *   1) ```…``` (istəyə bağlı dil adı ilə: ```python) — AÇIQ kod bloku;
 *   2) çəpərsiz yapışdırılmış kod — ən azı 2 sətirlik, içində ən azı bir «güclü» kod əlaməti olan
 *      ardıcıl sətirlər (`{ } ;` ilə bitən, açar söz, mənimsətmə, funksiya çağırışı; girintili sətirlər
 *      yalnız ona qoşulur). Qalan mətn olduğu kimi qalır (CSS `white-space: pre-wrap` sətirləri saxlayır).
 *
 * TƏHLÜKƏSİZLİK: istifadəçi mətni HEÇ VAXT innerHTML-ə getmir — DOM `createElement` + `textContent` ilə
 * qurulur. `hydrateCodeText(root)` əvvəlcədən `esc()` ilə render olunmuş `[data-code-text]` elementinin
 * `textContent`-ini (xam mətn) oxuyur və uşaqlarını yenidən qurur.
 *
 * SAF modul (import yoxdur) — Node testləri: tests/js/live_code_text.test.js. Python əkizi:
 * `core/templatetags/code_text.py` (eyni qaydalar; adi imtahan ekranı üçün).
 */

const FENCE_OPEN = /^\s*```\s*([\w#+.-]*)\s*$/;
const FENCE_CLOSE = /^\s*```\s*$/;
const INDENTED = /^(?:\t| {2,})\S/;
const STRONG = [
    /[{};]\s*$/, // C/Java/JS sətir sonu
    /^\s*[}\])]/, // bağlayan mötərizə ilə başlayır
    /^\s*(?:def|class|import|from|return|for|while|if|elif|else|try|except|finally|with|lambda|print|function|const|let|var|public|private|protected|static|void|int|float|double|char|bool|boolean|string|struct|using|namespace|package|begin|end|echo|printf|cout|cin|System)\b/,
    /^\s*#\s*(?:include|define|import)\b/,
    /^\s*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|FROM|WHERE|JOIN|GROUP BY|ORDER BY)\b/,
    /^\s*[A-Za-z_$][\w$.[\]]*\s*(?:[+\-*/%]?=)(?!=)\s*\S/, // x = 5, total += i
    /^\s*[A-Za-z_$][\w$.]*\(.*\)\s*;?\s*$/, // print(x), console.log(a) — «Ali (tələbə)» deyil
];

const isBlank = (line) => /^\s*$/.test(line);
const isStrong = (line) => STRONG.some((re) => re.test(line));

function trimBlankLines(lines) {
    let start = 0;
    let end = lines.length;
    while (start < end && isBlank(lines[start])) start += 1;
    while (end > start && isBlank(lines[end - 1])) end -= 1;
    return lines.slice(start, end);
}

function dedent(lines) {
    const widths = lines.filter((line) => !isBlank(line)).map((line) => line.match(/^[ \t]*/)[0].length);
    const cut = widths.length ? Math.min(...widths) : 0;
    return cut ? lines.map((line) => line.slice(Math.min(cut, line.match(/^[ \t]*/)[0].length))) : lines;
}

function pushText(segments, lines) {
    const kept = trimBlankLines(lines);
    if (kept.length) segments.push({ type: "text", text: kept.join("\n") });
}

function pushCode(segments, lines, lang) {
    const kept = dedent(trimBlankLines(lines));
    if (kept.length) segments.push({ type: "code", text: kept.join("\n"), lang: lang || "" });
}

/** Çəpərsiz sətirlər: kod «run»-larını tapır (bax modul şərhi). */
function splitPlain(segments, lines) {
    const kind = lines.map((line) => (isBlank(line) ? "blank" : isStrong(line) ? "strong" : INDENTED.test(line) ? "weak" : "text"));
    // İki kod sətri arasında qalan TƏK adi sətir (məs. `writeln(x)` olmayan Pascal sətri) koda qoşulur.
    for (let i = 1; i < kind.length - 1; i += 1) {
        if (kind[i] !== "text") continue;
        const prev = kind.slice(0, i).reverse().find((k) => k !== "blank");
        const next = kind.slice(i + 1).find((k) => k !== "blank");
        if ((prev === "strong" || prev === "weak") && (next === "strong" || next === "weak")) kind[i] = "weak";
    }
    let textBuf = [];
    let i = 0;
    while (i < lines.length) {
        if (kind[i] !== "strong" && kind[i] !== "weak") {
            textBuf.push(lines[i]);
            i += 1;
            continue;
        }
        let j = i;
        let last = i;
        let strong = 0;
        let count = 0;
        while (j < lines.length && kind[j] !== "text") {
            if (kind[j] !== "blank") {
                last = j;
                count += 1;
                if (kind[j] === "strong") strong += 1;
            }
            j += 1;
        }
        if (count >= 2 && strong >= 1) {
            pushText(segments, textBuf);
            textBuf = [];
            pushCode(segments, lines.slice(i, last + 1), "");
        } else {
            textBuf = textBuf.concat(lines.slice(i, last + 1));
        }
        i = last + 1;
    }
    pushText(segments, textBuf);
}

/** Mətni seqmentlərə bölür: [{ type: "text" | "code", text, lang? }]. */
export function splitCodeSegments(value) {
    const lines = String(value == null ? "" : value)
        .replace(/\r\n?/g, "\n")
        .split("\n");
    const segments = [];
    let plain = [];
    let i = 0;
    while (i < lines.length) {
        const open = FENCE_OPEN.exec(lines[i]);
        if (!open) {
            plain.push(lines[i]);
            i += 1;
            continue;
        }
        let j = i + 1;
        while (j < lines.length && !FENCE_CLOSE.test(lines[j])) j += 1;
        splitPlain(segments, plain);
        plain = [];
        pushCode(segments, lines.slice(i + 1, j), open[1]);
        i = j + 1; // bağlanmayan çəpər — mətnin sonuna qədər kod
    }
    splitPlain(segments, plain);
    return segments;
}

export const hasCodeBlock = (value) => splitCodeSegments(value).some((segment) => segment.type === "code");

/**
 * Elementin uşaqlarını seqmentlərdən qurur (yalnız createElement + textContent).
 * Kod yoxdursa elementə toxunmur (`pre-wrap` sətirləri onsuz da saxlayır) → false.
 */
export function renderCodeText(element, value) {
    if (!element) return false;
    const segments = splitCodeSegments(value);
    if (!segments.some((segment) => segment.type === "code")) return false;
    const doc = element.ownerDocument;
    element.textContent = "";
    segments.forEach((segment) => {
        if (segment.type === "code") {
            // <code> «phrasing content»-dir — <h2>/<p>/<button> içində etibarlıdır (<pre> deyil).
            const code = doc.createElement("code");
            code.className = "lx-code";
            code.setAttribute("translate", "no");
            if (segment.lang) code.dataset.lang = segment.lang;
            code.textContent = segment.text;
            element.appendChild(code);
        } else {
            const span = doc.createElement("span");
            span.className = "lx-code-text";
            span.textContent = segment.text;
            element.appendChild(span);
        }
    });
    element.classList.add("has-code");
    return true;
}

/** `[data-code-text]` elementlərini (bir dəfə) kod bloklu görünüşə çevirir. */
export function hydrateCodeText(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    root.querySelectorAll("[data-code-text]").forEach((element) => {
        if (element.dataset.codeText === "done") return;
        element.dataset.codeText = "done";
        renderCodeText(element, element.textContent);
    });
}
