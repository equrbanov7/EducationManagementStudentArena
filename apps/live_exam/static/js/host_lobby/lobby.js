import { $ } from './dom.js';
import { UI } from './dom.js';
import { PHASES } from './constants.js';
import { state } from './state.js';
import { setPresentationMarkup } from './presentation.js';
import {
    answerWord,
    avatarImageMarkup,
    avatarMarkup,
    buildJoinUrl,
    controlsEnabled,
    currentQrUrl,
    esc,
    fmt,
    joinUrlLabel,
    lobbyCopy,
    notifyHostShell,
    progressLabel,
    toMs,
    tr,
} from './utils.js';

export function renderIdleStage() {
    const copy = lobbyCopy();
    const joinedCount = Number(state.totalPlayers || 0);
    const audienceText = joinedCount > 0 ? fmt(copy.audienceLabel, { count: joinedCount }) : copy.audienceEmpty;
    const joinUrl = joinUrlLabel(buildJoinUrl());
    const waitingLabel = state.isLocked ? copy.lockedLabel : copy.waitingLabel;
    const waitingHint = state.isLocked ? copy.lockedHint : copy.waitingHint;
    const audienceSignature = (state.players || [])
        .map(player =>
            [
                Number(player?.id || 0),
                String(player?.nickname || ""),
                String(player?.avatar_key || ""),
                String(player?.accessory_key || ""),
            ].join(":")
        )
        .join("|");
    const audienceMarkup = state.players.length
        ? state.players
            .map(
                player => `
                    <article class="lobby-stage__audience-card" data-player-id="${Number(player?.id || 0)}">
                        <div class="lobby-stage__audience-avatar">${avatarImageMarkup(player, 64, "host-avatar-image--stage-participant")}</div>
                        <div class="lobby-stage__audience-name">${esc(player?.nickname || "")}</div>
                        ${
                            controlsEnabled()
                                ? `
                                    <button
                                        type="button"
                                        class="lobby-stage__audience-remove"
                                        data-remove-player-id="${Number(player?.id || 0)}"
                                        aria-label="${esc(copy.removePlayerLabel)}: ${esc(player?.nickname || "player")}"
                                        title="${esc(copy.removePlayerLabel)}">
                                        <i class="fas fa-user-minus"></i>
                                    </button>
                                `
                                : ""
                        }
                    </article>
                `
            )
            .join("")
        : `<div class="lobby-stage__audience-empty">${esc(copy.playersEmpty)}</div>`;

    setPresentationMarkup(
        PHASES.IDLE,
        `idle:${joinedCount}:${state.isLocked ? "locked" : "open"}:${state.sessionSettings.two_step_join === false ? "direct" : "pin"}:${audienceSignature}`,
        `
            <section class="present-view present-view--lobby">
                <header class="lobby-stage__join-board">
                    <div class="lobby-stage__join-copy">
                        <span class="lobby-stage__eyebrow">${esc(copy.joinLabel)}</span>
                        <strong>${esc(joinUrl || CONFIG.entryUrl || "")}</strong>
                        <p>${esc(copy.joinHint)}</p>
                    </div>
                    <div class="lobby-stage__pin">
                        <span class="lobby-stage__eyebrow">${esc(copy.pinLabel)}</span>
                        <strong>${esc(CONFIG.pin)}</strong>
                        <small>${esc(audienceText)}</small>
                    </div>
                    <button type="button" class="lobby-stage__qr" data-action="open-qr" aria-label="QR">
                        <img src="${esc(currentQrUrl())}" alt="QR">
                    </button>
                </header>

                <div class="lobby-stage__hero">
                    <div class="stage-pill stage-pill--brand">${esc(copy.brand)}</div>
                    <h1 class="stage-title stage-title--lobby">${esc(CONFIG.examTitle || tr("introTitle", "Quiz"))}</h1>
                    <div class="lobby-stage__status ${state.isLocked ? "is-locked" : ""}">
                        <span class="lobby-stage__status-dot" aria-hidden="true"></span>
                        <span>${esc(waitingLabel)}</span>
                    </div>
                </div>

                <section class="lobby-stage__audience-dock ${state.players.length ? "" : "is-empty"}" aria-label="${esc(copy.participantsTitle)}">
                    <header class="lobby-stage__audience-head">
                        <div class="lobby-stage__audience-copy">
                            <span class="lobby-stage__audience-kicker">${esc(copy.participantsTitle)}</span>
                            <strong>${esc(audienceText)}</strong>
                        </div>
                        <span class="lobby-stage__audience-count">${joinedCount}</span>
                    </header>
                    <div class="lobby-stage__audience-list">
                        ${audienceMarkup}
                    </div>
                </section>

                <footer class="lobby-stage__footer">
                    <div class="lobby-stage__meta lobby-stage__meta--muted">${esc(waitingHint)}</div>
                </footer>
            </section>
        `
    );
}

export function renderLobbyPlayers(players, totalCount = null) {
    state.players = Array.isArray(players) ? players : [];
    const expectedTotal = Number.isFinite(Number(totalCount)) ? Number(totalCount) : Number(state.players.length);
    state.totalPlayers = expectedTotal;

    if (UI.playersCount) {
        UI.playersCount.textContent = state.totalPlayers;
    }
    updateAnsweredCounter();

    if (!UI.playersList) {
        notifyHostShell();
        return;
    }

    UI.playersList.innerHTML = "";
    if (!state.players.length) {
        const empty = document.createElement("div");
        empty.className = "players-empty";
        empty.textContent = lobbyCopy().playersEmpty;
        UI.playersList.appendChild(empty);
        notifyHostShell();
        return;
    }

    state.players.forEach(player => {
        const chip = document.createElement("article");
        chip.className = "player-chip";
        chip.dataset.playerId = String(player.id);
        chip.innerHTML = `
            <div class="player-chip__avatar">${avatarMarkup(player, 54, "host-avatar host-avatar--chip")}</div>
            <div class="player-chip__name">${esc(player.nickname || "")}</div>
            ${
                !CONFIG.presentationOnly && state.sessionState === "lobby"
                    ? `
                        <button
                            type="button"
                            class="player-chip__remove"
                            data-remove-player-id="${Number(player.id || 0)}"
                            aria-label="Remove ${esc(player.nickname || "player")}">
                            <i class="fas fa-user-minus"></i>
                        </button>
                    `
                    : ""
            }
        `;
        UI.playersList.appendChild(chip);
    });

    notifyHostShell();
}

export function updateAnsweredCounter() {
    const answered = Number(state.answeredCount || 0);
    const total = Number(state.totalPlayers || 0);
    UI.answeredText.textContent = `${answered} / ${total}`;

    const counter = $("answerCounterValue");
    const counterNumber = $("answerCounterNumber");
    const counterLabel = $("answerCounterLabel");
    const subline = $("answerCounterSubline");
    if (counter) {
        counter.textContent = `${answered} ${answerWord(answered)}`;
    }
    if (counterNumber) {
        counterNumber.textContent = `${answered}`;
    }
    if (counterLabel) {
        counterLabel.textContent = answerWord(answered);
    }
    if (subline) {
        subline.textContent = fmt(tr("playersAnswered", "{answered} answered"), { answered });
    }
}

export function updateTimerBadge(nowMs) {
    const value = $("answerTimerValue");
    const badge = $("answerTimerBadge");
    if (!value || !badge || !state.questionPlan) return;
    const deadline = nowMs < state.questionPlan.answerStart ? state.questionPlan.answerStart : state.questionPlan.endsAt;
    const leftSeconds = Math.max(0, Math.ceil((deadline - nowMs) / 1000));
    value.textContent = `${leftSeconds}`;
    badge.classList.toggle("is-warning", leftSeconds <= 10 && leftSeconds > 5);
    badge.classList.toggle("is-danger", leftSeconds <= 5);
}

export function updateQuestionIntroProgress(nowMs) {
    const fill = $("questionOnlyBarFill");
    if (!fill || !state.questionPlan) return;
    const start = Number(state.questionPlan.countdownEnd || 0);
    const end = Number(state.questionPlan.answerStart || 0);
    const duration = Math.max(1, end - start);
    const progress = Math.max(0, Math.min(1, (nowMs - start) / duration));
    fill.style.width = `${Math.round(progress * 100)}%`;
}

export function buildQuestionPlan(question) {
    const startedAt = toMs(question?.started_at);
    const getReadyMs = Math.max(0, Number(question?.get_ready_duration_ms || 0));
    const introMs = Math.max(0, Number(question?.intro_duration_ms || 0));
    const readyEndsAt = toMs(question?.ready_ends_at) || (startedAt + getReadyMs);
    const answerStart = toMs(question?.answer_starts_at) || (readyEndsAt + introMs);
    const endsAt = toMs(question?.ends_at);
    const hasCountdown = getReadyMs > 0;
    const quizDuration = hasCountdown ? Math.max(850, Math.min(1000, getReadyMs - 2200)) : 0;
    const countdownStart = hasCountdown ? startedAt + quizDuration : readyEndsAt;
    const countdownEnd = hasCountdown ? readyEndsAt : readyEndsAt;

    return {
        startedAt,
        quizEnd: hasCountdown ? startedAt + quizDuration : startedAt,
        countdownStart,
        countdownEnd,
        readyEndsAt,
        answerStart,
        endsAt,
        hasCountdown,
        getReadyMs,
        introMs,
    };
}

export function distributionLookup(payload) {
    const counts = new Map();
    const rows = payload?.distribution?.counts || [];
    rows.forEach(row => {
        counts.set(Number(row.option_id || 0), Number(row.count || 0));
    });
    return {
        counts,
        totalAnswers: Number(payload?.distribution?.total_answers || 0),
    };
}
