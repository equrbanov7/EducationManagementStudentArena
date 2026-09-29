// LX-FE-PLAYER (2026-09-29): toxunma titrəyişi (navigator.vibrate) — yalnız dəstəklənəndə və
// istifadəçi səhifəyə artıq toxunubsa (əks halda Chrome «intervention» xəbərdarlığı yazır).
const canVibrate = typeof navigator !== "undefined" && typeof navigator.vibrate === "function";
let activated = false;

export const HAPTIC = Object.freeze({
    tap: 12,
    select: 8,
    denied: [16, 40, 16],
    lock: [10, 30, 18],
    correct: [18, 50, 28],
    partial: [18, 60],
    wrong: [70],
    timeup: [40, 60, 40],
    finale: [30, 50, 30, 50, 90],
});

export function markUserActivation() {
    activated = true;
}

function hasActivation() {
    if (activated) return true;
    const ua = typeof navigator !== "undefined" ? navigator.userActivation : null;
    return Boolean(ua && ua.hasBeenActive);
}

export function buzz(pattern) {
    if (!canVibrate || !pattern || !hasActivation()) return;
    try {
        navigator.vibrate(pattern);
    } catch (error) {
        // bəzi brauzerlər (iOS) dəstəkləmir — səssiz keçirik
    }
}
