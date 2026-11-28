// SAPS pondweed and potometer investigations. Air saturation pressure uses FAO-56 equation 11.
function percent(value, fallback) {
    const numeric = Number(value ?? fallback);
    return Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : fallback;
}

function level(index) {
    if (index <= 0) return "Yoxdur";
    if (index < 0.36) return "Aşağı";
    return index < 0.7 ? "Orta" : "Yüksək";
}

function setting() {
    return `<defs>
      <linearGradient id="bio-sky" x2="0" y2="1"><stop stop-color="#edf5e9"/><stop offset="1" stop-color="#d8e9da"/></linearGradient>
      <linearGradient id="bio-water" x2="0" y2="1"><stop stop-color="#b8e3da" stop-opacity=".65"/><stop offset="1" stop-color="#7ebdbd" stop-opacity=".88"/></linearGradient>
      <linearGradient id="bio-leaf" x2=".85" y2="1"><stop stop-color="#91b87c"/><stop offset=".65" stop-color="#598a61"/><stop offset="1" stop-color="#336752"/></linearGradient>
      <linearGradient id="bio-shelf" x2="0" y2="1"><stop stop-color="#d7ba98"/><stop offset="1" stop-color="#ae9071"/></linearGradient>
    </defs><rect width="640" height="340" rx="15" fill="url(#bio-sky)"/>
    <path d="M0 72H640M0 148H640M0 224H640M90 0v72m145-72v72m146-72v72m145-72v72M34 72v76m145-76v76m146-76v76m145-76v76m145-76v76"
      fill="none" stroke="#7d9e85" opacity=".15"/>
    <path d="M0 269h640v71H0Z" fill="url(#bio-shelf)"/><path d="M0 283h640m-640 48h640" stroke="#876c58" opacity=".4"/>`;
}

function pondSprig(x, y, scale, tilt) {
    const leaves = Array.from({length: 7}, (_, i) => {
        const top = -6 - i * 15;
        return `<g transform="translate(0 ${top})"><path d="M0 0Q-21 -5 -26 -23Q-8 -19 0 -2Q13 -21 24 -21Q19 -5 0 0Z" fill="url(#bio-leaf)" stroke="#487550"/>
          <path d="M-22 -19L0 0L18 -16" fill="none" stroke="#90ad74" stroke-width="1.3"/></g>`;
    }).join("");
    return `<g transform="translate(${x} ${y}) rotate(${tilt}) scale(${scale})">${leaves}
      <path d="M0 3Q3 -46 0 -112" stroke="#416b48" stroke-width="4" fill="none" stroke-linecap="round"/></g>`;
}

function photosynthesis(state) {
    const light = percent(state.light, 60);
    const carbon = percent(state.carbon, 65);
    // A bounded illustration of two limiting resources, not a model fitted to a particular plant.
    const limit = Math.min(light, carbon);
    const tendency = limit / 100;
    const active = state.runs > 0;
    const collector = state.tool === "collector";
    const numbers = active && limit > 0 ? Math.ceil(tendency * 9) : 0;
    const bubbles = Array.from({length: numbers}, (_, i) =>
        `<circle class="sci-cb-bubble" cx="${288 + (i * 9) % 22}" cy="${collector ? 159 - i * 10 : 166 - (i * 13) % 45}" r="${2 + i % 3}"/>`).join("");
    const collected = active && collector && tendency > 0
        ? `<path d="M279 ${68 + tendency * 17}V66q0-7 7-7h14q7 0 7 7v${2 + tendency * 17}Z" fill="#f6fcf5"/>` : "";
    const cover = collector ? `<path d="M276 170V67q0-13 12-13h10q13 0 13 13v103"
        fill="none" stroke="#587c82" stroke-width="3"/>${collected}
        <path d="M301 80h8m-5 10h5m-8 10h8m-5 10h5m-8 10h8" stroke="#76969a" stroke-width="2"/>
        <path d="M277 154h33l26 24h-87Z" stroke="#648f92" fill="#d9efdf" fill-opacity=".45"/>`
        : `<g><circle cx="480" cy="141" r="32" stroke="#617866" stroke-width="6" fill="#f7f9e9"/>
        <path d="M480 121v20l12 7" stroke="#3d625a" fill="none" stroke-width="3"/><path d="M474 100h13v9h-13Z" fill="#617866"/></g>`;
    const limiting = light === carbon ? "Hər ikisi eyni səviyyədə" : light < carbon ? "İşıq" : "Həll olmuş CO₂";
    return {
        svg: `${setting()}<path d="M84 250h84v13H84zM106 248l26-93-4-50 13-2 9 52-27 95" fill="#597970" stroke="#405c59" stroke-width="3"/>
          <path d="M109 83q14-30 38-15l40 33-49 39Z" fill="#edb760" stroke="#836846" stroke-width="3"/>
          <path d="M137 138q9-27 48-38" fill="none" stroke="#f7dc97" stroke-width="6"/>
          <path d="M147 135l99 83 29-85-91-29Z" fill="#f4d063" opacity="${(light / 155).toFixed(2)}"/>
          <ellipse cx="318" cy="268" rx="118" ry="7" fill="#537269" opacity=".2"/>
          <path d="M201 78h219l-9 171q-1 15-16 15H225q-16 0-17-15Z" stroke="#578084" stroke-width="3" fill="#f4fbf4" fill-opacity=".37"/>
          <path d="M205 118q51 6 106 0t105 0l-8 129q-1 13-14 13H226q-13 0-14-13Z" fill="url(#bio-water)"/>
          <path d="M211 119q43 5 94 0t106 0" stroke="#5f9fa0" fill="none" stroke-width="2"/>
          <path d="M218 249q49-19 95 0t89 0v10H219Z" fill="#99a88b"/>
          ${pondSprig(275, 250, 0.82, -13)}${pondSprig(319, 250, 0.82, 8)}${pondSprig(345, 252, 0.62, 18)}
          ${cover}<g class="sci-cb-bubbles">${bubbles}</g>
          <g class="sci-cb-caption" text-anchor="middle"><text x="122" y="302">İşıq mənbəyi</text>
          <text x="329" y="302">Su bitkisi</text><text x="488" y="${collector ? 222 : 201}">${collector ? "Qaz toplayıcı" : "Saniyəölçən"}</text></g>
          ${collector ? '<path d="M447 215l-73-9-63-54" stroke="#657968" fill="none" stroke-width="1.5"/>' : ''}`,
        results: [
            {label: "Fotosintez meyli", value: active ? level(tendency) : "Sınaq gözlənilir"},
            {label: "Modeldə məhdudlaşdıran", value: active ? limiting : "—"},
        ],
        explanation: collector
            ? "Su bitkisinin işıqda ayırdığı oksigen çevrilmiş boruda toplanır. Model yalnız işıq və həll olmuş CO₂ əlçatanlığını müqayisə edir. Toplanan qazın görünüşü şərtidir."
            : "Temperatur sabitdir. İşıq və həll olmuş CO₂ birlikdə fotosintezə təsir edir. Eyni müşahidə müddətində qabarcıqların çoxalması meyli göstərə bilər. Qabarcıqların həcmi eyni olmaya bilər.",
    };
}

function leaf(x, y, size, angle) {
    return `<g transform="translate(${x} ${y}) rotate(${angle}) scale(${size})">
      <path d="M0 0Q10-32 57-33Q48-8 0 0Z" fill="url(#bio-leaf)" stroke="#467551" stroke-width="1.5"/>
      <path d="M0 0L50-29M17-9l5-12m5 6 12 1m-3-6 4-7" stroke="#c3d69c" stroke-width="1.4" fill="none"/>
    </g>`;
}

function transpiration(state) {
    const humidity = percent(state.humidity, 50);
    const air = percent(state.air, 30);
    const active = state.runs > 0;
    const magnify = state.tool === "leaf";
    // Both the air and the leaf are held at 25 °C and internal leaf air is assumed saturated.
    const saturation = 0.6108 * Math.exp(17.27 * 25 / (25 + 237.3));
    const deficit = saturation * (1 - humidity / 100);
    // Air movement changes the model boundary layer. The inset is illustrative, not a flow meter.
    const tendency = (1 - humidity / 100) * (0.5 + 0.5 * air / 100);
    const bubbleX = 369 - (active ? tendency * 85 : 0);
    const drops = active && tendency > 0 ? Array.from({length: Math.ceil(5 * tendency)}, (_, i) =>
        `<path class="sci-cb-vapour" d="M${260 + i * 12} ${125 - i * 7}q-4-7 0-12t0-12" fill="none"
          stroke="#438997" stroke-dasharray="4 4" stroke-width="2.5" stroke-linecap="round"/>`).join("") : "";
    const airPaths = air > 0 ? `<g fill="none" stroke="#7da7a2" stroke-width="2" opacity="${(0.32 + air / 180).toFixed(2)}">
      <path d="M101 119q19-7 34 0t28-2m-7-5 8 5-7 7M103 137q12-6 25-1t35 1m-7-5 8 5-7 7"/></g>` : "";
    const inset = magnify ? `<circle cx="494" cy="138" r="57" fill="#e5f0c9" stroke="#73916c" stroke-width="5"/>
      <path d="M484 110c-20-9-32 38-13 51 10 7 18-1 13-10-5-9-6-20 4-29q7-7-4-12ZM501 110c20-9 33 38 14 51-9 8-18-1-13-10 5-9 6-20-4-29q-7-7 3-12Z"
        fill="#81a46d" stroke="#526f52" stroke-width="2"/><path d="M442 165l-60 11-68-37" stroke="#68886a" fill="none"/>
      <text x="493" y="226" text-anchor="middle" class="sci-cb-caption">Yarpaq ağızcığı</text>`
        : `<path d="M219 233v14q0 8 9 8h199" fill="none" stroke="#537980" stroke-width="17"/>
        <path d="M219 233v14q0 8 9 8h199" fill="none" stroke="#a6d4d4" stroke-width="11"/>
        <rect class="${active && tendency > 0 ? 'sci-cb-marker' : ''}" x="${bubbleX}" y="250" width="15" height="10" rx="5" fill="#fffde9" stroke="#7a8b79"/>
        <path d="M261 267v7m15-7v4m15-4v7m15-7v4m15-4v7m15-7v4m15-4v7m15-7v4m15-4v7m15-7v4" stroke="#6b7264"/>
        <text x="394" y="222" class="sci-cb-label">Hava qabarcığı</text><path d="M394 226l-13 8-${Math.max(3, 372 - bubbleX)} 13" fill="none" stroke="#73817a"/>`;
    return {
        svg: `${setting()}<g transform="translate(76 133)" stroke="#6b8277"><rect x="-7" y="31" width="14" height="73" fill="#91a88e"/>
          <rect x="-28" y="102" width="56" height="7" rx="3" fill="#728f80"/>
          <circle r="32" fill="#dce8db" stroke-width="3"/><g fill="#8eaaa0"><path d="M0-4q-21-7-12-20q10-7 12 20Zm4 5q15-18 24-4q4 12-24 4ZM-3 3q8 19-9 19q-12-3 9-19Z"/></g><circle r="5" fill="#6a847d"/></g>
          ${airPaths}<path d="M221 225q-3-73 34-118q19-24 33-49" fill="none" stroke="#547d53" stroke-width="6"/>
          ${leaf(232, 164, 1.07, -4)}${leaf(229, 165, -0.82, 59)}${leaf(248, 121, 1.15, 5)}${leaf(251, 116, -0.78, 73)}${leaf(272, 87, 0.8, 3)}${leaf(278, 76, 0.58, -47)}
          <path d="M197 206h45l-3 30h-39Z" fill="#ab927a" stroke="#7c735f" stroke-width="2"/>
          ${drops}${inset}<g class="sci-cb-caption" text-anchor="middle"><text x="87" y="302">Hava axını</text>
          <text x="303" y="302">${magnify ? "Yarpaqlı zoğ" : "Potometr"}</text></g>`,
        results: [
            {label: "Buxar təzyiqi fərqi (25 °C)", value: deficit.toFixed(2).replace(".", ",") + " kPa"},
            {label: "Su itkisinin meyli", value: active ? level(tendency) : "Sınaq gözlənilir"},
        ],
        explanation: magnify
            ? "Su buxarı yarpağın ağızcıqlarından havaya yayılır. Modeldə yağış və su çatışmazlığı yoxdur, yarpaqla hava eyni temperaturdadır və ağızcıqlar açıq qalır. Rütubət artdıqca buxar təzyiqi fərqi azalır."
            : "Potometr zoğun su qəbulunu hava qabarcığının yerdəyişməsi ilə göstərir. Bu, yarpağın su itkisini təxmini izləməyə imkan verir. Zəif hava axınında da quru havaya su buxarı yayıla bilər.",
    };
}

export const experiments = {
    photosynthesis: {
        title: "Su bitkisində fotosintez", prompt: "İşığı artıranda qaz ayrılması hansı halda məhdud qala bilər?",
        setup: "Eyni su bitkisi və sabit temperatur götürülür. İşıq və həll olmuş CO₂ üçün 0–100 şərti əlçatanlıq şkalasından istifadə olunur.",
        tools: [{id: "timer", label: "Saniyəölçən"}, {id: "collector", label: "Qaz toplayıcı"}],
        controls: [
            {id: "light", label: "İşıq əlçatanlığı", min: 0, max: 100, step: 5, value: 60, unit: "/100"},
            {id: "carbon", label: "Həll olmuş CO₂ əlçatanlığı", min: 0, max: 100, step: 5, value: 65, unit: "/100"},
        ], defaults: {tool: "timer"}, render: photosynthesis,
    },
    transpiration: {
        title: "Yarpaqdan suyun buxarlanması", prompt: "Hava rütubətlənəndə yarpaqdan su itkisinə nə olur?",
        setup: "Yarpaqdan su buxarının ayrılması transpirasiya adlanır. Hava və yarpaq 25 °C temperaturdadır. İşıq və yarpaq sahəsi sabitdir. Axın 0–100 şərti şkalada dəyişir.",
        tools: [{id: "potometer", label: "Potometr"}, {id: "leaf", label: "Yarpaq lupası"}],
        controls: [
            {id: "humidity", label: "Havanın nisbi rütubəti", min: 0, max: 100, step: 5, value: 50, unit: "%"},
            {id: "air", label: "Hava axınının gücü", min: 0, max: 100, step: 5, value: 30, unit: "/100"},
        ], defaults: {tool: "potometer"}, render: transpiration,
    },
};
