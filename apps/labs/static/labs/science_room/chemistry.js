// Teaching references: ACS Red Cabbage Indicator and Middle School Chemistry, lesson 6.2.
const samples = [
    {name: "Təmiz su", kind: "Neytral", shade: "Göy-bənövşəyi", color: "#67539d", raw: "#d5ebeb"},
    {name: "Alma şirəsi", kind: "Turş", shade: "Çəhrayı", color: "#d2527a", raw: "#eebe66"},
    {name: "Limon şirəsi", kind: "Turş", shade: "Çəhrayı-qırmızı", color: "#bb4055", raw: "#ead982"},
    {name: "Soda məhlulu", kind: "Zəif qələvi", shade: "Göy-yaşıl", color: "#36847f", raw: "#cde4e5"},
];

function bounded(value, fallback, min, max) {
    const number = Number(value ?? fallback);
    return Number.isFinite(number) ? Math.min(max, Math.max(min, number)) : fallback;
}

function amount(number, digits = 0) {
    return number.toFixed(digits).replace(".", ",");
}

function bench() {
    return `<defs>
      <linearGradient id="che-wall" x2="0" y2="1" gradientUnits="objectBoundingBox">
        <stop stop-color="#f9f4e9"/><stop offset="1" stop-color="#e4ede8"/></linearGradient>
      <linearGradient id="che-wood" x2="0" y2="1"><stop stop-color="#dcb88a"/><stop offset="1" stop-color="#ad8261"/></linearGradient>
      <linearGradient id="che-glass"><stop stop-color="#c4e4e5" stop-opacity=".48"/><stop offset=".32" stop-color="#fff" stop-opacity=".09"/>
        <stop offset=".8" stop-color="#fff" stop-opacity=".12"/><stop offset="1" stop-color="#729e9c" stop-opacity=".48"/></linearGradient>
    </defs><rect width="640" height="340" rx="15" fill="url(#che-wall)"/>
    <path d="M0 62H640M0 124H640M0 186H640M80 0V62M238 0V62M396 0V62M554 0V62M0 62V124M159 62V124M317 62V124M475 62V124M80 124V186M238 124V186M396 124V186M554 124V186"
      stroke="#839f97" opacity=".13" fill="none"/>
    <path d="M0 265H640V340H0Z" fill="url(#che-wood)"/><path d="M0 279H640M0 332H640" stroke="#9e765b" opacity=".55"/> `;
}

function beaker(liquid, height) {
    const surface = 258 - height;
    const fluid = height > 0 ? `<path d="M218 ${surface}Q264 ${surface + 5} 309 ${surface}L303 251Q299 259 291 259H237Q228 259 226 252Z"
      fill="${liquid}" opacity=".86"/><ellipse cx="263" cy="${surface}" rx="45" ry="4" fill="${liquid}"/>` : "";
    return `<ellipse cx="267" cy="268" rx="70" ry="7" fill="#584938" opacity=".16"/>
      <path d="M207 138H321L315 147L308 252Q306 265 293 265H236Q222 265 221 253L214 149Z"
        fill="url(#che-glass)" stroke="#42646b" stroke-width="3" stroke-linejoin="round"/>
      ${fluid}<path d="M224 151L230 244" stroke="#fff" stroke-width="3" opacity=".85"/>
      <path d="M303 163h11m-8 15h7m-11 15h10m-8 15h7m-11 15h10m-8 15h7" fill="none" stroke="#536c6b" stroke-width="2"/>`;
}

function legend() {
    return `<g class="sci-cb-label"><rect x="405" y="99" width="193" height="141" rx="10" fill="#fffbf2" stroke="#c8c2ac"/>
      <text x="421" y="124" font-weight="700">Kələm indikatoru</text>
      <circle cx="431" cy="151" r="9" fill="#cf5b78"/><text x="451" y="157">Turş</text>
      <rect x="422" y="174" width="18" height="16" rx="3" fill="#67539d"/><text x="451" y="188">Neytral</text>
      <path d="m431 204 10 16h-20z" fill="#36847f"/><text x="451" y="220">Zəif qələvi</text></g>`;
}

function indicator(state) {
    const sample = samples[Math.round(bounded(state.sample, 2, 1, 4)) - 1];
    const strip = state.tool === "strip";
    const tested = state.runs > 0;
    const swatch = tested ? sample.color : "#67539d";
    const glassColor = tested && !strip ? sample.color : sample.raw;
    const tool = strip ? `<g transform="rotate(12 267 165)">
      <rect x="253" y="56" width="21" height="144" rx="3" fill="#faf3d5" stroke="#887e68" stroke-width="2"/>
      <rect x="254" y="157" width="19" height="42" rx="1" fill="${swatch}"/>
      <path d="M257 66h13m-13 7h13m-13 7h13" stroke="#b1a58a"/></g>` :
        `<g transform="rotate(30 271 112)"><rect x="260" y="31" width="24" height="35" rx="10" fill="#81527e" stroke="#503c56" stroke-width="2"/>
        <path d="M264 64h16v49l-6 16h-4l-6-16Z" fill="#f5eff7" stroke="#626677" stroke-width="2"/>
        <path d="M268 83h8v29l-4 11-4-11Z" fill="#87618f"/></g>
        ${tested ? '<path class="sci-cb-drop" d="M262 135q-11 15-1 17q11-1 1-17" fill="#79518d"/>' : ''}`;
    return {
        svg: `${bench()}<g stroke="#626658" stroke-width="2">
          <path d="M67 155h38v18l13 13v67q0 7-8 7H60q-8 0-8-7v-66l15-14Z" fill="#744e78"/>
          <rect x="66" y="145" width="40" height="15" rx="3" fill="#c7a98b"/>
          <rect x="55" y="201" width="60" height="33" fill="#f8edda"/></g>
          <text x="85" y="222" text-anchor="middle" class="sci-cb-small">İndikator</text>
          ${beaker(glassColor, 68)}${tool}${legend()}
          <text x="265" y="301" text-anchor="middle" class="sci-cb-caption">${sample.name}</text>`,
        results: [
            {label: "Nümunə", value: sample.name},
            {label: "İndikatorun rəngi", value: tested ? sample.shade : "Sınaq gözlənilir"},
            {label: "Mühit", value: tested ? sample.kind : "—"},
        ],
        explanation: tested
            ? `${strip ? "Kağızdakı" : "Mayedəki"} kələm piqmenti üçün gözlənilən rəng göstərilir. Şirənin öz rəngi və nümunənin tərkibi çaları dəyişə bilər. Bu üsul mühiti təxmini ayırır.`
            : "Nümunəni seçin, sonra indikatoru pipetlə əlavə edin və ya kələm indikatorlu kağızı batırın.",
    };
}

function bubbles(state) {
    const vinegar = bounded(state.vinegar, 20, 0, 40);
    const soda = bounded(state.soda, 1, 0, 3);
    // 5 g CH3COOH per 100 mL. One mole of each reactant gives at most one mole of carbon dioxide.
    const acidMol = vinegar * 0.05 / 60.052;
    const sodaMol = soda / 84.007;
    const mass = Math.min(acidMol, sodaMol) * 44.01;
    const active = state.runs > 0 && mass > 0;
    const bubblesCount = active ? Math.ceil(3 + mass * 6) : 0;
    const magnify = state.tool === "lens";
    const liquidHeight = vinegar > 0 ? 16 + vinegar * 1.6 : 0;
    const particles = Array.from({length: bubblesCount}, (_, i) =>
        `<circle class="sci-cb-bubble" cx="${237 + (i * 23) % 49}" cy="${251 - (i * 13) % Math.max(9, liquidHeight - 3)}" r="${2 + i % 3}"/>`).join("");
    let limit = "Hər iki maddə yoxdur";
    if (acidMol || sodaMol) {
        limit = Math.abs(acidMol - sodaMol) < 1e-10 ? "Hər ikisi tam sərf olunur"
            : (acidMol < sodaMol ? "Sirkə turşusu" : "Qida sodası");
    }
    const tool = magnify ? `<g transform="rotate(-30 469 179)"><path d="M464 208h11v56h-11z" fill="#85654d"/>
      <circle cx="470" cy="167" r="46" fill="#eafafa" stroke="#486265" stroke-width="7"/>
      ${active ? '<g class="sci-cb-bubbles"><circle cx="459" cy="172" r="11"/><circle cx="477" cy="148" r="7"/><circle cx="487" cy="182" r="5"/></g>' : ''}
      <path d="M443 154q4-14 20-19" fill="none" stroke="white" stroke-width="4"/></g>` :
        `<g><path d="M438 98h37l-5 8v138h-25V107Z" fill="url(#che-glass)" stroke="#54717a" stroke-width="3"/>
        <path d="M447 ${238 - vinegar * 2.8}h21v143H447Z" fill="#a3cdd0" clip-path="url(#che-cylinder)"/>
        <defs><clipPath id="che-cylinder"><rect x="447" y="104" width="21" height="138"/></clipPath></defs>
        <path d="M441 248h34l9 9h-54z" fill="#7eaaa6"/><path d="M462 118h7m-5 17h5m-7 17h7m-5 17h5m-7 17h7m-5 17h5m-7 17h7" stroke="#506d70" stroke-width="2"/></g>`;
    return {
        svg: `${bench()}${beaker("#bddfe0", liquidHeight)}<g class="sci-cb-bubbles">${particles}</g>
          <g><path d="M57 211l8-54h63l7 54v41H57Z" fill="#eee3ce" stroke="#947f67" stroke-width="2"/>
          <path d="M65 158h63l-4 13H68Z" fill="#83a5a1"/><rect x="63" y="194" width="65" height="36" rx="3" fill="#fffcf3"/>
          <text x="95" y="217" text-anchor="middle" class="sci-cb-small">NaHCO₃</text></g>${tool}
          <g class="sci-cb-caption" text-anchor="middle"><text x="266" y="300">Reaksiya qabı</text><text x="465" y="300">${magnify ? "Böyüdücü" : "Sirkə həcmi"}</text></g>`,
        results: [
            {label: "Nəzəri CO₂ kütləsi", value: state.runs > 0 ? amount(mass, 2) + " q" : "Sınaq gözlənilir"},
            {label: "Miqdarı məhdudlaşdıran", value: state.runs > 0 ? limit : "—"},
        ],
        explanation: state.runs > 0
            ? "Bir mol sirkə turşusu bir mol qida sodası ilə reaksiyaya girib bir mol CO₂ verir. Göstərilən kütlə tam reaksiya üçün nəzəri həddir. Qabarcıqlar qazın ayrılmasını təsvir edir."
            : "Menzurkada sirkənin həcmini seçin. Qida sodasının kütləsini dəyişin və sınağı başladın. Böyüdücü ilə qaz qabarcıqlarına baxa bilərsiniz.",
    };
}

export const experiments = {
    indicator: {
        title: "Meyvə şirəsini indikatorla yoxla", prompt: "Alma şirəsi ilə təmiz suda eyni rəngi görəcəksinizmi?",
        setup: "Hər nümunə üçün təzə kələm indikatoru istifadə olunur. Pipet mayeyə indikator əlavə edir, kağız isə öz ucunda rəng dəyişir.",
        tools: [{id: "pipette", label: "Pipet"}, {id: "strip", label: "İndikator kağızı"}],
        controls: [{
            id: "sample", label: "Yoxlanacaq maddə", min: 1, max: 4, step: 1, value: 2, unit: "",
            choices: samples.map((sample, index) => ({value: index + 1, label: sample.name})),
        }],
        defaults: {tool: "pipette"}, render: indicator,
    },
    bubbles: {
        title: "Sirkə və soda ilə qazın ayrılması", prompt: "Sirkə sabit qalsa, soda əlavə etmək qazın miqdarını həmişə artırarmı?",
        setup: "Modeldə 100 ml sirkədə 5 q sirkə turşusu var. Qida sodası natrium hidrogenkarbonatdır. Reaksiya açıq qabda gedir.",
        tools: [{id: "cylinder", label: "Menzurka"}, {id: "lens", label: "Böyüdücü"}],
        controls: [
            {id: "vinegar", label: "Sirkənin həcmi", min: 0, max: 40, step: 1, value: 20, unit: "ml"},
            {id: "soda", label: "Qida sodasının kütləsi", min: 0, max: 3, step: 0.1, value: 1, unit: "q"},
        ],
        defaults: {tool: "cylinder"}, render: bubbles,
    },
};
