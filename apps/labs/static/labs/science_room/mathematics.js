// https://openstax.org/books/algebra-1/pages/4-7-3-writing-linear-equations
// https://www.itl.nist.gov/div898/handbook/eda/section3/eda366i.htm
function bounded(raw, low, high, fallback) {
    const n = Number(raw);
    return Number.isFinite(n) && raw != null ? Math.min(high, Math.max(low, n)) : fallback;
}
const fmt = (n, digits = 2) => n.toLocaleString("az-AZ", { maximumFractionDigits: digits });
function txt(x, y, caption, size = 13, color = "#354e55", anchor = "start") {
    return `<text x="${x}" y="${y}" font-size="${size}" fill="${color}" text-anchor="${anchor}" font-family="system-ui,sans-serif">${caption}</text>`;
}
function linear(state) {
    const m = bounded(state.slope, -3, 3, 1);
    const b = bounded(state.intercept, -4, 4, 1);
    const x = bounded(state.point, -3, 3, 1);
    const y = m * x + b;
    const pairs = state.tool !== "intercepts";
    const unit = 25,
        x0 = 207,
        y0 = 166,
        xLimit = 6;
    const yStep = 4; // Keep both axis scales fixed as the slope changes.
    const X = (n) => x0 + n * unit;
    const Y = (n) => y0 - (n * unit) / yStep;
    const equation =
        "y = " +
        (m === 0
            ? fmt(b)
            : `${m === 1 ? "" : m === -1 ? "−" : fmt(m)}x${b ? (b > 0 ? " + " : " − ") + fmt(Math.abs(b)) : ""}`);
    const grid = [];
    for (let i = -xLimit; i <= xLimit; i++) {
        grid.push(`<path d="M${X(i)} 58v210" stroke="#d4e0d9"/>`);
        if (i % 2 === 0 && i !== 0) grid.push(txt(X(i), 285, fmt(i), 11, "#49616a", "middle"));
    }
    for (let i = -4; i <= 4; i++) {
        grid.push(`<path d="M56 ${Y(i * yStep)}h302" stroke="#d4e0d9"/>`);
        if (i % 2 === 0) grid.push(txt(45, Y(i * yStep) + 4, fmt(i * yStep), 11, "#49616a", "end"));
    }
    const root = m === 0 ? null : -b / m;
    const rootText = root !== null ? fmt(root) : b === 0 ? "Bütün həqiqi ədədlər" : "Kəsişmir";
    const pulse =
        state.runs > 0 && !globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches
            ? `<animate attributeName="r" values="5;8;5" dur=".8s" repeatCount="2"/>`
            : "";
    const point = (xv, yv, color) =>
        `<circle cx="${X(xv)}" cy="${Y(yv)}" r="5" fill="${color}" stroke="#f9faf2" stroke-width="2">${pulse}</circle>`;
    const deltaMarkup = `<path d="M${X(x)} ${Y(y)}h${unit}v${(-m * unit) / yStep}" stroke="#b0653c" stroke-dasharray="4 3" fill="none" stroke-width="2"/>
        ${point(x, y, "#98552e")}${point(x + 1, y + m, "#98552e")}`;
    const interceptMarkup =
        point(x, y, "#547c8a") +
        point(0, b, "#a66538") +
        (root !== null && Math.abs(root) <= xLimit ? point(root, 0, "#8b526d") : "");
    const a = pairs ? `A (${fmt(x)}; ${fmt(y)})` : `Oy · (0; ${fmt(b)})`;
    const c = pairs ? `B (${fmt(x + 1)}; ${fmt(y + m)})` : `Ox · ${rootText}`;
    const svg = `<rect width="640" height="340" rx="12" fill="#f4f5ef"/>${txt(29, 35, "KOORDİNAT MÜSTƏVİSİ", 12)}
        <rect x="53" y="54" width="309" height="219" rx="6" fill="#fafbf5" stroke="#b9cbc2"/>
        <defs><clipPath id="math-graph-area"><rect x="55" y="56" width="305" height="215" rx="4"/></clipPath></defs>
        ${grid.join("")}<path d="M55 ${y0}h303m-4-3l4 3-4 3M${x0} 267V59m-3 4l3-4 3 4" fill="none" stroke="#66807c" stroke-width="1.5"/>
        ${txt(364, y0 + 5, "x", 13)}${txt(x0 + 8, 68, "y", 13)}
        <g clip-path="url(#math-graph-area)"><path d="M${X(-xLimit)} ${Y(-xLimit * m + b)}L${X(xLimit)} ${Y(xLimit * m + b)}" stroke="#197f78" stroke-width="3.5" fill="none"/>
        ${pairs ? deltaMarkup : interceptMarkup}</g>
        <rect x="391" y="63" width="224" height="90" rx="9" fill="#294d4c"/>
        ${txt(408, 89, "FUNKSİYA", 11, "#c1d8cb")}${txt(408, 129, equation, 25, "#f4f7e6")}
        ${txt(395, 186, pairs ? "Seçilən nöqtələr" : "Oxlarla kəsişmə", 13)}
        <circle cx="403" cy="217" r="4.5" fill="#a66538"/>${txt(418, 222, a, 16)}
        <circle cx="403" cy="249" r="4.5" fill="${pairs ? "#a66538" : "#8b526d"}"/>${txt(418, 254, c, 15)}
        <path d="M30 297h578" stroke="#c6d4ca"/>
        ${txt(32, 323, `Bir şaquli bölgü · ${fmt(yStep)} vahid`, 13)}${txt(607, 323, "y = mx + b", 15, "#386864", "end")}`;
    return {
        svg,
        results: [
            { label: "Meyl əmsalı", value: fmt(m) },
            { label: "Seçilən nöqtədə y", value: fmt(y) },
            { label: "Oy oxunu kəsdiyi nöqtə", value: `(0; ${fmt(b)})` },
            pairs
                ? { label: "x bir vahid artanda y dəyişməsi", value: fmt(m) }
                : { label: "y = 0 tənliyinin həlli", value: rootText }
        ],
        explanation: pairs
            ? `A nöqtəsindən B nöqtəsinə keçəndə x bir vahid artır. y qiyməti ${fmt(y)}-dən ${fmt(y + m)}-ə keçir. Bu fərq meyl əmsalına bərabərdir.`
            : `Oy oxunda x sıfırdır, ona görə y = ${fmt(b)} alınır. Ox oxu ilə kəsişməni tapmaq üçün y-ni sıfıra bərabərləşdirin.`
    };
}
function generator(seed) {
    let current = seed >>> 0;
    return () => {
        current = (Math.imul(1664525, current) + 1013904223) >>> 0;
        return current / 4294967296;
    };
}
const pips = {
    1: [[0, 0]],
    2: [
        [-1, -1],
        [1, 1]
    ],
    3: [
        [-1, -1],
        [0, 0],
        [1, 1]
    ],
    4: [
        [-1, -1],
        [1, -1],
        [-1, 1],
        [1, 1]
    ],
    5: [
        [-1, -1],
        [1, -1],
        [0, 0],
        [-1, 1],
        [1, 1]
    ],
    6: [
        [-1, -1],
        [1, -1],
        [-1, 0],
        [1, 0],
        [-1, 1],
        [1, 1]
    ]
};
function die(face) {
    return `<path d="M57 110l70-19 36 24-70 20z" fill="#e0d3b6" stroke="#829084"/>
        <path d="M127 112l36-14v75l-32 22z" fill="#c5baa2" stroke="#829084"/>
        <rect x="55" y="111" width="82" height="82" rx="13" fill="#faf3df" stroke="#738476" stroke-width="2"/>
        ${pips[face].map(([x, y]) => `<circle cx="${96 + 21 * x}" cy="${152 + 21 * y}" r="5" fill="#53695f"/>`).join("")}`;
}
function coin(face) {
    const emblem =
        face === 0
            ? `<path d="M93 121l6 13 15 2-11 11 3 15-13-7-13 7 3-15-11-11 15-2z" fill="#f9dea4"/>`
            : txt(93, 157, "1", 38, "#fbdfa4", "middle");
    return `<circle cx="97" cy="152" r="43" fill="#a47e45"/><circle cx="93" cy="146" r="43" fill="#cfa45f" stroke="#98753e" stroke-width="2"/>
        <circle cx="93" cy="146" r="35" fill="none" stroke="#f5d794" stroke-width="1.7"/>
        <circle cx="93" cy="146" r="31" fill="none" stroke="#ae874a" stroke-dasharray="2 3"/>${emblem}`;
}
function probability(state) {
    const dice = state.tool === "die";
    const sides = dice ? 6 : 2;
    const n = Math.round(bounded(state.trials, 10, 500, 100));
    const runs = Math.floor(bounded(state.runs, 0, 2147483647, 0));
    const labels = dice ? ["1", "2", "3", "4", "5", "6"] : ["Gerb", "Rəqəm"];
    const target = dice ? 5 : 0;
    const counts = Array(sides).fill(0);
    const next = generator((Math.imul(runs, 2654435761) ^ (dice ? 0x973aac11 : 0x5cb49f63)) >>> 0);
    let last = 0;
    if (runs) {
        for (let i = 0; i < n; i++) {
            last = Math.floor(next() * sides);
            counts[last]++;
        }
    }
    const expected = n / sides;
    const top = Math.max(1, Math.ceil(Math.max(expected, ...counts) * 1.24));
    const baseline = 243,
        scale = 124 / top,
        step = 303 / sides;
    const bars = counts
        .map((count, i) => {
            const x = 248 + (i + 0.5) * step,
                h = count * scale;
            const w = Math.min(55, step * 0.52);
            return `<rect x="${x - w / 2}" y="${baseline - h}" width="${w}" height="${h}" rx="3" fill="${i === target ? "#217d74" : "#90ad9f"}"/>
            ${runs ? txt(x, baseline - h - 8, String(count), 13, "#34584f", "middle") : ""}${txt(x, 264, labels[i], 13, "#50665d", "middle")}`;
        })
        .join("");
    const yExpected = baseline - expected * scale;
    const relative = runs ? `${fmt((100 * counts[target]) / n, 1)} %` : "Sınağı başladın";
    const svg = `<rect width="640" height="340" rx="12" fill="#f7f5eb"/>${txt(31, 35, "TƏSADÜFİ SINAQ", 12)}
        <rect x="24" y="58" width="162" height="217" rx="12" fill="#e6ecdf"/>
        ${txt(105, 87, dice ? "Altıüzlü zər" : "Sikkə", 15, "#375449", "middle")}
        ${dice ? die(runs ? last + 1 : 6) : coin(runs ? last : 0)}
        ${txt(105, 226, runs ? "Son atış" : "Sınaq aləti", 12, "#506a5d", "middle")}
        ${runs ? txt(105, 252, labels[last], 19, "#334f43", "middle") : ""}
        ${txt(228, 78, "Nəticələrin sayı", 17)}
        <path d="M247 102v141h313" stroke="#91a399" fill="none"/>
        ${txt(237, 247, "0", 11, "#567065", "end")}
        ${bars}<path d="M248 ${yExpected}h310" stroke="#a8773e" stroke-width="1.5" stroke-dasharray="5 4"/>
        ${txt(566, yExpected + 4, fmt(expected, 1), 12, "#805e37")}
        <path d="M32 297h577" stroke="#c4d0bf"/>
        <path d="M34 318h26" stroke="#a8773e" stroke-width="2" stroke-dasharray="5 4"/>
        ${txt(69, 323, "Hər nəticənin gözlənilən sayı", 13)}${txt(608, 323, `${fmt(n, 0)} atış`, 15, "#39675a", "end")}`;
    return {
        svg,
        results: [
            { label: dice ? "6 düşməsi ehtimalı" : "Gerb düşməsi ehtimalı", value: dice ? "1/6" : "1/2" },
            { label: "Gözlənilən say", value: fmt(expected, 2) },
            { label: "Müşahidə edilən say", value: runs ? String(counts[target]) : "Sınağı başladın" },
            { label: "Nisbi tezlik", value: relative }
        ],
        explanation: runs
            ? `${n} atışdan ${counts[target]}-də ${dice ? "6" : "gerb"} düşdü. Nisbi tezlik ${relative}-dir. Yeni sınaqda dəyişə bilər.`
            : `${dice ? "Simmetrik zərdə hər üzün" : "Simmetrik sikkədə hər tərəfin"} ehtimalı 1/${sides}-dir. Sınağı başladıb sütunları gözlənilən say xətti ilə müqayisə edin.`
    };
}
export const experiments = {
    linear: {
        title: "Xətti funksiyanın qrafiki",
        prompt: "Meyl əmsalını dəyişəndə xətt necə dönür? Sərbəst hədd qrafiki hara aparır?",
        setup: "Qrafikdə iki nöqtəni və ya oxlarla kəsişmələri seçin. m və b əmsallarını dəyişin. Sınağı başladıb ölçülən nöqtələri izləyin.",
        tools: [
            { id: "points", label: "İki nöqtə" },
            { id: "intercepts", label: "Oxlarla kəsişmə" }
        ],
        controls: [
            { id: "slope", label: "Meyl əmsalı (m)", min: -3, max: 3, step: 0.25, value: 1, unit: "" },
            { id: "intercept", label: "Sərbəst hədd (b)", min: -4, max: 4, step: 0.5, value: 1, unit: "" },
            { id: "point", label: "A nöqtəsinin x koordinatı", min: -3, max: 3, step: 0.5, value: 1, unit: "" }
        ],
        defaults: { tool: "points" },
        render: linear
    },
    probability: {
        title: "Ehtimal və nisbi tezlik",
        prompt: "Atışları çoxaltdıqda müşahidə etdiyiniz tezlik nəzəri ehtimala necə yaxınlaşır?",
        setup: "Sikkə və ya zəri seçin. Hər sınaqdakı atış sayını qurun və bir neçə sınaq keçirin. Seçilmiş nəticənin sayını gözlənti ilə müqayisə edin.",
        tools: [
            { id: "coin", label: "Sikkə" },
            { id: "die", label: "Zər" }
        ],
        controls: [
            {
                id: "trials",
                label: "Bir sınaqdakı atış sayı",
                min: 10,
                max: 500,
                step: 10,
                value: 100,
                unit: "atış"
            }
        ],
        defaults: { tool: "coin" },
        render: probability
    }
};
