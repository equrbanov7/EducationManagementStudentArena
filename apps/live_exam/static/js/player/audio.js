import { AudioCtor } from './config.js';
import { state } from './state.js';

export function getAudioContext() {
    if (!AudioCtor) return null;
    if (!state.audioContext) {
        state.audioContext = new AudioCtor();
    }
    return state.audioContext;
}

export function unlockAudio() {
    const ctx = getAudioContext();
    if (!ctx || ctx.state !== "suspended") return;
    ctx.resume().catch(() => {});
}

function playTone(ctx, config) {
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    const startTime = config.startTime;
    const duration = config.duration;
    const peak = config.gain;

    oscillator.type = config.type || "sine";
    oscillator.frequency.setValueAtTime(config.frequency, startTime);
    if (config.endFrequency) {
        oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, config.endFrequency), startTime + duration);
    }

    gainNode.gain.setValueAtTime(0.0001, startTime);
    gainNode.gain.exponentialRampToValueAtTime(peak, startTime + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    oscillator.start(startTime);
    oscillator.stop(startTime + duration + 0.02);
}

export function playRoundEndSound(revealKey) {
    if (state.lastRoundSoundKey === revealKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.01;
        playTone(ctx, {
            startTime: base,
            duration: 0.12,
            frequency: 520,
            endFrequency: 420,
            gain: 0.045,
            type: "triangle",
        });
        playTone(ctx, {
            startTime: base + 0.06,
            duration: 0.26,
            frequency: 320,
            endFrequency: 220,
            gain: 0.06,
            type: "sine",
        });
        state.lastRoundSoundKey = revealKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}

export function playLeaderboardSound(revealKey) {
    if (state.lastScoreSoundKey === revealKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.01;
        [290, 360, 430].forEach((frequency, index) => {
            playTone(ctx, {
                startTime: base + index * 0.08,
                duration: 0.12,
                frequency,
                endFrequency: frequency * 1.03,
                gain: 0.035,
                type: "square",
            });
        });
        playTone(ctx, {
            startTime: base + 0.02,
            duration: 0.34,
            frequency: 180,
            endFrequency: 140,
            gain: 0.022,
            type: "triangle",
        });
        state.lastScoreSoundKey = revealKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}

export function playFinalSound(finalKey) {
    if (state.lastFinalSoundKey === finalKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.02;
        [261.63, 329.63, 392, 523.25, 659.25].forEach((frequency, index) => {
            playTone(ctx, {
                startTime: base + index * 0.09,
                duration: index === 4 ? 0.58 : 0.24,
                frequency,
                endFrequency: frequency * 1.015,
                gain: index === 4 ? 0.048 : 0.032,
                type: index < 3 ? "triangle" : "sine",
            });
        });
        playTone(ctx, {
            startTime: base + 0.03,
            duration: 0.82,
            frequency: 130.81,
            endFrequency: 98,
            gain: 0.018,
            type: "sine",
        });
        state.lastFinalSoundKey = finalKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}
