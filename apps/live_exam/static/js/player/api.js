// LX-FE-PLAYER (2026-09-29): HTTP snapshot (/live/state/<pin>/) — WS qopanda, səhifə yenilənəndə,
// tab yenidən görünəndə və «gözlənilən mesaj gecikib» hallarında UI-ni server vəziyyətinə gətirir.
// Eyni anda yalnız bir sorğu; 429-da Retry-After-a hörmət; 403 → oyunçu sessiyada yoxdur.
import { BOOTSTRAP } from './config.js?v=lx20260929';
import { state } from './state.js?v=lx20260929';
import { updateServerTimeOffset } from './utils.js?v=lx20260929';

let inFlight = null;
let blockedUntil = 0;
let snapshotHandler = () => {};
let authLostHandler = () => {};
let failureHandler = () => {};

export function setSnapshotHandlers({ onSnapshot, onAuthLost, onFailure } = {}) {
    if (typeof onSnapshot === "function") snapshotHandler = onSnapshot;
    if (typeof onAuthLost === "function") authLostHandler = onAuthLost;
    if (typeof onFailure === "function") failureHandler = onFailure;
}

export function fetchState() {
    if (state.removed) return Promise.resolve(null);
    if (inFlight) return inFlight;
    if (Date.now() < blockedUntil) return Promise.resolve(null);
    const url = BOOTSTRAP.stateUrl || `/live/state/${encodeURIComponent(BOOTSTRAP.pin || "")}/`;
    inFlight = (async () => {
        try {
            const response = await fetch(url, {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                cache: "no-store",
            });
            if (response.status === 429) {
                const retryAfter = Number(response.headers.get("Retry-After") || 0);
                blockedUntil = Date.now() + Math.max(5, retryAfter || 10) * 1000;
                return null;
            }
            if (response.status === 403) {
                authLostHandler();
                return null;
            }
            if (!response.ok) {
                failureHandler();
                return null;
            }
            const receivedAt = Date.now();
            const snapshot = await response.json();
            updateServerTimeOffset(snapshot, receivedAt);
            snapshotHandler(snapshot);
            return snapshot;
        } catch (error) {
            failureHandler(error);
            return null;
        } finally {
            inFlight = null;
        }
    })();
    return inFlight;
}
