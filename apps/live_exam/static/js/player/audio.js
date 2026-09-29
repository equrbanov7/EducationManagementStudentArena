// LX-FE-PLAYER (2026-09-29): telefon səsləri — WebAudio sintezi (xarici fayl yoxdur).
// Musiqili, yumşaq zərf (attack/decay), low-pass süzgəc və kompressor; susdurma localStorage-da.
// Brauzerin autoplay siyasətinə görə kontekst ilk toxunuşda açılır (unlockAudio).
const AudioCtor = window.AudioContext || window.webkitAudioContext;
const STORE_KEY = "lx.player.sound";
const MASTER_LEVEL = 0.6;

let ctx = null;
let master = null;
let noiseBuffer = null;
let muted = readMuted();
const lastKeys = Object.create(null);
const listeners = new Set();

function readMuted() {
    try {
        return window.localStorage.getItem(STORE_KEY) === "off";
    } catch (error) {
        return false;
    }
}

function persist() {
    try {
        window.localStorage.setItem(STORE_KEY, muted ? "off" : "on");
    } catch (error) {
        // localStorage bağlı ola bilər (gizli rejim) — səs seçimi sadəcə yadda qalmır.
    }
}

function notify() {
    listeners.forEach((fn) => {
        try {
            fn();
        } catch (error) {
            // dinləyici xətası səs mühərrikini sındırmamalıdır
        }
    });
}

function build() {
    if (ctx || !AudioCtor) return;
    try {
        ctx = new AudioCtor();
    } catch (error) {
        ctx = null;
        return;
    }
    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -18;
    compressor.knee.value = 12;
    compressor.ratio.value = 4;
    compressor.attack.value = 0.004;
    compressor.release.value = 0.18;
    master = ctx.createGain();
    master.gain.value = muted ? 0 : MASTER_LEVEL;
    master.connect(compressor);
    compressor.connect(ctx.destination);
    ctx.onstatechange = notify;
}

export function unlockAudio() {
    if (!AudioCtor) return;
    build();
    if (ctx && ctx.state === "suspended") {
        ctx.resume().then(notify).catch(() => {});
    }
}

export function audioState() {
    if (!AudioCtor) return "unsupported";
    if (!ctx) return "locked";
    return ctx.state === "running" ? "running" : "locked";
}

export function isMuted() {
    return muted;
}

export function setMuted(value) {
    muted = Boolean(value);
    persist();
    if (ctx && master) {
        master.gain.cancelScheduledValues(ctx.currentTime);
        master.gain.setTargetAtTime(muted ? 0 : MASTER_LEVEL, ctx.currentTime, 0.03);
    }
    notify();
}

export function onAudioChange(fn) {
    if (typeof fn === "function") listeners.add(fn);
}

function tone({ at, freq, dur, type = "sine", gain = 0.06, endFreq = 0, attack = 0.012, filter = 4200 }) {
    const osc = ctx.createOscillator();
    const amp = ctx.createGain();
    const lowpass = ctx.createBiquadFilter();
    lowpass.type = "lowpass";
    lowpass.frequency.value = filter;
    lowpass.Q.value = 0.6;
    osc.type = type;
    osc.frequency.setValueAtTime(freq, at);
    if (endFreq) {
        osc.frequency.exponentialRampToValueAtTime(Math.max(30, endFreq), at + dur);
    }
    amp.gain.setValueAtTime(0.0001, at);
    amp.gain.exponentialRampToValueAtTime(gain, at + attack);
    amp.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(lowpass);
    lowpass.connect(amp);
    amp.connect(master);
    osc.start(at);
    osc.stop(at + dur + 0.05);
}

// Zəng tembri: əsas ton + zəif harmoniklər (yumşaq, «oyuncaq ksilofon» səsi).
function bell(at, freq, dur, gain) {
    tone({ at, freq, dur, type: "sine", gain });
    tone({ at, freq: freq * 2, dur: dur * 0.6, type: "sine", gain: gain * 0.22 });
    tone({ at, freq: freq * 3.01, dur: dur * 0.35, type: "sine", gain: gain * 0.07 });
}

function noiseSweep(at, dur, gain, from, to) {
    if (!noiseBuffer) {
        const length = Math.floor(ctx.sampleRate * 0.6);
        noiseBuffer = ctx.createBuffer(1, length, ctx.sampleRate);
        const data = noiseBuffer.getChannelData(0);
        for (let i = 0; i < length; i += 1) data[i] = Math.random() * 2 - 1;
    }
    const source = ctx.createBufferSource();
    source.buffer = noiseBuffer;
    const band = ctx.createBiquadFilter();
    band.type = "bandpass";
    band.Q.value = 1.3;
    band.frequency.setValueAtTime(from, at);
    band.frequency.exponentialRampToValueAtTime(to, at + dur);
    const amp = ctx.createGain();
    amp.gain.setValueAtTime(0.0001, at);
    amp.gain.exponentialRampToValueAtTime(gain, at + dur * 0.35);
    amp.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    source.connect(band);
    band.connect(amp);
    amp.connect(master);
    source.start(at);
    source.stop(at + dur + 0.05);
}

const N = {
    C4: 261.63,
    E4: 329.63,
    G4: 392.0,
    B4: 493.88,
    C5: 523.25,
    E5: 659.25,
    G5: 783.99,
    A5: 880.0,
    B5: 987.77,
    C6: 1046.5,
    D6: 1174.66,
    E6: 1318.51,
    G6: 1567.98,
};

const CUES = {
    tap(at) {
        tone({ at, freq: N.A5, dur: 0.07, type: "triangle", gain: 0.04, filter: 3000 });
    },
    select(at) {
        tone({ at, freq: N.E5, dur: 0.08, type: "triangle", gain: 0.04, filter: 3200 });
    },
    deselect(at) {
        tone({ at, freq: N.C5, dur: 0.08, type: "triangle", gain: 0.035, filter: 2600 });
    },
    denied(at) {
        tone({ at, freq: N.E4, dur: 0.12, type: "triangle", gain: 0.05, filter: 1800 });
        tone({ at: at + 0.09, freq: N.C4, dur: 0.14, type: "triangle", gain: 0.05, filter: 1600 });
    },
    lock(at) {
        bell(at, N.E5, 0.18, 0.065);
        bell(at + 0.08, N.B5, 0.32, 0.065);
    },
    correct(at) {
        [N.C5, N.E5, N.G5].forEach((f, i) => bell(at + i * 0.08, f, 0.22, 0.055));
        bell(at + 0.24, N.C6, 0.6, 0.07);
    },
    partial(at) {
        bell(at, N.E5, 0.2, 0.055);
        bell(at + 0.1, N.G5, 0.45, 0.055);
    },
    wrong(at) {
        tone({ at, freq: N.E4, dur: 0.26, type: "triangle", gain: 0.07, filter: 1500, endFreq: 311.13 });
        tone({ at: at + 0.17, freq: 246.94, dur: 0.5, type: "sine", gain: 0.075, filter: 1200, endFreq: 207.65 });
    },
    timeup(at) {
        bell(at, N.G4, 0.5, 0.055);
        tone({ at, freq: 196, dur: 0.7, type: "sine", gain: 0.045, filter: 900 });
    },
    tick(at) {
        tone({ at, freq: N.E6, dur: 0.045, type: "sine", gain: 0.04, filter: 6000 });
        tone({ at, freq: 2637, dur: 0.025, type: "triangle", gain: 0.01, filter: 6000 });
    },
    count(at) {
        bell(at, N.A5, 0.14, 0.045);
    },
    go(at) {
        bell(at, N.E6, 0.3, 0.055);
    },
    question(at) {
        noiseSweep(at, 0.32, 0.045, 500, 3200);
        bell(at + 0.2, N.G5, 0.2, 0.04);
    },
    streak(at) {
        [N.G5, N.B5, N.D6, N.G6].forEach((f, i) => bell(at + i * 0.055, f, 0.16, 0.035));
        noiseSweep(at + 0.05, 0.35, 0.016, 4000, 9000);
    },
    leaderboard(at) {
        [N.G4, N.C5, N.E5].forEach((f, i) => bell(at + i * 0.09, f, 0.3, 0.04));
    },
    fanfare(at) {
        [N.C5, N.E5, N.G5, N.C6].forEach((f, i) => bell(at + i * 0.11, f, 0.25, 0.06));
        [N.C5, N.E5, N.G5, N.C6].forEach((f) =>
            tone({ at: at + 0.48, freq: f, dur: 1.4, type: "triangle", gain: 0.03, filter: 3200 })
        );
        noiseSweep(at + 0.45, 0.9, 0.018, 3000, 8000);
    },
    finale(at) {
        [N.C5, N.E5, N.G5].forEach((f) => tone({ at, freq: f, dur: 1.2, type: "sine", gain: 0.045, attack: 0.06 }));
        bell(at + 0.15, N.C6, 0.6, 0.035);
    },
    pop(at) {
        tone({ at, freq: N.C6, endFreq: N.G6, dur: 0.09, type: "sine", gain: 0.045 });
    },
};

// `key` verilərsə eyni səs eyni açarla ikinci dəfə çalınmır (eyni faza təkrar render olanda).
export function playSound(name, key) {
    const cue = CUES[name];
    if (!cue || muted || !ctx || ctx.state !== "running") return false;
    if (key !== undefined && key !== null) {
        const normalized = String(key);
        if (lastKeys[name] === normalized) return false;
        lastKeys[name] = normalized;
    }
    try {
        cue(ctx.currentTime + 0.015);
    } catch (error) {
        return false;
    }
    return true;
}
