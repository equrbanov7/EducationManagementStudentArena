// LXNET (2026-10-02): server saatının təxmini — NTP üsulu.
//
// Əvvəl: hər WS mesajında `server_time − qəbul anı` EWMA ilə ortalanırdı. Bu nümunə həmişə
// birtərəfli şəbəkə gecikməsi qədər AŞAĞIdır → zəif şəbəkədə telefonun saatı serverdən geri qalırdı
// (slow 3G ≈ 0.4 s, itkili şəbəkədə gecikmiş bir mesajdan sonra 1.6 s-ə qədər) və cavab plitələri
// həmin qədər GEC açılırdı — gecikmə birbaşa bal itkisinə çevrilirdi.
//
// İndi:
//  * gediş-gəliş nümunələri (WS ping→pong, HTTP snapshot): server vaxtı [t0, t1] arasındadır →
//    ofset ∈ [st − t1, st − t0]; təxmin = ən kiçik RTT-li nümunənin ortası;
//  * birtərəfli (push) nümunələr yalnız AŞAĞI SƏRHƏDdir (mesaj göndəriləndən tez çata bilməz);
//  * sərhədlər ziddiyyətlidirsə (telefonun saatı dəyişib) köhnə nümunələr atılır.
const WINDOW_MS = 120000;
const MAX_SAMPLES = 12;
const TOLERANCE_MS = 25;

let roundTrips = [];
let pushBounds = [];
let current = { offset: 0, known: false, rtt: 0 };

function parse(value) {
    if (!value) return 0;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function prune(now) {
    roundTrips = roundTrips.filter((s) => now - s.at <= WINDOW_MS).slice(-MAX_SAMPLES);
    pushBounds = pushBounds.filter((s) => now - s.at <= WINDOW_MS).slice(-MAX_SAMPLES);
}

function bounds() {
    let lower = -Infinity;
    let upper = Infinity;
    roundTrips.forEach((s) => {
        lower = Math.max(lower, s.lower);
        upper = Math.min(upper, s.upper);
    });
    pushBounds.forEach((s) => {
        lower = Math.max(lower, s.lower);
    });
    return { lower, upper };
}

function recompute(now) {
    prune(now);
    let { lower, upper } = bounds();
    if (lower > upper + TOLERANCE_MS) {
        // Ziddiyyət: telefonun saatı dəyişib — yalnız ən təzə nümunələr saxlanılır.
        const lastRt = roundTrips[roundTrips.length - 1];
        roundTrips = lastRt ? [lastRt] : [];
        pushBounds = lastRt ? pushBounds.filter((s) => s.at >= lastRt.at) : pushBounds.slice(-1);
        ({ lower, upper } = bounds());
        if (lower > upper + TOLERANCE_MS) {
            pushBounds = [];
            ({ lower, upper } = bounds());
        }
    }
    const best = roundTrips.reduce((acc, s) => (!acc || s.rtt < acc.rtt ? s : acc), null);
    let offset;
    if (best) {
        offset = best.mid;
        if (Number.isFinite(lower) && offset < lower) offset = lower;
        if (Number.isFinite(upper) && offset > upper) offset = upper;
    } else if (Number.isFinite(lower)) {
        offset = lower;
    } else {
        return current;
    }
    current = { offset: Math.round(offset), known: true, rtt: best ? best.rtt : 0 };
    return current;
}

// Gediş-gəliş: `t0` sorğu göndərilən, `t1` cavab alınan an (Date.now()), `serverIso` — server vaxtı.
export function recordRoundTrip(t0, serverIso, t1) {
    const st = parse(serverIso);
    if (!st || !Number.isFinite(t0) || !Number.isFinite(t1) || t1 < t0) return current;
    roundTrips.push({ at: t1, rtt: t1 - t0, lower: st - t1, upper: st - t0, mid: st - (t0 + t1) / 2 });
    return recompute(t1);
}

// Birtərəfli push (WS hadisəsi): yalnız aşağı sərhəd.
export function recordPush(serverIso, receivedAt = Date.now()) {
    const st = parse(serverIso);
    if (!st || !Number.isFinite(receivedAt)) return current;
    pushBounds.push({ at: receivedAt, lower: st - receivedAt });
    return recompute(receivedAt);
}

export function clockOffsetMs() {
    return current.offset;
}

export function clockKnown() {
    return current.known;
}

export function resetClock() {
    roundTrips = [];
    pushBounds = [];
    current = { offset: 0, known: false, rtt: 0 };
}
