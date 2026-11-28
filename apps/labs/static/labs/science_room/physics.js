// Physics models and reference values:
// https://openstax.org/books/university-physics-volume-3/pages/6-2-photoelectric-effect
// https://openstax.org/books/university-physics-volume-1/pages/15-4-pendulums
// https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html
// Each scene uses a 640 × 340 instrument plate. Inputs are normalized before drawing.
const metals = {
    sodium: { name: "Natrium", work: 2.46, tint: "#dac498" },
    calcium: { name: "Kalsium", work: 2.71, tint: "#b9c9be" },
    silver: { name: "Gümüş", work: 4.73, tint: "#cdd4e4" }
};
const gravity = {
    earth: { name: "Yer", g: 9.81 },
    moon: { name: "Ay", g: 1.62 }
};
function value(raw, min, max, fallback) {
    const n = Number(raw);
    return Number.isFinite(n) && raw != null ? Math.min(max, Math.max(min, n)) : fallback;
}
const fmt = (n, digits = 2) => n.toLocaleString("az-AZ", { maximumFractionDigits: digits });
function selected(options, key, fallback) {
    return Object.hasOwn(options, key) ? options[key] : options[fallback];
}
function label(x, y, text, size = 13, color = "#33504e", anchor = "start") {
    return `<text x="${x}" y="${y}" fill="${color}" font-size="${size}" text-anchor="${anchor}" font-family="system-ui,sans-serif">${text}</text>`;
}
function moving(runs) {
    return runs > 0 && !globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
function opticalColor(nm) {
    if (nm < 380) return "#7359a8";
    if (nm < 450) return "#8060ae";
    if (nm < 490) return "#427db5";
    if (nm < 510) return "#21827c";
    if (nm < 565) return "#6b873a";
    if (nm < 590) return "#c29427";
    if (nm < 630) return "#c77834";
    return "#bc5958";
}
function photoelectric(state) {
    const metal = selected(metals, state.tool, "sodium");
    const wavelength = value(state.wavelength, 200, 700, 430);
    const threshold = 1239.841984 / metal.work;
    const photon = 1239.841984 / wavelength;
    const emits = photon > metal.work;
    const kinetic = Math.max(0, photon - metal.work);
    const waveColor = opticalColor(wavelength);
    const band = wavelength < 380 ? "Ultrabənövşəyi" : "Görünən işıq";
    const wave = Array.from({ length: 131 }, (_, i) => {
        const x = 117 + i * 1.2;
        const y = 151 - 8 * Math.sin((i * 1.2 * 2 * Math.PI) / (wavelength / 14));
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    const ticks = Array.from(
        { length: 31 },
        (_, i) => `<path d="M${95 + i * 15} 258v${i % 5 === 0 ? 12 : 6}"/>`
    ).join("");
    const electrons = emits
        ? [0, 1, 2]
              .map((i) => {
                  const x = 327 + i * 35;
                  const y = 144 + (i % 2) * 20;
                  const anim = moving(state.runs)
                      ? `<animate attributeName="cx" values="${x - 20};${x};${x + 16}" dur="1.5s" repeatCount="2"/>`
                      : "";
                  return `<circle cx="${x}" cy="${y}" r="5" fill="#0d7f73">${anim}</circle>`;
              })
              .join("")
        : "";
    const svg = `<rect width="640" height="340" rx="12" fill="#f7f4eb"/>
        <defs><linearGradient id="pe-bulb" x2="0" y2="1"><stop stop-color="#f7ffff"/><stop offset="1" stop-color="#d7e7df"/></linearGradient></defs>
        ${label(32, 36, "FOTOELEMENT", 12)}${label(610, 36, `${band} · ${fmt(wavelength, 0)} nm`, 13, "#435c5b", "end")}
        <path d="M78 228v24m296-24v24m-316 0h49m243 0h48" stroke="#62756d" stroke-width="7" fill="none"/>
        <rect x="40" y="119" width="65" height="65" rx="8" fill="#365959"/><path d="M105 133l14 5v28l-14 5z" fill="#78918b"/>
        <path d="M49 128h24m-24 6h20m-20 6h16" stroke="#a1b4a6" stroke-width="2"/>
        <path d="M79 184v48" stroke="#52645d" stroke-width="8"/>
        <path d="M118 143l170-21v66l-170-28z" fill="${waveColor}" opacity=".12"/>
        <polyline points="${wave}" fill="none" stroke="${waveColor}" stroke-width="3"/>
        <rect x="259" y="97" width="198" height="115" rx="56" fill="url(#pe-bulb)" stroke="#849b91" stroke-width="3"/>
        <path d="M277 121q17-17 40-17h87" fill="none" stroke="#fff" stroke-width="4"/>
        <path d="M307 127q-13 23 0 49" fill="none" stroke="#435954" stroke-width="11"/>
        <path d="M310 126q-13 23 0 49" fill="none" stroke="${metal.tint}" stroke-width="5"/>
        <path d="M417 129v46" stroke="#516b65" stroke-width="7" stroke-linecap="round"/>
        <path d="M315 214h89l-5 13h-79z" fill="#889990"/>${electrons}
        <path d="M287 164v73h205v-48m-75-37h48v-70h66v11" fill="none" stroke="#69847a" stroke-width="2"/>
        <rect x="476" y="90" width="125" height="100" rx="8" fill="#335552"/>
        <rect x="487" y="103" width="103" height="46" rx="4" fill="#e1eee1"/>
        ${label(538, 134, emits ? `${fmt(kinetic)} V` : "—", 18, "#203e3d", "middle")}
        ${label(538, 173, "|Uₛ|", 15, "#e7efe2", "middle")}
        ${label(31, 102, "İşıq mənbəyi")}${label(306, 78, `${metal.name} katod`, 13, "#435c5b", "middle")}${label(414, 78, "Anod", 13, "#435c5b", "middle")}
        <path d="M306 84v29m109-29v30" fill="none" stroke="#a8b6a6" stroke-width="1.3"/>
        <rect x="31" y="252" width="578" height="25" rx="5" fill="#dfe5d8"/>
        <g stroke="#789080">${ticks}</g>${label(32, 312, emits ? "Katoddan elektron ayrılır" : "Elektron ayrılmır", 16)}
        ${label(609, 312, `Hədd · ${fmt(threshold, 0)} nm`, 14, "#52635f", "end")}`;
    return {
        svg,
        results: [
            { label: "Fotonun enerjisi", value: `${fmt(photon)} eV` },
            { label: "Çıxış işi", value: `${fmt(metal.work)} eV` },
            { label: "Maksimal kinetik enerji", value: emits ? `${fmt(kinetic)} eV` : "Elektron ayrılmır" },
            { label: "Saxlayıcı gərginliyin modulu", value: emits ? `${fmt(kinetic)} V` : "Ölçülmür" }
        ],
        explanation: emits
            ? `${metal.name} səthində fotonun enerjisi çıxış işindən çoxdur. Fərq elektronun maksimal kinetik enerjisidir.`
            : `Bu dalğa uzunluğunda fotonun enerjisi kifayət etmir. ${metal.name} üçün hədd dalğa uzunluğu təxminən ${fmt(threshold, 0)} nm-dir.`
    };
}
function pendulum(state) {
    const place = selected(gravity, state.tool, "earth");
    const length = value(state.length, 0.25, 1.5, 1);
    const angle = value(state.angle, 2, 12, 8);
    const period = 2 * Math.PI * Math.sqrt(length / place.g);
    const arm = length * 130;
    const theta = (angle * Math.PI) / 180;
    const dx = arm * Math.sin(theta),
        dy = arm * Math.cos(theta);
    const anim = moving(state.runs)
        ? `<animateTransform attributeName="transform" type="rotate" values="${angle} 262 70;${-angle} 262 70;${angle} 262 70" keyTimes="0;.5;1" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1" dur="${period.toFixed(4)}s" repeatCount="2"/>`
        : "";
    const ticks = Array.from(
        { length: 17 },
        (_, i) => `<path d="M144 ${75 + i * 10}h${i % 5 === 0 ? 12 : 6}"/>`
    ).join("");
    const svg = `<rect width="640" height="340" rx="12" fill="#f3f5eb"/>
        <defs><radialGradient id="pd-ball" cx=".34" cy=".27"><stop stop-color="#fff2b6"/><stop offset=".42" stop-color="#d3a658"/><stop offset="1" stop-color="#846238"/></radialGradient></defs>
        ${label(31, 35, "RƏQQAS STENDİ", 12)}${label(610, 35, `${place.name} · g = ${fmt(place.g)} m/s²`, 13, "#435c5b", "end")}
        <rect x="81" y="277" width="290" height="13" rx="5" fill="#526d62"/><path d="M112 274V58h153v13" fill="none" stroke="#769284" stroke-width="9" stroke-linejoin="round"/>
        <path d="M113 94l34-35" stroke="#829d8e" stroke-width="5"/><rect x="141" y="74" width="19" height="172" rx="3" fill="#e6ddbd"/>
        <g stroke="#746e56">${ticks}</g><path d="M262 71v190" fill="none" stroke="#a6b4a0" stroke-dasharray="4 5"/>
        <path d="M${262 - dx} ${70 + dy}A${arm} ${arm} 0 0 0 ${262 + dx} ${70 + dy}" fill="none" stroke="#ba9c5c" stroke-width="2" stroke-dasharray="4 3"/>
        <g transform="rotate(${angle} 262 70)">${anim}<path d="M262 70v${arm}" stroke="#50675e" stroke-width="2.4"/>
        <circle cx="262" cy="${70 + arm}" r="13" fill="url(#pd-ball)" stroke="#886e46"/></g>
        <circle cx="262" cy="70" r="6" fill="#344f47"/>${label(278, 90, `${fmt(angle, 0)}°`, 14)}
        <rect x="381" y="104" width="199" height="106" rx="13" fill="#3b5d55"/><rect x="395" y="122" width="171" height="54" rx="6" fill="#e2ead8"/>
        ${label(480, 158, `${fmt(period, 3)} s`, 27, "#24463c", "middle")}${label(480, 196, "Bir tam rəqs", 13, "#f0f3e4", "middle")}
        <path d="M380 242h201" stroke="#bdc9b5"/>${label(380, 268, `Asqı uzunluğu · ${fmt(length)} m`)}
        ${label(32, 313, "T = 2π√(L/g)", 18)}${label(609, 313, "Kiçik bucaq modeli", 13, "#52635f", "end")}`;
    return {
        svg,
        results: [
            { label: "Bir tam rəqsin dövrü", value: `${fmt(period, 3)} s` },
            { label: "Tezlik", value: `${fmt(1 / period, 3)} Hz` },
            { label: "On tam rəqs", value: `${fmt(10 * period, 2)} s` }
        ],
        explanation: `${place.name} şəraitində ${fmt(length)} m uzunluqlu ideal rəqqas bir tam rəqsi ${fmt(period, 3)} saniyəyə edir. Kiçik bucaqlarda dövr əsasən uzunluqdan və cazibə təcilindən asılıdır.`
    };
}
export const experiments = {
    photoelectric: {
        title: "Fotoelektrik effekt",
        prompt: "Eyni işıqla natriumdan elektron ayrıldığı halda gümüşdə nə baş verir?",
        setup: "Katodu seçin, dalğa uzunluğunu dəyişin və foton enerjisini metalın çıxış işi ilə müqayisə edin. Sınağı başladıb elektronların hərəkətinə baxın.",
        tools: [
            { id: "sodium", label: "Natrium" },
            { id: "calcium", label: "Kalsium" },
            { id: "silver", label: "Gümüş" }
        ],
        controls: [
            { id: "wavelength", label: "Dalğa uzunluğu", min: 200, max: 700, step: 1, value: 430, unit: "nm" }
        ],
        defaults: { tool: "sodium" },
        render: photoelectric
    },
    pendulum: {
        title: "Riyazi rəqqas",
        prompt: "Eyni uzunluqlu rəqqas Yerdə, yoxsa Ayda daha tez rəqs edir?",
        setup: "Mühiti seçin. İpin uzunluğunu və başlanğıc bucağını qurun. Sınağı başladıb yayınmanın bir tam rəqsdən sonra təkrarlanmasını izləyin.",
        tools: [
            { id: "earth", label: "Yer" },
            { id: "moon", label: "Ay" }
        ],
        controls: [
            { id: "length", label: "İpin uzunluğu", min: 0.25, max: 1.5, step: 0.05, value: 1, unit: "m" },
            { id: "angle", label: "Başlanğıc bucağı", min: 2, max: 12, step: 1, value: 8, unit: "°" }
        ],
        defaults: { tool: "earth" },
        render: pendulum
    }
};
