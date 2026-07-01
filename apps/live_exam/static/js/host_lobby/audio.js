import { state } from './state.js';

const AudioCtor = window.AudioContext || window.webkitAudioContext;

/* ═══════════════════════════════════════════════════════════════════
 *  SOUND EFFECTS SYSTEM
 *  ────────────────────
 *  All game sounds are synthesized via the Web Audio API below.
 *  To change a specific sound, find its function by name:
 *
 *    playIntroSound      – "Get ready" jingle before a question
 *    playCountdownSound  – 3-2-1 countdown beeps (escalating pitch)
 *    playRevealSound     – Dramatic reveal when answers are shown
 *    playScoreboardSound – Energetic build-up for the leaderboard
 *    playFinalSound      – Victory fanfare on the final podium
 *    scheduleLobbyMusicLoop – Background lobby music patterns
 *
 *  Each function contains clearly labelled note arrays you can
 *  tweak (frequency, duration, gain, type).
 *
 *  Volume is controlled by the master gain node (state.sfxVolume,
 *  range 0-100). The slider lives in the settings drawer.
 * ═══════════════════════════════════════════════════════════════════ */

function getAudioContext() {
    if (!AudioCtor) return null;
    if (!state.audioContext) {
        state.audioContext = new AudioCtor();
    }
    return state.audioContext;
}

function getMasterGain() {
    const context = getAudioContext();
    if (!context) return null;
    if (!state.masterGain) {
        state.masterGain = context.createGain();
        state.masterGain.connect(context.destination);
    }
    const vol = Math.max(0, Math.min(100, Number(state.sfxVolume ?? 70)));
    state.masterGain.gain.value = vol / 100;
    return state.masterGain;
}

export function setSfxVolume(value) {
    state.sfxVolume = Math.max(0, Math.min(100, Number(value) || 0));
    const master = getMasterGain();
    if (master) {
        master.gain.value = state.sfxVolume / 100;
    }
    const slider = document.getElementById("sfxVolumeSlider");
    if (slider && Number(slider.value) !== state.sfxVolume) {
        slider.value = state.sfxVolume;
    }
    const label = document.getElementById("sfxVolumeLabel");
    if (label) label.textContent = `${state.sfxVolume}%`;
}

export function unlockAudio() {
    const context = getAudioContext();
    if (!context || context.state !== "suspended") return;
    context.resume().then(() => {
        getMasterGain();
        syncLobbyMusic(true);
    }).catch(() => {});
}

/**
 * Core tone generator. All sounds are built from layered calls to this.
 * @param {AudioContext} context
 * @param {Object} config – { startTime, duration, frequency, endFrequency?, gain, type }
 */
function playTone(context, config) {
    const master = getMasterGain();
    if (!master) return;

    const oscillator = context.createOscillator();
    const gainNode = context.createGain();
    const startTime = config.startTime;
    const duration = config.duration;

    oscillator.type = config.type || "triangle";
    oscillator.frequency.setValueAtTime(config.frequency, startTime);
    if (config.endFrequency) {
        oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, config.endFrequency), startTime + duration);
    }
    if (config.detune) {
        oscillator.detune.setValueAtTime(config.detune, startTime);
    }

    gainNode.gain.setValueAtTime(0.0001, startTime);
    gainNode.gain.linearRampToValueAtTime(config.gain || 0.04, startTime + (config.attack || 0.015));
    if (config.sustain != null && config.sustainEnd != null) {
        gainNode.gain.setValueAtTime(config.sustain, startTime + config.sustainEnd);
    }
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

    oscillator.connect(gainNode);
    gainNode.connect(master);
    oscillator.start(startTime);
    oscillator.stop(startTime + duration + 0.05);
}

function withAudio(fn) {
    const context = getAudioContext();
    if (!context) return;
    if (context.state === "suspended") {
        context.resume().then(() => fn(context)).catch(() => {});
        return;
    }
    fn(context);
}

/* ── Intro Sound: bright ascending arpeggio ("Get ready!") ──────── */
export function playIntroSound(key) {
    if (!CONFIG.presentationOnly || state.lastIntroSoundKey === key) return;
    withAudio(context => {
        const t = context.currentTime + 0.01;
        // Rising arpeggio: C4 → E4 → G4 → C5 with sparkle
        const notes = [
            { offset: 0.00, freq: 262, end: 280, dur: 0.18, gain: 0.06, type: "triangle" },
            { offset: 0.10, freq: 330, end: 350, dur: 0.18, gain: 0.06, type: "triangle" },
            { offset: 0.20, freq: 392, end: 420, dur: 0.20, gain: 0.07, type: "triangle" },
            { offset: 0.32, freq: 523, end: 560, dur: 0.30, gain: 0.08, type: "sine" },
        ];
        notes.forEach(n => {
            playTone(context, { startTime: t + n.offset, duration: n.dur, frequency: n.freq, endFrequency: n.end, gain: n.gain, type: n.type });
        });
        // Sub bass warmth
        playTone(context, { startTime: t, duration: 0.5, frequency: 131, endFrequency: 165, gain: 0.025, type: "sine" });
        // Shimmer layer
        playTone(context, { startTime: t + 0.32, duration: 0.35, frequency: 1047, endFrequency: 1100, gain: 0.015, type: "sine" });
        state.lastIntroSoundKey = key;
    });
}

/* ── Countdown Sound: escalating tension beeps (3, 2, 1) ────────── */
export function playCountdownSound(key) {
    if (!CONFIG.presentationOnly || state.lastCountdownSoundKey === key) return;
    withAudio(context => {
        const t = context.currentTime + 0.01;
        // Extract number from key: "xxx:3" → 3, "xxx:2" → 2, "xxx:1" → 1
        const parts = String(key).split(":");
        const num = parseInt(parts[parts.length - 1], 10) || 3;
        // Higher pitch as countdown decreases: 3→low, 2→mid, 1→high
        const pitches = { 3: 440, 2: 554, 1: 659 };
        const baseFreq = pitches[num] || 440;

        // Main beep with percussive attack
        playTone(context, { startTime: t, duration: 0.18, frequency: baseFreq, endFrequency: baseFreq * 0.92, gain: 0.09, type: "square", attack: 0.005 });
        // Soft harmonic layer
        playTone(context, { startTime: t, duration: 0.22, frequency: baseFreq * 2, endFrequency: baseFreq * 1.8, gain: 0.025, type: "sine", attack: 0.005 });
        // Sub pulse
        playTone(context, { startTime: t, duration: 0.12, frequency: baseFreq / 2, gain: 0.04, type: "triangle", attack: 0.003 });

        // On "1" add extra emphasis - a bright resolve
        if (num === 1) {
            playTone(context, { startTime: t + 0.06, duration: 0.28, frequency: baseFreq * 1.5, endFrequency: baseFreq * 1.6, gain: 0.04, type: "sine" });
        }
        state.lastCountdownSoundKey = key;
    });
}

/* ── Lobby Music: ambient background loop patterns ──────────────── */
export function stopLobbyMusic() {
    if (state.lobbyMusicTimer) {
        clearTimeout(state.lobbyMusicTimer);
        state.lobbyMusicTimer = 0;
    }
    state.lobbyMusicMode = "";
}

function scheduleLobbyMusicLoop(mode) {
    const context = getAudioContext();
    if (!context || context.state !== "running" || state.sessionState !== "lobby" || mode === "silent") {
        stopLobbyMusic();
        return;
    }

    // Lobby music patterns – tweak notes here to change the vibe
    const patterns = {
        original: {
            loopMs: 3200,
            notes: [
                { offset: 0.00, duration: 0.22, frequency: 196, endFrequency: 220, gain: 0.016, type: "triangle" },
                { offset: 0.24, duration: 0.18, frequency: 246.94, endFrequency: 261.63, gain: 0.013, type: "sine" },
                { offset: 0.52, duration: 0.22, frequency: 293.66, endFrequency: 329.63, gain: 0.015, type: "triangle" },
                { offset: 0.84, duration: 0.24, frequency: 392, endFrequency: 440, gain: 0.016, type: "triangle" },
                { offset: 1.24, duration: 0.26, frequency: 164.81, endFrequency: 174.61, gain: 0.01, type: "sine" },
                { offset: 1.56, duration: 0.18, frequency: 261.63, endFrequency: 293.66, gain: 0.012, type: "square" },
            ],
        },
        focus: {
            loopMs: 3600,
            notes: [
                { offset: 0.00, duration: 0.34, frequency: 174.61, endFrequency: 196, gain: 0.012, type: "sine" },
                { offset: 0.44, duration: 0.26, frequency: 220, endFrequency: 233.08, gain: 0.01, type: "triangle" },
                { offset: 0.96, duration: 0.36, frequency: 261.63, endFrequency: 293.66, gain: 0.011, type: "sine" },
                { offset: 1.54, duration: 0.24, frequency: 196, endFrequency: 174.61, gain: 0.009, type: "triangle" },
            ],
        },
    };

    const selected = patterns[mode] || patterns.original;
    const base = context.currentTime + 0.04;
    selected.notes.forEach((note) => {
        playTone(context, {
            startTime: base + note.offset,
            duration: note.duration,
            frequency: note.frequency,
            endFrequency: note.endFrequency,
            gain: note.gain,
            type: note.type,
        });
    });

    state.lobbyMusicMode = mode;
    if (state.lobbyMusicTimer) {
        clearTimeout(state.lobbyMusicTimer);
    }
    state.lobbyMusicTimer = window.setTimeout(() => {
        scheduleLobbyMusicLoop(mode);
    }, selected.loopMs);
}

export function syncLobbyMusic(force = false) {
    const mode = String(state.sessionSettings.lobby_music || "original");
    const context = getAudioContext();
    const shouldPlay = state.sessionState === "lobby" && mode !== "silent";

    if (!shouldPlay || !context || context.state !== "running") {
        stopLobbyMusic();
        return;
    }

    if (!force && state.lobbyMusicMode === mode && state.lobbyMusicTimer) {
        return;
    }

    scheduleLobbyMusicLoop(mode);
}

/* ── Reveal Sound: dramatic suspense-to-resolve flourish ────────── */
export function playRevealSound(key) {
    if (state.lastRevealSoundKey === key) return;
    withAudio(context => {
        const t = context.currentTime + 0.01;
        // Suspenseful descending sweep
        playTone(context, { startTime: t, duration: 0.14, frequency: 880, endFrequency: 440, gain: 0.04, type: "sawtooth", attack: 0.005 });
        // Resolve chord: bright major chord (C-E-G)
        playTone(context, { startTime: t + 0.12, duration: 0.35, frequency: 523, endFrequency: 530, gain: 0.055, type: "triangle" });
        playTone(context, { startTime: t + 0.14, duration: 0.32, frequency: 659, endFrequency: 665, gain: 0.04, type: "sine" });
        playTone(context, { startTime: t + 0.16, duration: 0.30, frequency: 784, endFrequency: 790, gain: 0.035, type: "sine" });
        // Deep bass hit
        playTone(context, { startTime: t + 0.10, duration: 0.4, frequency: 131, endFrequency: 110, gain: 0.04, type: "sine" });
        state.lastRevealSoundKey = key;
    });
}

/* ── Scoreboard Sound: energetic ascending fanfare ──────────────── */
export function playScoreboardSound(key) {
    if (state.lastScoreboardSoundKey === key) return;
    withAudio(context => {
        const t = context.currentTime + 0.01;
        // Quick ascending scale with rhythmic punch: C-D-E-F-G-C5
        const arpeggio = [
            { offset: 0.00, freq: 262, dur: 0.10, gain: 0.06, type: "square" },
            { offset: 0.07, freq: 294, dur: 0.10, gain: 0.06, type: "square" },
            { offset: 0.14, freq: 330, dur: 0.10, gain: 0.06, type: "triangle" },
            { offset: 0.21, freq: 349, dur: 0.10, gain: 0.06, type: "triangle" },
            { offset: 0.28, freq: 392, dur: 0.12, gain: 0.07, type: "triangle" },
            { offset: 0.38, freq: 523, dur: 0.28, gain: 0.08, type: "sine" },
        ];
        arpeggio.forEach(n => {
            playTone(context, { startTime: t + n.offset, duration: n.dur, frequency: n.freq, endFrequency: n.freq * 1.02, gain: n.gain, type: n.type, attack: 0.005 });
        });
        // Warm bass underneath
        playTone(context, { startTime: t, duration: 0.6, frequency: 131, endFrequency: 165, gain: 0.03, type: "sine" });
        // Top shimmer on final note
        playTone(context, { startTime: t + 0.38, duration: 0.3, frequency: 1047, endFrequency: 1060, gain: 0.015, type: "sine" });
        state.lastScoreboardSoundKey = key;
    });
}

/* ── Final/Victory Sound: celebratory fanfare with harmony ──────── */
export function playFinalSound(key) {
    if (state.lastFinalSoundKey === key) return;
    withAudio(context => {
        const t = context.currentTime + 0.02;
        // Triumphant ascending fanfare: C-E-G-C5-E5 with big sustain
        const fanfare = [
            { offset: 0.00, freq: 262, dur: 0.22, gain: 0.06, type: "triangle" },
            { offset: 0.12, freq: 330, dur: 0.22, gain: 0.06, type: "triangle" },
            { offset: 0.24, freq: 392, dur: 0.24, gain: 0.07, type: "triangle" },
            { offset: 0.38, freq: 523, dur: 0.30, gain: 0.08, type: "sine" },
            { offset: 0.54, freq: 659, dur: 0.65, gain: 0.09, type: "sine" },
        ];
        fanfare.forEach(n => {
            playTone(context, { startTime: t + n.offset, duration: n.dur, frequency: n.freq, endFrequency: n.freq * 1.01, gain: n.gain, type: n.type });
            // Doubled octave below for richness
            playTone(context, { startTime: t + n.offset + 0.01, duration: n.dur * 0.8, frequency: n.freq / 2, endFrequency: n.freq / 2, gain: n.gain * 0.35, type: "sine" });
        });
        // Grand bass foundation
        playTone(context, { startTime: t, duration: 1.2, frequency: 131, endFrequency: 98, gain: 0.035, type: "sine" });
        // Sparkle overtone on the final sustained note
        playTone(context, { startTime: t + 0.56, duration: 0.6, frequency: 1318, endFrequency: 1400, gain: 0.012, type: "sine" });
        playTone(context, { startTime: t + 0.60, duration: 0.5, frequency: 1568, endFrequency: 1600, gain: 0.008, type: "sine" });
        state.lastFinalSoundKey = key;
    });
}
