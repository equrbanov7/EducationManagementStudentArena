// Relative lunar phase uses the mean synodic month and parallel sunlight.
// https://science.nasa.gov/moon/moon-phases/
// https://science.nasa.gov/earth/facts/
// Solar declination and equation of time follow NOAA's non-leap-year approximation.
// https://gml.noaa.gov/grad/solcalc/solareqns.PDF
const RAD = Math.PI / 180;
const LUNATION = 29.53059;
const MONTHS = [
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avqust",
    "sentyabr",
    "oktyabr",
    "noyabr",
    "dekabr"
];
const mod = (n, base) => ((n % base) + base) % base;
const fmt = (n, precision = 1) => n.toLocaleString("az-AZ", { maximumFractionDigits: precision });
function bounded(raw, min, max, fallback) {
    const n = Number(raw);
    return raw != null && Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}
function runCount(raw) {
    return Math.floor(bounded(raw, 0, 1000000, 0));
}
function text(x, y, caption, size = 13, color = "#dce8ed", anchor = "start") {
    return `<text x="${x}" y="${y}" fill="${color}" font-size="${size}" text-anchor="${anchor}" font-family="system-ui,sans-serif">${caption}</text>`;
}
function phaseName(angle) {
    const closest = Math.round(angle / 90);
    if (Math.abs(angle - closest * 90) < 0.6)
        return ["Yeni ay", "İlk rüb", "Bədirlənmiş ay", "Son rüb", "Yeni ay"][closest];
    if (angle < 90) return "Böyüyən hilal";
    if (angle < 180) return "Böyüyən qabarıq Ay";
    if (angle < 270) return "Kiçilən qabarıq Ay";
    return "Kiçilən hilal";
}
function litFace(cx, cy, r, angle) {
    // At latitude y on the apparent disc the terminator lies at cos(angle) × half-width.
    const east = angle <= 180 ? 1 : -1;
    const cosine = Math.cos(angle * RAD);
    const edge = [],
        divider = [];
    for (let i = 0; i <= 48; i++) {
        const a = -Math.PI / 2 + (i * Math.PI) / 48;
        const y = cy + r * Math.sin(a),
            width = r * Math.cos(a);
        edge.push(`${(cx + east * width).toFixed(2)},${y.toFixed(2)}`);
        divider.push(`${(cx + east * cosine * width).toFixed(2)},${y.toFixed(2)}`);
    }
    return `M${edge.join("L")}L${divider.reverse().join("L")}Z`;
}
function moonphase(state) {
    const runs = runCount(state.runs);
    const degrees = bounded(state.phase, 0, 360, 90);
    const step = bounded(state.days, 0.5, 3, 1);
    const angle = mod(degrees + (360 * mod(runs * step, LUNATION)) / LUNATION, 360);
    const a = angle * RAD,
        fraction = (1 - Math.cos(a)) / 2;
    const age = (angle * LUNATION) / 360;
    const name = phaseName(angle);
    const grid = state.tool === "grid";
    const cx = 154,
        cy = 170,
        radius = 78;
    const mx = cx + radius * Math.cos(a),
        my = cy - radius * Math.sin(a);
    const lx = 474,
        ly = 160,
        lr = 69,
        face = litFace(lx, ly, lr, angle);
    const marks = [
        [38, 78],
        [69, 237],
        [258, 78],
        [105, 53],
        [295, 202],
        [228, 237],
        [47, 170],
        [308, 99]
    ]
        .map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.4" fill="#a3b9c4" opacity=".75"/>`)
        .join("");
    const arrows = [-14, 0, 14]
        .map(
            (offset) =>
                `<path d="M309 ${cy + offset}h-44m6-3-6 3 6 3" fill="none" stroke="#dfb56f" stroke-width="1.6"/>`
        )
        .join("");
    const gridLines = grid
        ? [-48, -32, -16, 0, 16, 32, 48]
              .map(
                  (d) =>
                      `<path d="M${lx + d} ${ly - lr}v${2 * lr}M${lx - lr} ${ly + d}h${2 * lr}" fill="none" stroke="#607f83" stroke-opacity=".65" stroke-width=".9"/>`
              )
              .join("")
        : "";
    const craters = [
        [454, 123, 8],
        [488, 125, 4],
        [503, 158, 11],
        [443, 179, 13],
        [483, 195, 6],
        [461, 160, 5],
        [520, 183, 5]
    ]
        .map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="#979e96" opacity=".4"/>`)
        .join("");
    const svg = `<rect width="640" height="340" rx="12" fill="#152a39"/>
        <defs><clipPath id="astro-lit-face"><path d="${face}"/></clipPath><clipPath id="astro-moon-disc"><circle cx="${lx}" cy="${ly}" r="${lr}"/></clipPath></defs>
        <path d="M333 32v265" stroke="#45606b"/>${marks}
        ${text(24, 36, "ORBİTƏ YUXARIDAN BAXIŞ", 12, "#c4d9dc")}${text(356, 36, "YERDƏN GÖRÜNÜŞ", 12, "#c4d9dc")}
        <circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="#819ba8" stroke-width="1.5" stroke-dasharray="3 4"/>
        <path d="M${cx} ${cy}L${mx} ${my}" stroke="#739497" stroke-width="1.5"/>
        <circle cx="${cx}" cy="${cy}" r="20" fill="#3d737d"/><path d="M154 150a20 20 0 0 1 0 40z" fill="#70b1bc"/>
        <path d="M159 153l6 6-4 5 6 3-2 7-6 5-1-10-5-5z" fill="#b5c5a6"/>
        ${text(147, cy + 39, "Yer", 13, "#dce8ed", "end")}
        ${arrows}<circle cx="317" cy="${cy}" r="10" fill="#f0c47a"/>
        ${text(284, cy + 34, "Günəş", 12, "#efcf99", "middle")}
        <circle cx="${mx}" cy="${my}" r="11" fill="#516673" stroke="#c0c7bc"/>
        <path d="M${mx} ${my - 10.5}a10.5 10.5 0 0 1 0 21z" fill="#e6e3cc"/>
        <circle cx="${lx}" cy="${ly}" r="${lr + 4}" fill="none" stroke="#749297" stroke-dasharray="${grid ? "3 3" : "1 12"}"/>
        <circle cx="${lx}" cy="${ly}" r="${lr}" fill="#344650"/>
        <path d="${face}" fill="#ebe7d2"/><g clip-path="url(#astro-lit-face)">${craters}</g>
        <g clip-path="url(#astro-moon-disc)">${gridLines}</g>
        ${text(lx, 257, name, 18, "#eef1e6", "middle")}
        <path d="M359 282h230" stroke="#4d6570" stroke-width="5" stroke-linecap="round"/>
        ${fraction > 0.00001 ? `<path d="M359 282h${230 * fraction}" stroke="#d9c394" stroke-width="5" stroke-linecap="round"/>` : ""}
        ${text(25, 315, `Yeni aydan · ${fmt(age)} gün`, 14)}${text(604, 315, `İşıqlı sahə · ${fmt(fraction * 100)} %`, 14, "#e9dfbf", "end")}`;
    return {
        svg,
        results: [
            { label: "Ayın fazası", value: name },
            { label: "Görünən diskin işıqlı hissəsi", value: `${fmt(fraction * 100)} %` },
            { label: "Yeni aydan keçən vaxt", value: `${fmt(age, 2)} gün` },
            { label: "Dövr üzrə bucaq", value: `${fmt(angle)}°` }
        ],
        explanation: `Günəş Ayın bir yarısını işıqlandırır. Bu mövqedə Yerdən görünən diskin ${fmt(fraction * 100)} faizi işıqlıdır. ${grid ? "Torun xanaları işıqlı və qaranlıq sahələri müqayisə etməyə kömək edir." : "Teleskop görünüşündə astronomik şimal yuxarıdır."}`
    };
}
function noonOn(day, latitude, longitude) {
    const gamma = (2 * Math.PI * (day - 1)) / 365;
    const c = Math.cos,
        s = Math.sin;
    const decl =
        (0.006918 -
            0.399912 * c(gamma) +
            0.070257 * s(gamma) -
            0.006758 * c(2 * gamma) +
            0.000907 * s(2 * gamma) -
            0.002697 * c(3 * gamma) +
            0.00148 * s(3 * gamma)) /
        RAD;
    const equation =
        229.18 *
        (0.000075 + 0.001868 * c(gamma) - 0.032077 * s(gamma) - 0.014615 * c(2 * gamma) - 0.040849 * s(2 * gamma));
    const minutes = Math.round(720 - 4 * longitude - equation);
    const normalized = mod(minutes, 1440),
        shift = Math.floor(minutes / 1440);
    const utc = `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${String(normalized % 60).padStart(2, "0")}${shift < 0 ? " (əvvəlki gün)" : shift > 0 ? " (sonrakı gün)" : ""}`;
    return { decl, altitude: 90 - Math.abs(latitude - decl), utc };
}
function seasons(state) {
    const run = runCount(state.runs);
    const initialDay = Math.round(bounded(state.day, 1, 365, 172));
    const day = 1 + mod(initialDay - 1 + run * 7, 365);
    const lat = bounded(state.latitude, -80, 80, 40);
    const lon = bounded(state.longitude, -180, 180, 50);
    const instrument = state.tool === "tall" ? 2 : 1;
    const { decl, altitude, utc } = noonOn(day, lat, lon);
    const above = altitude > 0.001;
    const isVertical = altitude > 89.999;
    const length = above ? instrument / Math.tan(altitude * RAD) : 0;
    const direction = lat >= decl ? 1 : -1;
    const shadowDir = !above || isVertical ? "—" : direction === 1 ? "Şimal" : "Cənub";
    const date = new Date(Date.UTC(2025, 0, day));
    const caption = `${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}`;
    const baseX = 314,
        ground = 246,
        unit = 52,
        top = ground - instrument * unit;
    const shadowPixels = Math.min(244, unit * length);
    const shadowEnd = baseX + direction * shadowPixels;
    const rayEndY = above ? Math.min(ground, top + shadowPixels * Math.tan(altitude * RAD)) : ground;
    const solarX = baseX - direction * 115 * Math.cos(altitude * RAD);
    const solarY = above ? top - 115 * Math.sin(altitude * RAD) : ground + 1 + Math.min(14, -0.45 * altitude);
    const stars = [
        [34, 84],
        [112, 111],
        [182, 59],
        [299, 88],
        [415, 58],
        [506, 120],
        [587, 66]
    ]
        .map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.3" fill="#cfdee1"/>`)
        .join("");
    const skyline = `<path d="M0 231l54-13 42 8 54-13 39 12 56-7 65 7 46-5 66 6 52-17 79 17 53-8 34 8v23H0z" fill="${above ? "#bac9b2" : "#3b5255"}"/>`;
    const extension = unit * length > 244 ? text(shadowEnd, ground - 5, "…", 15, "#385650", "middle") : "";
    const rods = Array.from(
        { length: instrument * 5 },
        (_, i) => `<path d="M${baseX - 3} ${ground - i * (unit / 5)}h${i % 5 === 0 ? 8 : 5}" stroke="#c5d5ca"/>`
    ).join("");
    const svg = `<rect width="640" height="340" rx="12" fill="${above ? "#e8f2eb" : "#213744"}"/>
        ${above ? "" : stars}${text(26, 35, "YERLİ GÜNƏŞ GÜNORTASI", 12, above ? "#41665f" : "#d9e4e1")}
        ${text(610, 35, caption, 15, above ? "#3a5d59" : "#dde6e4", "end")}
        ${skyline}<path d="M0 ${ground}h640v94H0z" fill="${above ? "#e3dfc8" : "#d4d2bd"}"/>
        <path d="M0 ${ground}h640" stroke="#8d9d85" stroke-width="2"/>
        ${
            above
                ? `<path d="M${solarX} ${solarY}L${baseX} ${top}L${shadowEnd} ${rayEndY}" fill="none" stroke="#bd8e39" stroke-width="1.7" stroke-dasharray="5 4"/>
        <circle cx="${solarX}" cy="${solarY}" r="23" fill="#efd28a" opacity=".42"/><circle cx="${solarX}" cy="${solarY}" r="13" fill="#e4a738" stroke="#cb902a"/>
        <path d="M${baseX} ${ground + 2}H${shadowEnd}" stroke="#68776c" stroke-width="6" stroke-linecap="round"/>${extension}`
                : text(320, 106, "Günəş üfüqün altındadır", 18, "#dce4dd", "middle")
        }
        <path d="M${baseX} ${ground}V${top}" stroke="#35564e" stroke-width="7" stroke-linecap="round"/>${rods}
        ${text(baseX + 10, top + 22, `${instrument} m`, 14, above ? "#3c554e" : "#e7ede5")}
        ${text(29, 267, "Cənub", 13, "#4e6659")}${text(607, 267, "Şimal", 13, "#4e6659", "end")}
        <path d="M31 286h578" stroke="#b1baa5"/>
        ${text(31, 315, `Günəşin hündürlüyü · ${fmt(altitude)}°`, 14, "#334e49")}
        ${text(608, 315, `Günorta · ${utc} UTC`, 14, "#334e49", "end")}`;
    return {
        svg,
        results: [
            { label: "Günəşin üfüqdən hündürlüyü", value: `${fmt(altitude, 2)}°` },
            { label: "Kölgənin uzunluğu", value: above ? `${fmt(length, 2)} m` : "Kölgə yoxdur" },
            { label: "Kölgənin istiqaməti", value: shadowDir },
            { label: "Günəşin meyli", value: `${fmt(decl, 2)}°` },
            { label: "Günəş günortası (UTC)", value: utc }
        ],
        explanation: above
            ? `${caption} tarixində Günəş meridiandan ${fmt(altitude)}° hündürlükdə keçir. Şaquli ${instrument} metrlik çubuğun üfüqi səthdə kölgəsi təxminən ${fmt(length, 2)} m olur. UTC vaxtı uzunluq dairəsi və zaman tənliyi ilə hesablanıb.`
            : `${caption} tarixində bu enlikdə Günəş yerli günorta da üfüqün altındadır. Birbaşa Günəş şüası çubuğa çatmır.`
    };
}
export const experiments = {
    moonphase: {
        title: "Ayın fazaları",
        prompt: "Ayın Yer ətrafındakı mövqeyi dəyişəndə işıqlı hissəsi necə görünür?",
        setup: "Teleskopu və ya ölçü torunu yerləşdirin. Başlanğıc bucağını seçin. Hər sınaq Ayı seçilmiş qədər gün irəli aparır. Model orta 29,53 günlük faza dövrünü göstərir.",
        tools: [
            { id: "telescope", label: "Teleskop" },
            { id: "grid", label: "Sahə ölçən tor" }
        ],
        controls: [
            { id: "phase", label: "Başlanğıc faza bucağı", min: 0, max: 360, step: 5, value: 90, unit: "°" },
            { id: "days", label: "Hər sınaqda keçən vaxt", min: 0.5, max: 3, step: 0.5, value: 1, unit: "gün" }
        ],
        defaults: { tool: "telescope" },
        render: moonphase
    },
    seasons: {
        title: "Fəsillər və günorta kölgəsi",
        prompt: "Eyni çubuğun günorta kölgəsi Bakıda və cənub yarımkürəsində niyə fərqlənir?",
        setup: "Yer oxunun təxminən 23,4° meyli Günəşin il ərzində günorta hündürlüyünü dəyişir. Şaquli çubuğu yerləşdirib enliyi, uzunluğu və başlanğıc günü seçin. Şimal və şərq müsbət işarəlidir. Hər sınaq 365 günlük il modelində tarixi bir həftə irəli aparır.",
        tools: [
            { id: "short", label: "1 metrlik çubuq" },
            { id: "tall", label: "2 metrlik çubuq" }
        ],
        controls: [
            { id: "latitude", label: "Coğrafi enlik", min: -80, max: 80, step: 1, value: 40, unit: "°" },
            { id: "longitude", label: "Coğrafi uzunluq", min: -180, max: 180, step: 1, value: 50, unit: "°" },
            {
                id: "day",
                label: "Başlanğıc gün (ilin 1–365-ci günü)",
                min: 1,
                max: 365,
                step: 1,
                value: 172,
                unit: ""
            }
        ],
        defaults: { tool: "short" },
        render: seasons
    }
};
