// LX-FE-PLAYER (2026-09-29): faza görünüşlərinin (view) açarla idarəsi.
// Eyni açar (faza + sual + reveal) təkrar gələndə DOM yenidən qurulmur → ikiqat animasiya/səs yoxdur.
// Keçid: köhnə view «is-leaving» (220 ms) ilə çıxır, yenisi «is-entering» ilə girir (yalnız
// transform/opacity). Azaldılmış hərəkət rejimində dəyişmə anidir.
import { prefersReducedMotion } from './config.js?v=lx20261002';
import { UI } from './dom.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';

const LEAVE_MS = 240;
let current = null;

export function currentViewEl() {
    return current && current.el.isConnected ? current.el : null;
}

export function mountView(key, html, { tone = "", className = "" } = {}) {
    if (current && current.key === key && current.el.isConnected) {
        return { el: current.el, created: false };
    }
    const reduced = prefersReducedMotion();
    const el = document.createElement("section");
    el.className = className ? `lxp-view ${className}` : "lxp-view";
    el.dataset.viewKey = key;
    el.innerHTML = html;

    if (current && current.el.isConnected) {
        const old = current.el;
        old.classList.remove("is-entering");
        old.classList.add("is-leaving");
        old.setAttribute("aria-hidden", "true");
        old.inert = true;
        if (reduced) {
            old.remove();
        } else {
            window.setTimeout(() => old.isConnected && old.remove(), LEAVE_MS);
        }
    }
    if (!reduced) el.classList.add("is-entering");
    UI.views.appendChild(el);
    current = { key, el };
    state.viewKey = key;
    document.body.dataset.tone = tone || "";
    return { el, created: true };
}
