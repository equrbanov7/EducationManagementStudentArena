import { state } from './state.js?v=lx20261002';

/* ═══════════════════════════════════════════════════════════════════
 *  SƏS MÜHƏRRİKİ (2026-09-29 LX-FE-STAGE) — yalnız WebAudio sintezi, fayl yoxdur.
 *  Qraf: [sfx bus, music bus] → master (səs/susdur) → lowpass 9 kHz (sərt
 *  yüksək tezliklər kəsilir) → kompressor/limiter → çıxış.
 *  • Hər cue AÇARLA idempotentdir (`once`): eyni vəziyyətin təkrar render-i
 *    səsi ikiqat çalmır.
 *  • Dövrələr (lobbi musiqisi, drumroll, rəqs ritmi) lookahead planlayıcı ilə
 *    işləyir; eyni adlı dövrə heç vaxt ikinci dəfə başlamır.
 *  • Yalnız təqdimat (proyektor) pəncərəsi səs çalır (CONFIG.presentationOnly) —
 *    idarə səhifəsi + proyektor açıq olanda səs ikiləşmir.
 *  • Seçimlər (səs %, susdur, musiqi) localStorage-da (try/catch).
 * ═══════════════════════════════════════════════════════════════════ */

const Ctor = window.AudioContext || window.webkitAudioContext;
const PREF_KEY = "emsLiveHostSound.v1";
const NOTE = (m) => 440 * 2 ** ((m - 69) / 12);

const eng = {
    ctx: null, master: null, sfx: null, music: null, noiseBuf: null,
    loops: new Map(), want: new Map(), keys: new Map(), listeners: new Set(), lastJoin: 0,
};

function loadPrefs() {
    const fallback = { volume: Number(CONFIG?.sessionSettings?.sfx_volume ?? 70), muted: false, music: true, custom: false };
    try {
        const raw = JSON.parse(window.localStorage.getItem(PREF_KEY) || "null");
        if (raw && typeof raw === "object") {
            return {
                volume: Math.max(0, Math.min(100, Number(raw.volume ?? fallback.volume))),
                muted: Boolean(raw.muted), music: raw.music !== false, custom: true,
            };
        }
    } catch (error) { /* gizli pəncərə / bloklanmış yaddaş */ }
    return fallback;
}

const prefs = loadPrefs();

function savePrefs() {
    try {
        window.localStorage.setItem(PREF_KEY, JSON.stringify({ volume: prefs.volume, muted: prefs.muted, music: prefs.music }));
    } catch (error) { /* yaddaş əlçatmazdır — seçim yalnız bu sessiyada qalır */ }
}

export const audioEnabled = () => Boolean(CONFIG?.presentationOnly) && Boolean(Ctor);
export const soundPrefs = () => ({ volume: prefs.volume, muted: prefs.muted, music: prefs.music });

export function audioStatus() {
    if (!audioEnabled()) return "off";
    if (!eng.ctx) return "idle";
    return eng.ctx.state === "running" ? "running" : "suspended";
}

export function onAudioStatus(listener) {
    eng.listeners.add(listener);
    return () => eng.listeners.delete(listener);
}

function emitStatus() {
    const detail = { status: audioStatus(), ...soundPrefs() };
    eng.listeners.forEach((fn) => { try { fn(detail); } catch (error) { /* dinləyici xətası səsi dayandırmasın */ } });
}

function ctx() {
    if (!audioEnabled()) return null;
    if (eng.ctx) return eng.ctx;
    const c = new Ctor();
    const comp = c.createDynamicsCompressor();
    comp.threshold.value = -16; comp.knee.value = 18; comp.ratio.value = 5;
    comp.attack.value = 0.004; comp.release.value = 0.22;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass"; lp.frequency.value = 9000; lp.Q.value = 0.5;
    eng.master = c.createGain();
    eng.sfx = c.createGain();
    eng.music = c.createGain();
    eng.sfx.connect(eng.master); eng.music.connect(eng.master);
    eng.master.connect(lp); lp.connect(comp); comp.connect(c.destination);
    eng.ctx = c;
    applyGains(true);
    c.onstatechange = () => { if (c.state === "running") startWantedLoops(); emitStatus(); };
    return c;
}

function applyGains(immediate) {
    if (!eng.ctx) return;
    const t = eng.ctx.currentTime;
    const v = prefs.muted ? 0 : (prefs.volume / 100) ** 1.6 * 0.9;
    const m = prefs.music ? 0.55 : 0;
    if (immediate) { eng.master.gain.value = v; eng.music.gain.value = m; return; }
    eng.master.gain.setTargetAtTime(v, t, 0.05);
    eng.music.gain.setTargetAtTime(m, t, 0.08);
}

export function setSfxVolume(value, options = {}) {
    prefs.volume = Math.max(0, Math.min(100, Number(value) || 0));
    state.sfxVolume = prefs.volume;
    if (options.persist !== false) { prefs.custom = true; savePrefs(); }
    applyGains(false);
    const slider = document.getElementById("sfxVolumeSlider");
    if (slider && Number(slider.value) !== prefs.volume) slider.value = prefs.volume;
    const label = document.getElementById("sfxVolumeLabel");
    if (label) label.textContent = `${prefs.volume}%`;
    emitStatus();
}

/** Server tənzimləməsi — yalnız bu cihazda şəxsi seçim edilməyibsə tətbiq olunur. */
export function applyServerVolume(value) {
    if (prefs.custom || value == null) return;
    setSfxVolume(value, { persist: false });
}

export function setMuted(muted) { prefs.muted = Boolean(muted); savePrefs(); applyGains(false); emitStatus(); }
export function setMusicEnabled(on) { prefs.music = Boolean(on); savePrefs(); applyGains(false); emitStatus(); }

export function unlockAudio() {
    const c = ctx();
    if (!c) return;
    if (c.state === "suspended") c.resume().then(() => { startWantedLoops(); emitStatus(); }).catch(() => {});
}

function once(key) {
    if (!key) return true;
    if (eng.keys.has(key)) return false;
    eng.keys.set(key, Date.now());
    if (eng.keys.size > 400) eng.keys.delete(eng.keys.keys().next().value);
    return true;
}

function live() {
    const c = ctx();
    return c && c.state === "running" ? c : null;
}

/* ── Primitivlər ───────────────────────────────────────────────────── */
function tone(o) {
    const c = eng.ctx;
    const t = o.t ?? c.currentTime + 0.01;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = o.type || "sine";
    osc.frequency.setValueAtTime(o.f, t);
    if (o.f2) osc.frequency.exponentialRampToValueAtTime(o.f2, t + (o.glide ?? o.r ?? 0.3));
    const a = o.a ?? 0.012;
    const r = o.r ?? 0.3;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(o.g ?? 0.08, t + a);
    if (o.hold) g.gain.setValueAtTime(o.g ?? 0.08, t + a + o.hold);
    g.gain.setTargetAtTime(0.0001, t + a + (o.hold || 0), r / 3);
    let node = osc;
    if (o.lp) {
        const f = c.createBiquadFilter();
        f.type = "lowpass"; f.frequency.value = o.lp; f.Q.value = o.q ?? 0.7;
        osc.connect(f); node = f;
    }
    node.connect(g);
    g.connect(o.bus || eng.sfx);
    osc.start(t);
    osc.stop(t + a + (o.hold || 0) + r * 2.2 + 0.05);
}

function noiseBuffer() {
    if (eng.noiseBuf) return eng.noiseBuf;
    const c = eng.ctx;
    const buf = c.createBuffer(1, c.sampleRate * 2, c.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
    eng.noiseBuf = buf;
    return buf;
}

function noise(o) {
    const c = eng.ctx;
    const t = o.t ?? c.currentTime + 0.01;
    const src = c.createBufferSource();
    src.buffer = noiseBuffer();
    const f = c.createBiquadFilter();
    f.type = o.ft || "bandpass";
    f.frequency.setValueAtTime(o.f || 1500, t);
    if (o.f2) f.frequency.exponentialRampToValueAtTime(o.f2, t + (o.glide ?? o.r ?? 0.3));
    f.Q.value = o.q ?? 1;
    const g = c.createGain();
    const a = o.a ?? 0.004;
    const r = o.r ?? 0.1;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(o.g ?? 0.1, t + a);
    if (o.hold) g.gain.setValueAtTime(o.g ?? 0.1, t + a + o.hold);
    g.gain.setTargetAtTime(0.0001, t + a + (o.hold || 0), r / 3);
    src.connect(f); f.connect(g); g.connect(o.bus || eng.sfx);
    src.start(t, Math.random() * 1.5);
    src.stop(t + a + (o.hold || 0) + r * 2.2 + 0.05);
}

const pluck = (m, t, g, r, bus, type) => tone({ f: NOTE(m), t, type: type || "triangle", g: g ?? 0.05, a: 0.006, r: r ?? 0.35, lp: 3200, bus });
const chord = (ms, t, g, r, bus, type) => ms.forEach((m) => pluck(m, t, g, r, bus, type));

/* ── Oyun cue-ları ─────────────────────────────────────────────────── */
const PENTA = [72, 74, 76, 79, 81, 84];

export function playJoin(key) {
    const c = live();
    if (!c || !once(key)) return;
    const now = performance.now();
    if (now - eng.lastJoin < 110) return; // bir anda çox qoşulma — səs sel olmasın
    eng.lastJoin = now;
    const m = PENTA[Math.floor(Math.random() * PENTA.length)];
    tone({ f: NOTE(m - 5), f2: NOTE(m), glide: 0.07, type: "sine", g: 0.08, a: 0.004, r: 0.14 });
    tone({ f: NOTE(m + 12), type: "triangle", g: 0.018, a: 0.004, r: 0.1, t: c.currentTime + 0.05 });
}

export function playWhoosh(key) {
    const c = live();
    if (!c || !once(key)) return;
    noise({ ft: "bandpass", f: 280, f2: 3200, glide: 0.42, q: 1.4, g: 0.16, a: 0.18, r: 0.28 });
    tone({ f: 110, f2: 220, glide: 0.4, type: "sine", g: 0.05, a: 0.2, r: 0.25 });
}

export function playIntroSound(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.02;
    [60, 64, 67, 72].forEach((m, i) => pluck(m, t + i * 0.11, 0.07, 0.4));
    chord([48, 55, 64], t + 0.44, 0.03, 1.1, undefined, "sine");
    tone({ f: NOTE(84), t: t + 0.44, type: "sine", g: 0.02, r: 0.8 });
}

export function playCountdownSound(key) {
    const c = live();
    if (!c || !once(key)) return;
    const n = parseInt(String(key).split(":").pop(), 10) || 3;
    const m = { 3: 67, 2: 69, 1: 71 }[n] || 67;
    const t = c.currentTime + 0.01;
    tone({ f: NOTE(m), t, type: "sine", g: 0.13, a: 0.003, r: 0.35 });
    tone({ f: NOTE(m) * 4, t, type: "sine", g: 0.018, a: 0.002, r: 0.08 });
    if (n === 1) chord([72, 76, 79], t + 0.02, 0.02, 0.5, undefined, "sine");
}

export function playTick(key, urgent) {
    const c = live();
    if (!c || !once(key)) return;
    noise({ ft: "bandpass", f: urgent ? 2100 : 1700, q: 7, g: urgent ? 0.22 : 0.16, a: 0.001, r: 0.05 });
    tone({ f: urgent ? 1318 : 1175, type: "sine", g: urgent ? 0.05 : 0.035, a: 0.001, r: 0.05 });
}

export function playTimeUp(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    [[64, 0], [60, 0.22]].forEach(([m, d]) => {
        tone({ f: NOTE(m), t: t + d, type: "triangle", g: 0.09, a: 0.006, r: 0.7, lp: 2200 });
        tone({ f: NOTE(m) * 2.4, t: t + d, type: "sine", g: 0.015, a: 0.004, r: 0.4 });
    });
    tone({ f: 70, f2: 45, glide: 0.3, t, type: "sine", g: 0.12, a: 0.005, r: 0.3 });
}

export function playAllAnswered(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    tone({ f: NOTE(84), t, type: "sine", g: 0.05, r: 0.4 });
    tone({ f: NOTE(88), t: t + 0.09, type: "sine", g: 0.05, r: 0.5 });
}

export function playRevealSound(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    tone({ f: 330, f2: 990, glide: 0.16, t, type: "sine", g: 0.04, a: 0.01, r: 0.12 });
    chord([72, 76, 79], t + 0.16, 0.06, 0.7);
    chord([48, 60], t + 0.16, 0.05, 0.6, undefined, "sine");
    noise({ ft: "highpass", f: 6000, t: t + 0.16, g: 0.025, r: 0.5 });
}

export function playScoreboardSound(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    [72, 74, 76, 79, 81, 84].forEach((m, i) => pluck(m, t + i * 0.065, 0.045, 0.22));
    tone({ f: NOTE(48), t, type: "sine", g: 0.06, r: 0.6 });
}

/* ── Səhnə cue-ları ───────────────────────────────────────────────── */
export function playImpact(key, big) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    tone({ f: 95, f2: 38, glide: 0.35, t, type: "sine", g: big ? 0.42 : 0.3, a: 0.003, r: 0.45 });
    noise({ ft: "lowpass", f: 420, t, g: 0.18, a: 0.002, r: 0.18 });
    if (big) noise({ ft: "highpass", f: 4200, t, g: 0.08, a: 0.004, r: 1.6 });
}

export function playFinalSound(key) { playFanfare(key); }

export function playFanfare(key) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.02;
    const brass = (m, at, hold, g) => {
        tone({ f: NOTE(m), t: at, type: "sawtooth", g: g ?? 0.045, a: 0.03, hold, r: 0.5, lp: 1900, q: 1.1 });
        tone({ f: NOTE(m), t: at, type: "sawtooth", g: (g ?? 0.045) * 0.6, a: 0.03, hold, r: 0.5, lp: 1900, detune: 8 });
    };
    brass(67, t, 0.08); brass(72, t + 0.16, 0.08); brass(76, t + 0.32, 0.08); brass(79, t + 0.48, 0.75, 0.055);
    [60, 64, 67].forEach((m) => tone({ f: NOTE(m), t: t + 0.48, type: "triangle", g: 0.035, a: 0.05, hold: 0.7, r: 0.7, lp: 1600 }));
    [0, 0.48].forEach((d) => tone({ f: 98, f2: 70, glide: 0.25, t: t + d, type: "sine", g: 0.22, a: 0.003, r: 0.3 }));
}

export function playCheer(key, strength = 1) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.02;
    const len = 1.6 + strength * 1.2;
    for (let i = 0; i < 10; i += 1) {
        noise({ ft: "bandpass", f: 500 + Math.random() * 1800, q: 3 + Math.random() * 4, t: t + Math.random() * 0.3, g: 0.022 * strength, a: 0.35, hold: len * 0.4, r: len * 0.5 });
    }
    const claps = Math.round(18 + 22 * strength);
    for (let i = 0; i < claps; i += 1) {
        noise({ ft: "bandpass", f: 1300 + Math.random() * 900, q: 1.2, t: t + Math.random() * len, g: 0.05 * strength, a: 0.001, r: 0.035 });
    }
}

export function playRiser(key, seconds = 1.8) {
    const c = live();
    if (!c || !once(key)) return;
    const t = c.currentTime + 0.01;
    noise({ ft: "bandpass", f: 350, f2: 5200, glide: seconds, q: 2, t, g: 0.09, a: seconds * 0.9, r: 0.2 });
    tone({ f: 160, f2: 640, glide: seconds, t, type: "triangle", g: 0.03, a: seconds * 0.9, r: 0.2, lp: 1800 });
}

/** Barabam təkrarı — `seconds` ərzində crescendo; qaytarılan funksiya dayandırır. */
export function startDrumroll(key, seconds = 3, from = 0.03, to = 0.14) {
    const c = live();
    if (!c || !once(key)) return () => {};
    const bus = c.createGain();
    bus.connect(eng.sfx);
    const t0 = c.currentTime + 0.02;
    const hits = Math.round(seconds * 19);
    for (let i = 0; i < hits; i += 1) {
        const k = i / hits;
        noise({ ft: "bandpass", f: 1900 + Math.random() * 300, q: 0.9, t: t0 + i / 19 + Math.random() * 0.008, g: from + (to - from) * k * k, a: 0.001, r: 0.06, bus });
    }
    tone({ f: 82, t: t0, type: "sine", g: 0.05, a: seconds * 0.8, hold: 0.1, r: 0.3, bus });
    return () => {
        try { bus.gain.setTargetAtTime(0, c.currentTime, 0.03); setTimeout(() => bus.disconnect(), 400); } catch (error) { /* artıq bağlanıb */ }
    };
}

/* ── Dövrələr (lookahead planlayıcı) ──────────────────────────────── */
function startLoop(name, spec) {
    const existing = eng.loops.get(name);
    if (existing && existing.id === spec.id) return;
    stopLoop(name, 0.15);
    eng.want.set(name, spec);
    const c = live();
    if (!c) return;
    const stepDur = 60 / spec.bpm / 4;
    const bus = c.createGain();
    bus.gain.value = spec.gain ?? 1;
    bus.connect(spec.music ? eng.music : eng.sfx);
    const loop = { id: spec.id, bus, step: 0, next: c.currentTime + 0.08, timer: 0 };
    loop.timer = window.setInterval(() => {
        const cc = eng.ctx;
        if (!cc || cc.state !== "running") return;
        if (loop.next < cc.currentTime) loop.next = cc.currentTime + 0.05; // gizli tab boşluğundan sonra
        while (loop.next < cc.currentTime + 0.25) {
            spec.onStep(loop.step, loop.next, bus, stepDur);
            loop.step += 1;
            loop.next += stepDur;
            if (spec.maxSteps && loop.step >= spec.maxSteps) {
                stopLoop(name, 1.2);
                if (typeof spec.onEnd === "function") spec.onEnd();
                return;
            }
        }
    }, 50);
    eng.loops.set(name, loop);
}

function stopLoop(name, fade = 0.25) {
    eng.want.delete(name);
    const loop = eng.loops.get(name);
    if (!loop) return;
    window.clearInterval(loop.timer);
    eng.loops.delete(name);
    try {
        loop.bus.gain.setTargetAtTime(0, eng.ctx.currentTime, fade / 3);
        window.setTimeout(() => loop.bus.disconnect(), fade * 1000 + 400);
    } catch (error) { /* kontekst bağlanıb */ }
}

function startWantedLoops() {
    eng.want.forEach((spec, name) => { if (!eng.loops.has(name)) startLoop(name, spec); });
}

export function stopAllLoops() {
    Array.from(eng.loops.keys()).forEach((name) => stopLoop(name, 0.3));
    eng.want.clear();
}

const PROG_LOBBY = [[48, [60, 64, 67]], [43, [59, 62, 67]], [45, [60, 64, 69]], [41, [60, 65, 69]]];

function lobbyStep(mode) {
    return (step, t, bus, sd) => {
        const bar = Math.floor(step / 16) % 4;
        const s = step % 16;
        const [root, tri] = PROG_LOBBY[bar];
        if (s === 0) tri.forEach((m) => tone({ f: NOTE(m), t, type: "triangle", g: 0.022, a: 0.35, hold: sd * 10, r: 1.4, lp: 1300, bus }));
        if (mode === "focus") {
            if (s === 0 || s === 8) pluck(tri[s === 0 ? 2 : 1] + 12, t, 0.03, 0.9, bus, "sine");
            return;
        }
        if (s === 0 || s === 8) tone({ f: NOTE(root + 12), t, type: "triangle", g: 0.07, a: 0.01, r: 0.45, lp: 520, bus });
        if (s === 14) tone({ f: NOTE(root + 14), t, type: "triangle", g: 0.045, a: 0.01, r: 0.2, lp: 520, bus });
        if (s % 4 === 2) pluck([tri[0], tri[1], tri[2], tri[1]][(s - 2) / 4] + 12, t, 0.03, 0.28, bus, "sine");
        if (s === 4 || s === 12) noise({ ft: "highpass", f: 7500, t, g: 0.012, a: 0.002, r: 0.05, bus });
    };
}

export function stopLobbyMusic() { stopLoop("lobby", 0.6); }

export function syncLobbyMusic() {
    const mode = String(state.sessionSettings?.lobby_music || "original");
    if (state.sessionState !== "lobby" || mode === "silent" || !audioEnabled()) {
        stopLobbyMusic();
        return;
    }
    const bpm = mode === "focus" ? 72 : 96;
    startLoop("lobby", { id: `lobby:${mode}`, bpm, music: true, gain: 1, onStep: lobbyStep(mode) });
}

const PROG_DANCE = [[48, [60, 64, 67]], [45, [57, 60, 64]], [41, [57, 60, 65]], [43, [59, 62, 67]]];

export function startDanceBeat(maxBars = 32, onEnd) {
    startLoop("dance", {
        id: "dance", bpm: 112, music: true, gain: 1, maxSteps: maxBars * 16, onEnd,
        onStep(step, t, bus) {
            const bar = Math.floor(step / 16) % 4;
            const s = step % 16;
            const [root, tri] = PROG_DANCE[bar];
            if (s === 0 || s === 8 || (bar === 3 && s === 10)) tone({ f: 150, f2: 46, glide: 0.11, t, type: "sine", g: 0.36, a: 0.002, r: 0.2, bus });
            if (s === 4 || s === 12) {
                noise({ ft: "bandpass", f: 1500, q: 0.9, t, g: 0.13, a: 0.001, r: 0.09, bus });
                noise({ ft: "bandpass", f: 1500, q: 0.9, t: t + 0.012, g: 0.1, a: 0.001, r: 0.1, bus });
            }
            if (s % 2 === 0) noise({ ft: "highpass", f: 7200, t, g: s % 4 === 2 ? 0.03 : 0.02, a: 0.001, r: s === 6 || s === 14 ? 0.12 : 0.03, bus });
            if ([0, 3, 6, 8, 11, 14].includes(s)) tone({ f: NOTE(root + (s === 11 ? 19 : 12)), t, type: "triangle", g: 0.11, a: 0.004, r: 0.16, lp: 700, bus });
            if (s === 4 || s === 12 || s === 7) chord(tri, t, 0.02, 0.12, bus);
            if (bar === 3 && s % 2 === 0 && s < 8) pluck([79, 76, 72, 76][s / 2], t, 0.03, 0.3, bus, "sine");
        },
    });
}

export function stopDanceBeat() { stopLoop("dance", 1); }
