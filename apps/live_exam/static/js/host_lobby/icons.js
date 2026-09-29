/* icons.js — aparıcı (host) oyun ekranının xüsusi SVG ikonları (Font Awesome əvəzinə).
 * 24×24 xətti ikonlar (currentColor, 2px) + cavab fiqurları (40×40, doldurulmuş).
 * `window.LiveHostIcons` klassik skriptlər (host_lobby_shell.js) üçün də açıqdır.
 * Server fiqur açarları: triangle, diamond, circle, square, pentagon (ULDUZ kimi
 * çəkilir — kiçik ölçüdə altıbucaqdan fərqlənsin), hexagon.
 */

const STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';

const PATHS = {
    play: '<path d="M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.4-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z" fill="currentColor"/>',
    next: `<path d="M6 5.5v13l9-6.5z" fill="currentColor"/><path d="M18 5.5v13" ${STROKE} stroke-width="2.4"/>`,
    skip: '<path d="M3.5 6v12l8-6zM12.5 6v12l8-6z" fill="currentColor"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor"/>',
    eye: `<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" ${STROKE}/><circle cx="12" cy="12" r="3" ${STROKE}/>`,
    lock: `<rect x="5" y="10.5" width="14" height="10" rx="2.5" ${STROKE}/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" ${STROKE}/><circle cx="12" cy="15.5" r="1.4" fill="currentColor"/>`,
    unlock: `<rect x="5" y="10.5" width="14" height="10" rx="2.5" ${STROKE}/><path d="M8 10.5V8a4 4 0 0 1 7.6-1.7" ${STROKE}/><circle cx="12" cy="15.5" r="1.4" fill="currentColor"/>`,
    timer: `<circle cx="12" cy="13.5" r="7.5" ${STROKE}/><path d="M12 9.5v4.2l2.6 1.6M9.5 2.5h5M19 6.5l1.4-1.4" ${STROKE}/>`,
    users: `<circle cx="9" cy="8.5" r="3.3" ${STROKE}/><path d="M2.8 19.5c.6-3.3 3.2-5.2 6.2-5.2s5.6 1.9 6.2 5.2" ${STROKE}/><path d="M15.5 5.6a3.2 3.2 0 0 1 0 6.1M17.6 14.6c1.9.7 3.2 2.4 3.6 4.9" ${STROKE}/>`,
    check: `<path d="M5 12.5l4.5 4.5L19 7.5" ${STROKE} stroke-width="3"/>`,
    cross: `<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" ${STROKE} stroke-width="3"/>`,
    crown: '<path d="M3 8.5l4.6 3.8L12 5l4.4 7.3L21 8.5l-1.9 10H4.9z" fill="currentColor"/><rect x="4.9" y="19.5" width="14.2" height="2" rx="1" fill="currentColor"/>',
    medal: `<path d="M8 2.5h3l1.5 5M16 2.5h-3" ${STROKE}/><circle cx="12" cy="14.5" r="6.5" fill="currentColor"/><path d="M12 11l1 2.1 2.3.3-1.7 1.6.4 2.3-2-1.1-2 1.1.4-2.3-1.7-1.6 2.3-.3z" fill="#fff" opacity=".9"/>`,
    flame: '<path d="M12.5 2.5c.6 3.2-1 5-2.6 6.8C8.3 11 7 12.8 7 15.3 7 18.7 9.4 21.5 12 21.5s5-2.4 5-6c0-2.3-1-4-2-5.2-.2 1.6-1 2.6-2 3 .8-3.2.3-6.6-.5-9.8z" fill="currentColor"/><path d="M12 21.5c-1.7 0-3-1.3-3-3.2 0-1.6 1-2.6 2-3.5.1 1.1.6 1.8 1.4 2.1 0-1.3.4-2.3 1.2-3.2.5 1 1.4 2 1.4 3.6 0 2.4-1.3 4.2-3 4.2z" fill="#fff" opacity=".55"/>',
    trophy: `<path d="M7 3.5h10v5a5 5 0 0 1-10 0z" fill="currentColor"/><path d="M7 5.5H4v1.5A3.5 3.5 0 0 0 7.4 10.5M17 5.5h3v1.5a3.5 3.5 0 0 1-3.4 3.5" ${STROKE}/><path d="M12 13.5v3.5M8 20.5h8M9.5 17h5v3.5h-5z" ${STROKE}/>`,
    bolt: '<path d="M13.5 2L4.5 13.5h6L9.5 22l9-11.5h-6z" fill="currentColor"/>',
    star: '<path d="M12 2.8l2.8 5.9 6.4.8-4.7 4.5 1.2 6.4L12 17.3l-5.7 3.1 1.2-6.4-4.7-4.5 6.4-.8z" fill="currentColor"/>',
    sparkle: '<path d="M12 2c.8 4.8 2.2 6.2 7 7-4.8.8-6.2 2.2-7 7-.8-4.8-2.2-6.2-7-7 4.8-.8 6.2-2.2 7-7zM19 15c.4 2.2 1 2.8 3 3.2-2 .4-2.6 1-3 3.2-.4-2.2-1-2.8-3-3.2 2-.4 2.6-1 3-3.2z" fill="currentColor"/>',
    volume: `<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6M18.2 6.5a8 8 0 0 1 0 11" ${STROKE}/>`,
    volumeLow: `<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M15.5 9a4.2 4.2 0 0 1 0 6" ${STROKE}/>`,
    mute: `<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M16 9.5l5 5M21 9.5l-5 5" ${STROKE}/>`,
    music: `<path d="M9 18.5V5.5l11-2v12.5" ${STROKE}/><circle cx="6.5" cy="18.5" r="2.5" fill="currentColor"/><circle cx="17.5" cy="16" r="2.5" fill="currentColor"/>`,
    replay: `<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" ${STROKE}/><path d="M4 3.8v4.4h4.4" ${STROKE}/><path d="M10.5 9v6l4.5-3z" fill="currentColor"/>`,
    expand: `<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" ${STROKE}/>`,
    sliders: `<path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1" ${STROKE}/><circle cx="15" cy="6.5" r="2" ${STROKE}/><circle cx="9" cy="12" r="2" ${STROKE}/><circle cx="17" cy="17.5" r="2" ${STROKE}/>`,
    qr: `<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1" ${STROKE}/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1" ${STROKE}/><rect x="3.5" y="14" width="6.5" height="6.5" rx="1" ${STROKE}/><path d="M14 14h2.5v2.5H14zM18 18h2.5v2.5H18zM14 18.5h1.5M18.5 14h2" ${STROKE}/>`,
    keyboard: `<rect x="2.5" y="6" width="19" height="12" rx="2.5" ${STROKE}/><path d="M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M6.5 13.8h.01M17 13.8h.01M9.5 14h5" ${STROKE} stroke-width="2.4"/>`,
    chevronRight: `<path d="M9.5 5.5l6.5 6.5-6.5 6.5" ${STROKE} stroke-width="2.4"/>`,
    up: '<path d="M12 5l7.5 9h-15z" fill="currentColor"/>',
    down: '<path d="M12 19l-7.5-9h15z" fill="currentColor"/>',
    close: `<path d="M6.5 6.5l11 11M17.5 6.5l-11 11" ${STROKE} stroke-width="2.4"/>`,
    userMinus: `<circle cx="10" cy="8.5" r="3.4" ${STROKE}/><path d="M3.5 19.5c.6-3.3 3.3-5.3 6.5-5.3 1.3 0 2.5.3 3.5.9M15.5 16.5h6" ${STROKE}/>`,
};

const SHAPES = {
    triangle: '<path d="M20 5.5l15.2 27.2a1.5 1.5 0 0 1-1.3 2.3H6.1a1.5 1.5 0 0 1-1.3-2.3z"/>',
    diamond: '<path d="M20 3.5l16 16.5-16 16.5L4 20z"/>',
    circle: '<circle cx="20" cy="20" r="15.5"/>',
    square: '<rect x="5.5" y="5.5" width="29" height="29" rx="3.5"/>',
    star: '<path d="M20 3.2l4.9 10.4 11.4 1.3-8.5 7.8 2.4 11.2L20 28.2l-10.2 5.7 2.4-11.2-8.5-7.8 11.4-1.3z"/>',
    hexagon: '<path d="M20 3.5l14.3 8.25v16.5L20 36.5 5.7 28.25v-16.5z"/>',
};

const SHAPE_ORDER = ["triangle", "diamond", "circle", "square", "star", "hexagon"];

export function icon(name, className = "") {
    const body = PATHS[name] || "";
    return `<svg class="hx-icon${className ? ` ${className}` : ""}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
}

/** Server açarını (pentagon → star) vizual fiqur açarına çevirir. */
export function shapeKey(option, index) {
    const raw = String(option?.shape || "").toLowerCase();
    if (raw === "pentagon" || raw === "star") return "star";
    if (SHAPES[raw]) return raw;
    return SHAPE_ORDER[Math.max(0, Number(index) || 0) % SHAPE_ORDER.length];
}

export function shapeSvg(key, className = "") {
    const body = SHAPES[key] || SHAPES.circle;
    return `<svg class="hx-shape${className ? ` ${className}` : ""}" viewBox="0 0 40 40" aria-hidden="true" focusable="false"><g fill="currentColor">${body}</g></svg>`;
}

/** Cavab rəngi/fiquru üçün 1..6 indeksi (host və telefon eyni). */
export function toneIndex(index) {
    return (Math.max(0, Number(index) || 0) % 6) + 1;
}

/** Şablondakı `<span class="hx-i" data-icon="play">` yer tutucularını SVG ilə doldurur. */
export function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((el) => {
        if (!el.firstElementChild) el.innerHTML = icon(el.dataset.icon);
    });
}

window.LiveHostIcons = Object.freeze({ icon, shapeSvg, shapeKey, hydrateIcons });
