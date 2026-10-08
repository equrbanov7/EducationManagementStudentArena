import { icon, shapeKey, shapeSvg, toneIndex } from './icons.js?v=lx20261008';
import { esc, formatNumber, lengthClass, tr } from './utils.js?v=lx20261008';

/* Cavab plitələri — rəng (t1..t6) + FİQUR (rəng korları üçün), host və telefonda eyni:
 * 1 üçbucaq (qırmızı), 2 romb (göy), 3 dairə (kəhrəba), 4 kvadrat (yaşıl),
 * 5 ulduz (bənövşəyi; server açarı "pentagon"), 6 altıbucaq (firuzəyi). */

const SHAPE_LABELS = {
    triangle: ["shapeTriangle", "Üçbucaq"],
    diamond: ["shapeDiamond", "Romb"],
    circle: ["shapeCircle", "Dairə"],
    square: ["shapeSquare", "Kvadrat"],
    star: ["shapeStar", "Ulduz"],
    hexagon: ["shapeHexagon", "Altıbucaq"],
};

export function optionShapeLabel(option, index) {
    const [key, fallback] = SHAPE_LABELS[shapeKey(option, index)] || SHAPE_LABELS.circle;
    return tr(key, fallback);
}

/** 2026-10-08 (L4): ən uzun variantın uzunluq sinfi — səhnə plitələrə hündürlüyün çox payını verir. */
export function optionsLengthClass(options) {
    const longest = (Array.isArray(options) ? options : []).reduce((max, option) => Math.max(max, String(option?.text || "").length), 0);
    if (longest <= 40) return "s";
    if (longest <= 90) return "m";
    return "l";
}

export function tilesGridClass(count) {
    const n = Math.max(1, Math.min(6, Number(count) || 0));
    return `hx-tiles--n${n}`;
}

/** verdict: undefined (sual) | "correct" | "wrong" (reveal). */
export function answerTileMarkup(option, index, verdict) {
    const shape = shapeKey(option, index);
    const label = optionShapeLabel(option, index);
    const text = String(option?.text || "");
    const verdictClass = verdict === "correct" ? "is-correct" : verdict === "wrong" ? "is-wrong" : "";
    const verdictText = verdict === "correct" ? tr("correctTag", "Düzgün") : verdict === "wrong" ? tr("wrongTag", "Səhv") : "";
    return `
        <article class="hx-tile hx-tile--t${toneIndex(index)} ${verdictClass}" data-len="${lengthClass(text)}" data-option-id="${Number(option?.id || 0)}">
            <span class="hx-tile__shape" role="img" aria-label="${esc(label)}">${shapeSvg(shape)}</span>
            <span class="hx-tile__text hx-scroll">${esc(text)}</span>
            ${
                verdict
                    ? `<span class="hx-tile__verdict" role="img" aria-label="${esc(verdictText)}">${icon(verdict === "correct" ? "check" : "cross")}</span>`
                    : ""
            }
        </article>
    `;
}

/** Reveal sütun qrafiki (Chart.js əvəzinə — yalnız transform animasiyası). */
export function distributionBarsMarkup(options, distribution, correctIds) {
    const max = Math.max(1, ...options.map((option) => Number(distribution.counts.get(Number(option?.id || 0)) || 0)));
    const total = Math.max(0, Number(distribution.totalAnswers || 0));
    return options
        .map((option, index) => {
            const id = Number(option?.id || 0);
            const count = Number(distribution.counts.get(id) || 0);
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            const correct = correctIds.includes(id);
            return `
                <div class="hx-bar hx-bar--t${toneIndex(index)} ${correct ? "is-correct" : "is-wrong"}" data-ratio="${(count / max).toFixed(4)}" data-count="${count}">
                    <span class="hx-bar__value"><strong data-bar-count>0</strong><small>${pct}%</small></span>
                    <span class="hx-bar__track"><span class="hx-bar__fill"></span></span>
                    <span class="hx-bar__foot">
                        <span class="hx-bar__shape" role="img" aria-label="${esc(optionShapeLabel(option, index))}">${shapeSvg(shapeKey(option, index))}</span>
                        ${correct ? `<span class="hx-bar__check" role="img" aria-label="${esc(tr("correctTag", "Düzgün"))}">${icon("check")}</span>` : ""}
                    </span>
                    <span class="hx-sr">${esc(option?.text || "")}: ${formatNumber(count)} (${pct}%)</span>
                </div>
            `;
        })
        .join("");
}
