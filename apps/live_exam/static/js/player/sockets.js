// LX-FE-PLAYER (2026-09-29): oyun WebSocket-i — avtomatik yenidən qoşulma (eksponensial gecikmə +
// jitter). Əvvəl soket bir dəfə açılırdı; Wi-Fi qopanda yalnız 2.5 s-lik HTTP sorğusu qalırdı.
// Server qoşulma limiti (LIVE_WS_CONNECT_RATE_LIMIT, 20/dəq) aşılmasın deyə gecikmə 10 s-ə qədər artır;
// 4429 (limit) → 15 s; 4401 (token etibarsız / oyunçu silinib) → yenidən cəhd yoxdur.
//
// LXNET (2026-10-02) — zəif şəbəkə:
//  * ürək döyüntüsü: açıq socket-də ~6 s-də bir `ping`; `pong` vaxtında gəlməsə socket «ilişib»
//    sayılır (TCP təkrar ötürmə gözləyir, brauzer `close` vermir) → köhnəsi atılır, TƏZƏ socket
//    açılır və `onStall` (HTTP snapshot) dərhal işləyir. Əvvəl belə socket-də növbəti sual 30 s-ə
//    qədər gecikə bilirdi (gözətçi 4 → 30 s);
//  * pong həm RTT (bağlantı keyfiyyəti: good / weak / down), həm də saat sinxronu verir (clock.js);
//  * qoşulma vaxt həddi: CONNECTING-də ilişən socket 9 s sonra atılır;
//  * ilişmiş köhnə socket dərhal bağlanmır («ehtiyat»): uzun qopmada təzə bağlantının SYN-i də
//    gecikir, köhnə TCP isə bəzən daha tez bərpa olunur — hansı birinci çatdırsa, o işlənir
//    (zaman xətti təkrarı süzür); təzə socket açılan kimi köhnə bağlanır.
import { BOOTSTRAP } from './config.js?v=lx20261002';
import { recordServerRoundTrip, wsUrl } from './utils.js?v=lx20261002';

const PING_INTERVAL_MS = 6000;
const PONG_TIMEOUT_MIN_MS = 3500;
const PONG_TIMEOUT_MAX_MS = 9000;
const CONNECT_TIMEOUT_MS = 9000;
const WEAK_RTT_MS = 900;
const PROBE_MIN_GAP_MS = 1500;

let ws = null;
let standby = null;
let attempt = 0;
let retryTimer = null;
let connectTimer = null;
let heartbeatTimer = null;
let handlers = {};
let stopped = false;
let pingSeq = 0;
let pendingPing = null;
let lastPingSentAt = 0;
let srtt = 0;
let quality = "down";
// Server ping-i dəstəkləyir? (ilk pong-dan sonra). Deploy anında köhnə backend pong vermir —
// onda «ilişib» qərarı verilmir, köhnə davranış (gözətçi + HTTP) qalır.
let pongSeen = false;

export function isSocketOpen() {
    return Boolean(ws && ws.readyState === WebSocket.OPEN);
}

function isSocketConnecting() {
    return Boolean(ws && ws.readyState === WebSocket.CONNECTING);
}

export function smoothedRttMs() {
    return srtt;
}

export function socketQuality() {
    return quality;
}

// Cavab WS ilə getsin, yoxsa dərhal HTTP? Bağlıdırsa və ya ping cavabsız qalıbsa — «şübhəli».
export function isSocketSuspect() {
    if (!isSocketOpen()) return true;
    return Boolean(pongSeen && pendingPing && Date.now() - pendingPing.sentAt > Math.max(1500, srtt * 3));
}

function setQuality(next) {
    if (quality === next) return;
    quality = next;
    if (typeof handlers.onQuality === "function") handlers.onQuality(next, srtt);
}

export function pongTimeoutMs() {
    return Math.min(PONG_TIMEOUT_MAX_MS, Math.max(PONG_TIMEOUT_MIN_MS, Math.round(srtt * 4 + 1500)));
}

function sendPing() {
    if (!isSocketOpen() || pendingPing) return;
    pingSeq = (pingSeq % 2147483646) + 1;
    pendingPing = { id: pingSeq, sentAt: Date.now() };
    lastPingSentAt = pendingPing.sentAt;
    try {
        ws.send(JSON.stringify({ type: "ping", id: pingSeq }));
    } catch (error) {
        pendingPing = null;
    }
}

function handlePong(data) {
    if (!pendingPing || Number(data.id) !== pendingPing.id) return;
    const now = Date.now();
    const rtt = now - pendingPing.sentAt;
    pendingPing = null;
    pongSeen = true;
    srtt = srtt ? Math.round(srtt * 0.75 + rtt * 0.25) : rtt;
    recordServerRoundTrip(now - rtt, data.server_time, now);
    setQuality(srtt >= WEAK_RTT_MS ? "weak" : "good");
}

function stopHeartbeat() {
    window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
    pendingPing = null;
}

function heartbeatTick() {
    if (!isSocketOpen()) return;
    const now = Date.now();
    if (pendingPing) {
        const waited = now - pendingPing.sentAt;
        if (!pongSeen) {
            if (waited > PONG_TIMEOUT_MAX_MS) pendingPing = null; // server ping-i tanımır — yenə cəhd
            return;
        }
        if (waited > pongTimeoutMs()) {
            handleStall();
        } else if (waited > Math.max(1200, srtt * 2.5)) {
            setQuality("weak");
        }
        return;
    }
    if (now - lastPingSentAt >= PING_INTERVAL_MS) sendPing();
}

function startHeartbeat() {
    stopHeartbeat();
    lastPingSentAt = 0;
    heartbeatTimer = window.setInterval(heartbeatTick, 1000);
    sendPing();
}

// Köhnə socket-in hadisələri artıq nəzərə alınmır (gec gələn `close` yeni socket-i pozmasın).
function abandonSocket() {
    const old = ws;
    ws = null;
    stopHeartbeat();
    window.clearTimeout(connectTimer);
    connectTimer = null;
    if (!old) return;
    old.onopen = null;
    old.onmessage = null;
    old.onerror = null;
    old.onclose = null;
    try {
        old.close();
    } catch (error) {
        // artıq bağlıdır
    }
}

function dropStandby() {
    const old = standby;
    standby = null;
    if (!old) return;
    old.onopen = null;
    old.onmessage = null;
    old.onerror = null;
    old.onclose = null;
    try {
        old.close();
    } catch (error) {
        // artıq bağlıdır
    }
}

function handleStall() {
    // Arxa planda taymerlər boğulur — qayıdanda visibilitychange özü yoxlayır.
    if (document.hidden) {
        pendingPing = null;
        return;
    }
    dropStandby();
    standby = ws;
    ws = null;
    stopHeartbeat();
    window.clearTimeout(connectTimer);
    connectTimer = null;
    setQuality("down");
    if (typeof handlers.onStall === "function") handlers.onStall();
    attempt = 0;
    connect();
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
    window.clearTimeout(connectTimer);
    connectTimer = window.setTimeout(() => {
        if (socket !== ws || socket.readyState !== WebSocket.CONNECTING) return;
        abandonSocket();
        scheduleReconnect();
    }, CONNECT_TIMEOUT_MS);
    socket.onopen = () => {
        if (socket !== ws) return;
        window.clearTimeout(connectTimer);
        connectTimer = null;
        attempt = 0;
        dropStandby();
        startHeartbeat();
        if (typeof handlers.onOpen === "function") handlers.onOpen();
    };
    socket.onmessage = (event) => {
        if (socket !== ws && socket !== standby) return;
        let data = null;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        if (data && data.type === "pong") {
            if (socket === ws) handlePong(data);
            return;
        }
        if (typeof handlers.onMessage === "function") handlers.onMessage(data);
    };
    socket.onerror = () => {
        // onclose həmişə ardınca gəlir — orada idarə olunur
    };
    socket.onclose = (event) => {
        if (socket === standby) {
            standby = null;
            return;
        }
        if (socket !== ws) return;
        ws = null;
        stopHeartbeat();
        window.clearTimeout(connectTimer);
        connectTimer = null;
        setQuality("down");
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

// Şəbəkə qayıdanda / tab görünəndə: bağlıdırsa gözləmədən qoşul, açıqdırsa ping ilə yoxla
// (yuxudan oyanan telefonda «açıq» socket çox vaxt ölüdür).
export function reconnectNow() {
    if (stopped) return;
    if (isSocketOpen()) {
        if (!pendingPing && Date.now() - lastPingSentAt >= PROBE_MIN_GAP_MS) sendPing();
        return;
    }
    if (isSocketConnecting()) return;
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
    abandonSocket();
    dropStandby();
}
