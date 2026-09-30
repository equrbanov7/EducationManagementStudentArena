// LX-FE-PLAYER (2026-09-29): cavab fiqurları (SVG) — host ekranı ilə eyni forma + rəng sırası:
// 1 üçbucaq (qırmızı), 2 romb (mavi), 3 dairə (kəhrəba), 4 kvadrat (yaşıl), 5 ulduz (server açarı
// «pentagon»), 6 altıbucaq (firuzəyi). Rəng yalnız köməkçidir — forma rəngkor oyunçu üçün əsasdır.
import { OPTION_SHAPES } from './config.js?v=lx20260930';
import { tr } from './utils.js?v=lx20260930';

const PATHS = {
    triangle:
        '<path d="M12 2.6c.5 0 .96.26 1.22.7l9.3 16.1c.55.95-.14 2.1-1.22 2.1H2.7c-1.08 0-1.77-1.15-1.22-2.1l9.3-16.1c.26-.44.72-.7 1.22-.7z"/>',
    diamond:
        '<path d="M12 1.6c.4 0 .78.16 1.06.44l8.9 8.9a1.5 1.5 0 0 1 0 2.12l-8.9 8.9a1.5 1.5 0 0 1-2.12 0l-8.9-8.9a1.5 1.5 0 0 1 0-2.12l8.9-8.9c.28-.28.66-.44 1.06-.44z"/>',
    circle: '<circle cx="12" cy="12" r="10"/>',
    square: '<rect x="2.5" y="2.5" width="19" height="19" rx="3.4"/>',
    pentagon:
        '<path d="M12 1.7c.38 0 .72.22.88.56l2.6 5.56 6.08.74c.8.1 1.12 1.08.53 1.63l-4.48 4.18 1.18 6.02c.15.79-.69 1.4-1.4 1.01L12 18.4l-5.39 2.99c-.71.4-1.55-.22-1.4-1.01l1.18-6.02-4.48-4.18c-.59-.55-.27-1.53.53-1.63l6.08-.74 2.6-5.56c.16-.34.5-.56.88-.56z"/>',
    hexagon:
        '<path d="M7.1 2.4h9.8c.57 0 1.1.3 1.39.8l4.9 8.5c.28.5.28 1.1 0 1.6l-4.9 8.5c-.29.5-.82.8-1.39.8H7.1c-.57 0-1.1-.3-1.39-.8L.81 13.3a1.6 1.6 0 0 1 0-1.6L5.71 3.2c.29-.5.82-.8 1.39-.8z"/>',
};

const LABELS = {
    triangle: ["shapeTriangle", "Üçbucaq"],
    diamond: ["shapeDiamond", "Romb"],
    circle: ["shapeCircle", "Dairə"],
    square: ["shapeSquare", "Kvadrat"],
    pentagon: ["shapeStar", "Ulduz"],
    hexagon: ["shapeHexagon", "Altıbucaq"],
};

export function shapeKey(option, index) {
    const fallback = OPTION_SHAPES[Math.abs(Number(index) || 0) % OPTION_SHAPES.length];
    const raw = String((option && option.shape) || fallback).toLowerCase();
    return Object.prototype.hasOwnProperty.call(PATHS, raw) ? raw : fallback;
}

// Rəng tonu fiqurdan törəyir: host da rəngi eyni sıra ilə verir (1..6).
export function toneIndex(option, index) {
    const position = OPTION_SHAPES.indexOf(shapeKey(option, index));
    return position >= 0 ? position + 1 : (Math.abs(Number(index) || 0) % OPTION_SHAPES.length) + 1;
}

export function shapeLabel(key) {
    const [i18nKey, fallback] = LABELS[key] || LABELS.circle;
    return tr(i18nKey, fallback);
}

export function shapeSvg(key, className = "lxp-shape") {
    const body = PATHS[key] || PATHS.circle;
    return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><g fill="currentColor">${body}</g></svg>`;
}
