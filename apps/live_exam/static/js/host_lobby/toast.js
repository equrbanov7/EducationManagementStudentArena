/* toast.js — aparıcı ekranında qısa bildiriş (2026-10-08). `alert()` əvəzinə: proyektorda
 * brauzerin modal dialoqu tam ekranı qırır. Bir konteyner, ən çox 3 bildiriş, avtomatik itir. */
import { esc } from './utils.js?v=lx20261008';

const MAX_TOASTS = 3;

function host() {
    let root = document.getElementById("hxToasts");
    if (!root) {
        root = document.createElement("div");
        root.id = "hxToasts";
        root.className = "hx-toasts";
        root.setAttribute("role", "status");
        root.setAttribute("aria-live", "polite");
        document.body.appendChild(root);
    }
    return root;
}

/** `tone`: "info" | "ok" | "error". */
export function showToast(message, tone = "info", ms = 3200) {
    const text = String(message || "").trim();
    if (!text) return;
    const root = host();
    while (root.childElementCount >= MAX_TOASTS) root.firstElementChild.remove();
    const toast = document.createElement("div");
    toast.className = `hx-toast hx-toast--${tone}`;
    toast.innerHTML = `<span>${esc(text)}</span>`;
    root.appendChild(toast);
    window.setTimeout(() => {
        toast.classList.add("is-leaving");
        window.setTimeout(() => toast.remove(), 260);
    }, Math.max(1200, ms));
}
