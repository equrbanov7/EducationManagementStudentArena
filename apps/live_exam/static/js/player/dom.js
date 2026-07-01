export const $ = (id) => document.getElementById(id);

export const UI = {
    questionChip: $("questionChip"),
    quizTitleText: $("quizTitleText"),
    connStatus: $("connStatus"),
    connStatusText: document.querySelector("#connStatus .live-player-connection__text"),
    timerBox: $("timerBox"),
    timerText: $("timerText"),
    phasePanelInner: $("phasePanelInner"),
    optionsShell: $("optionsShell"),
    optionsContainer: $("optionsContainer"),
    multiActions: $("multiActions"),
    selectCounter: $("selectCounter"),
    submitBtn: $("submitBtn"),
    playerAvatar: $("playerAvatar"),
    playerName: $("playerName"),
    playerScore: $("playerScore"),
    roundProgressText: $("roundProgressText"),
};
