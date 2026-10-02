// LX-FE-PLAYER (2026-09-29): HTTP snapshot (/live/state/<pin>/) — WS qopanda, səhifə yenilənəndə,
// tab yenidən görünəndə və «gözlənilən mesaj gecikib» hallarında UI-ni server vəziyyətinə gətirir.
// Eyni anda yalnız bir sorğu; 429-da Retry-After-a hörmət; 403 → oyunçu sessiyada yoxdur.
// LXNET (2026-10-02):
//  * sorğunun vaxt həddi var (6 s) — qopma zamanı ilişən (TCP təkrar ötürmə gözləyən) sorğu
//    sonrakı bütün sorğuları bloklayırdı; indi ləğv olunur, növbəti cəhd təzə bağlantı ilə gedir;
//  * `fetchState({ fresh: true })` (socket təzə açıldı / tab qayıtdı / şəbəkə qayıtdı) köhnəlmiş
//    gözləyən sorğunu ləğv edib dərhal yenisini göndərir — şəbəkə artıq işləyir;
//  * snapshot həm də saat sinxronu üçün gediş-gəliş nümunəsidir (clock.js).
import { BOOTSTRAP } from './config.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { recordServerRoundTrip } from './utils.js?v=lx20261002';

const SNAPSHOT_TIMEOUT_MS = 6000;
const STALE_IN_FLIGHT_MS = 1500;

let inFlight = null;
let inFlightAbort = null;
let inFlightAt = 0;
let blockedUntil = 0;
let snapshotHandler = () => {};
let authLostHandler = () => {};
let failureHandler = () => {};

// `fetch` + vaxt həddi (AbortController yoxdursa — adi fetch). `controller` verilməsə yenisi yaradılır.
export function fetchWithTimeout(url, init, timeoutMs, controller = null) {
    if (typeof AbortController !== "function") return fetch(url, init);
    const ctrl = controller || new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
    return fetch(url, Object.assign({}, init, { signal: ctrl.signal })).finally(() => window.clearTimeout(timer));
}

export function setSnapshotHandlers({ onSnapshot, onAuthLost, onFailure } = {}) {
    if (typeof onSnapshot === "function") snapshotHandler = onSnapshot;
    if (typeof onAuthLost === "function") authLostHandler = onAuthLost;
    if (typeof onFailure === "function") failureHandler = onFailure;
}

export function fetchState({ fresh = false } = {}) {
    if (state.removed) return Promise.resolve(null);
    if (inFlight) {
        if (!fresh || !inFlightAbort || Date.now() - inFlightAt < STALE_IN_FLIGHT_MS) return inFlight;
        inFlightAbort();
        inFlight = null;
    }
    if (Date.now() < blockedUntil) return Promise.resolve(null);
    const url = BOOTSTRAP.stateUrl || `/live/state/${encodeURIComponent(BOOTSTRAP.pin || "")}/`;
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    const flight = (async () => {
        await null; // gövdə həmişə asinxron davam edir — `flight` aşağıda təyin olunandan sonra
        const sentAt = Date.now();
        try {
            const response = await fetchWithTimeout(
                url,
                { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" },
                SNAPSHOT_TIMEOUT_MS,
                controller
            );
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
            // LXNET: snapshot gediş-gəliş nümunəsidir (server vaxtı [sentAt, receivedAt] arasında).
            recordServerRoundTrip(sentAt, snapshot && snapshot.server_time, receivedAt);
            snapshotHandler(snapshot);
            return snapshot;
        } catch (error) {
            failureHandler(error);
            return null;
        } finally {
            if (inFlight === flight) {
                inFlight = null;
                inFlightAbort = null;
            }
        }
    })();
    inFlight = flight;
    inFlightAbort = controller ? () => controller.abort() : null;
    inFlightAt = Date.now();
    return flight;
}
