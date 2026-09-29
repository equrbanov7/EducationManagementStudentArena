// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının yeganə vəziyyət obyekti.
import { BOOTSTRAP } from './config.js?v=lx20260929';

export const state = {
    player: Object.assign({ score: 0 }, BOOTSTRAP.player || {}),
    // Cari sual (question_published / snapshot) və ona verilmiş cavab.
    currentQuestion: null,
    selectedIds: new Set(),
    currentAnswer: null,
    // Göndərilmiş, amma hələ təsdiqlənməmiş cavab: {questionId, payload, sentAt, via}.
    pendingSubmit: null,
    typedDraft: "",
    phase: "",
    viewKey: "",
    // Reveal: {key, payload}; eyni reveal təkrar gələndə (WS + snapshot) səs/animasiya təkrarlanmır.
    revealKey: "",
    revealPayload: null,
    finalKey: "",
    lastTop: [],
    totalPlayers: 0,
    // Taymerlər (hamısı timers.js vasitəsilə təmizlənir).
    ticker: null,
    pollTimer: null,
    watchdogTimer: null,
    phaseTimer: null,
    ackTimer: null,
    serverTimeOffsetMs: 0,
    hasServerOffset: false,
    timelineMeta: null,
    removed: false,
};
