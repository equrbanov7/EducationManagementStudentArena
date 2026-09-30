// LX-FE-PLAYER (2026-09-29): oyun WebSocket-i — avtomatik yenidən qoşulma (eksponensial gecikmə +
// jitter). Əvvəl soket bir dəfə açılırdı; Wi-Fi qopanda yalnız 2.5 s-lik HTTP sorğusu qalırdı.
// Server qoşulma limiti (LIVE_WS_CONNECT_RATE_LIMIT, 20/dəq) aşılmasın deyə gecikmə 10 s-ə qədər artır;
// 4429 (limit) → 15 s; 4401 (token etibarsız / oyunçu silinib) → yenidən cəhd yoxdur.
import { BOOTSTRAP } from './config.js?v=lx20260930';
import { wsUrl } from './utils.js?v=lx20260930';

let ws = null;
let attempt = 0;
let retryTimer = null;
let handlers = {};
let stopped = false;

export function isSocketOpen() {
    return Boolean(ws && ws.readyState === WebSocket.OPEN);
}

function isSocketConnecting() {
    return Boolean(ws && ws.readyState === WebSocket.CONNECTING);
}

function scheduleReconnect(forcedDelayMs) {
    if (stopped) return;
    attempt += 1;
    const base = forcedDelayMs || Math.min(10000, 800 * Math.pow(2, attempt - 1));
    const delay = base + Math.floor(Math.random() * 400);
    window.clearTimeout(retryTimer);
    retryTimer = window.setTimeout(connect, delay);
    if (typeof handlers.onRetry === "function") handlers.onRetry(delay, attempt);
}

function connect() {
    window.clearTimeout(retryTimer);
    retryTimer = null;
    if (stopped || isSocketOpen() || isSocketConnecting()) return;
    let socket;
    try {
        socket = new WebSocket(wsUrl(`/ws/live/${encodeURIComponent(BOOTSTRAP.pin || "")}/play/`));
    } catch (error) {
        scheduleReconnect();
        return;
    }
    ws = socket;
    socket.onopen = () => {
        if (socket !== ws) return;
        attempt = 0;
        if (typeof handlers.onOpen === "function") handlers.onOpen();
    };
    socket.onmessage = (event) => {
        if (socket !== ws) return;
        if (typeof handlers.onMessage === "function") handlers.onMessage(event);
    };
    socket.onerror = () => {
        // onclose həmişə ardınca gəlir — orada idarə olunur
    };
    socket.onclose = (event) => {
        if (socket !== ws) return;
        ws = null;
        if (typeof handlers.onClose === "function") handlers.onClose(event);
        if (stopped) return;
        if (event && (event.code === 4401 || event.code === 4403)) {
            if (typeof handlers.onAuthLost === "function") handlers.onAuthLost(event);
            return;
        }
        scheduleReconnect(event && event.code === 4429 ? 15000 : 0);
    };
}

export function openPlayerSocket(nextHandlers) {
    handlers = nextHandlers || {};
    stopped = false;
    connect();
}

// Şəbəkə qayıdanda / tab görünəndə gözləmədən yenidən qoşul.
export function reconnectNow() {
    if (stopped || isSocketOpen() || isSocketConnecting()) return;
    attempt = 0;
    connect();
}

export function sendJson(payload) {
    if (!isSocketOpen()) return false;
    try {
        ws.send(JSON.stringify(payload));
        return true;
    } catch (error) {
        return false;
    }
}

export function closePlayerSocket() {
    stopped = true;
    window.clearTimeout(retryTimer);
    retryTimer = null;
    if (ws) {
        try {
            ws.close();
        } catch (error) {
            // artıq bağlıdır
        }
    }
    ws = null;
}
