// LX-FE-PLAYER (2026-09-29): sabit (bir dəfə render olunan) elementlər. Faza-spesifik elementlər
// view-ların içindədir və yalnız class/data-atributla tapılır (keçid zamanı iki view ola bilər).
export const $ = (id) => document.getElementById(id);

export const UI = {
    shell: $("lxpShell"),
    netBanner: $("netBanner"),
    netSignal: $("netSignal"),
    questionChip: $("questionChip"),
    timerBox: $("timerBox"),
    timerText: $("timerText"),
    timeBar: $("timeBar"),
    timeBarFill: $("timeBarFill"),
    soundToggle: $("soundToggle"),
    views: $("lxpViews"),
    playerAvatar: $("playerAvatar"),
    playerName: $("playerName"),
    playerScore: $("playerScore"),
    playerRank: $("playerRank"),
    toast: $("lxpToast"),
    fx: $("lxpFx"),
    live: $("lxpLive"),
};
