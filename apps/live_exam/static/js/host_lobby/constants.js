export const PHASES = {
    IDLE: "idle",
    INTRO: "intro",
    COUNTDOWN: "countdown",
    QUESTION: "question",
    ANSWERS: "answers",
    REVEAL: "reveal",
    SCOREBOARD: "scoreboard",
    // Sahib 2026-09-30: son sualdan sonra liderlər lövhəsi əvəzinə qısa «Nəticələr…» fazası.
    SUSPENSE: "suspense",
    FINISHED: "finished",
};

export const STATE_POLL_INTERVAL_MS = 2500;
// Sahib 2026-09-30: lobbidə oyunçu siyahısının avtomatik sinxronu (yalnız host, bir sorğu).
export const LOBBY_RESYNC_INTERVAL_MS = 15000;
// Lobbidə eyni anda göstərilən maksimum oyunçu "baloncuğu" (qalanı «+N»).
export const LOBBY_MAX_BUBBLES = 60;
// Liderlər lövhəsində göstərilən sətirlər.
export const SCOREBOARD_ROWS = 5;
// Son sualdan sonrakı gərginlik fazasının defolt müddəti (server `final_suspense_ms` göndərir).
export const FINAL_SUSPENSE_MS = 2500;
