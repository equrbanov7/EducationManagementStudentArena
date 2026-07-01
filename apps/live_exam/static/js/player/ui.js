import { BOOTSTRAP, WAITING_MESSAGES } from './config.js';
import { UI } from './dom.js';
import { state } from './state.js';
import { avatarMarkup, formatClock, isMulti, maxSelect, tr } from './utils.js';

export function setRoundHint(text) {
    if (UI.roundProgressText) {
        UI.roundProgressText.textContent = text || "";
    }
}

export function setConnection(kind) {
    if (!UI.connStatus || !UI.connStatusText) {
        return;
    }
    UI.connStatus.classList.remove("is-online", "is-offline");
    if (kind === "online") {
        UI.connStatus.classList.add("is-online");
        UI.connStatusText.textContent = tr("connectionOnline", "Online");
        return;
    }
    if (kind === "offline") {
        UI.connStatus.classList.add("is-offline");
        UI.connStatusText.textContent = tr("connectionOffline", "Offline");
        return;
    }
    UI.connStatusText.textContent = tr("connectionConnecting", "Connecting");
}

export function setTimerState(show, milliseconds = 0) {
    UI.timerBox.classList.toggle("is-visible", Boolean(show));
    UI.timerBox.classList.remove("is-warning", "is-danger");
    if (!show) {
        UI.timerText.textContent = "--:--";
        return;
    }

    UI.timerText.textContent = formatClock(milliseconds);
    const seconds = Math.ceil(Math.max(0, milliseconds) / 1000);
    if (seconds <= 5) {
        UI.timerBox.classList.add("is-danger");
    } else if (seconds <= 10) {
        UI.timerBox.classList.add("is-warning");
    }
}

export function setQuestionChip(question) {
    if (!question || !question.index) {
        UI.questionChip.textContent = tr("questionLabel", "Question");
        return;
    }
    UI.questionChip.textContent = `${tr("questionLabel", "Question")} ${question.index}`;
}

export function setScore(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    state.player.score = parsed;
    UI.playerScore.textContent = String(parsed);
}

export function renderPlayerIdentity() {
    if (UI.quizTitleText) {
        UI.quizTitleText.textContent = BOOTSTRAP.quizTitle || "Quiz";
    }
    UI.playerName.textContent = state.player.nickname || "Player";
    UI.playerAvatar.innerHTML = avatarMarkup(state.player, 72, "player-avatar");
    setScore(state.player.score || 0);
}

export function hideOptions() {
    UI.optionsShell.style.display = "none";
    UI.optionsContainer.innerHTML = "";
    UI.multiActions.style.display = "none";
    UI.submitBtn.disabled = true;
}

export function disableOptions() {
    document.querySelectorAll(".option-btn").forEach((button) => {
        button.disabled = true;
    });
    UI.submitBtn.disabled = true;
}

export function updateCounter() {
    if (!isMulti(state.currentQuestion)) {
        UI.multiActions.style.display = "none";
        return;
    }
    const maximum = maxSelect(state.currentQuestion);
    UI.multiActions.style.display = "flex";
    UI.selectCounter.textContent = `Selected ${state.selectedIds.size} / ${maximum}`;
    UI.submitBtn.disabled = state.selectedIds.size === 0 || state.submitting;
}

export function pickWaitingMessage() {
    const pool = WAITING_MESSAGES.filter((message) => message !== state.lastWaitingMessage);
    const source = pool.length ? pool : WAITING_MESSAGES;
    const choice = source[Math.floor(Math.random() * source.length)] || WAITING_MESSAGES[0];
    state.lastWaitingMessage = choice;
    return choice;
}
