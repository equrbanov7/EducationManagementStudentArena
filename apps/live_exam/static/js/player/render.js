import { LEADERBOARD_LIMIT, PHASES, PODIUM_SIZE } from './config.js';
import { UI } from './dom.js';
import { playFinalSound, playLeaderboardSound } from './audio.js';
import { stopStatePolling } from './polling.js';
import { state } from './state.js';
import { clearPhaseTimer, clearTicker } from './timers.js';
import {
    avatarMarkup,
    buildQuestionCard,
    esc,
    fmt,
    getPersonalResult,
    getRevealKey,
    normalizeTopRows,
    nowMs,
    optionMarkerMarkup,
    ordinal,
    setStoredTop,
    showQuestionsOnDevices,
    topSignature,
    tr,
    ts,
} from './utils.js';
import {
    hideOptions,
    pickWaitingMessage,
    setQuestionChip,
    setRoundHint,
    setScore,
    setTimerState,
    updateCounter,
} from './ui.js';

let optionClickHandler = () => {};

export function setOptionClickHandler(handler) {
    optionClickHandler = typeof handler === "function" ? handler : () => {};
}

function animateNumber(element, fromValue, toValue, duration = 900) {
    if (!element) return;
    const from = Number(fromValue);
    const to = Number(toValue);
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) {
        element.textContent = String(toValue);
        return;
    }

    const startedAt = performance.now();
    const step = (timestamp) => {
        const progress = Math.min(1, (timestamp - startedAt) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = Math.round(from + ((to - from) * eased));
        element.textContent = String(value);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };

    window.requestAnimationFrame(step);
}

export function renderIdle() {
    clearTicker();
    clearPhaseTimer();
    state.phase = PHASES.IDLE;
    state.currentQuestion = null;
    state.currentAnswer = null;
    state.revealPayload = null;
    state.resultSignature = "";
    state.leaderboardSignature = "";
    state.finalSignature = "";
    hideOptions();
    setTimerState(false);
    setQuestionChip(null);
    setRoundHint(tr("waitingForHost", "Waiting for the host to start the next round."));
    UI.phasePanelInner.innerHTML = `
        <div class="phase-shell">
            <div class="phase-kicker"><i class="fa-solid fa-circle-play"></i><span>Live Exam</span></div>
            <div class="phase-arch"></div>
            <h1 class="phase-title">${esc(tr("getReadyTitle", "Get ready"))}</h1>
            <p class="phase-subtitle">${esc(tr("waitingForHost", "Waiting for the host to start the next round."))}</p>
        </div>
    `;
}

export function renderGetReady(question) {
    if (state.phase !== PHASES.GET_READY) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-kicker"><i class="fa-solid fa-bolt"></i><span>Live mode</span></div>
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(tr("getReadyTitle", "Get ready"))}</h1>
                <p class="phase-subtitle">${esc(tr("getReadyBody", "Loading the first question..."))}</p>
            </div>
        `;
        state.phase = PHASES.GET_READY;
    }
    setRoundHint(tr("getReadyBody", "Loading the first question..."));
}

export function renderIntro(question) {
    if (state.phase !== PHASES.INTRO) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                ${buildQuestionCard(
                    question,
                    `
                        <div class="intro-progress">
                                <div class="intro-progress__track">
                                    <div class="intro-progress__meter" data-intro-meter></div>
                                </div>
                                <div class="intro-progress__meta">
                                <span>${esc(
                                    showQuestionsOnDevices()
                                        ? tr("introHint", "Read the question. Answers are about to appear.")
                                        : tr("introHintMainScreen", "Look at the main screen. Answers unlock soon.")
                                )}</span>
                                <span data-intro-countdown></span>
                            </div>
                        </div>
                    `
                )}
            </div>
        `;
        state.phase = PHASES.INTRO;
    }
    updateIntroProgress(question);
    setRoundHint(
        showQuestionsOnDevices()
            ? tr("introHint", "Read the question. Answers are about to appear.")
            : tr("introHintMainScreen", "Look at the main screen. Answers unlock soon.")
    );
}

export function updateIntroProgress(question) {
    const meter = UI.phasePanelInner.querySelector("[data-intro-meter]");
    const countdown = UI.phasePanelInner.querySelector("[data-intro-countdown]");
    if (!meter || !countdown) return;

    const readyEndsAt = ts(question.ready_ends_at) || ts(question.started_at);
    const answerStartsAt = ts(question.answer_starts_at);
    const now = nowMs();
    const total = Math.max(1, answerStartsAt - readyEndsAt);
    const elapsed = Math.max(0, Math.min(total, now - readyEndsAt));
    const percent = Math.max(0, Math.min(100, (elapsed / total) * 100));
    meter.style.width = `${percent}%`;

    const seconds = Math.max(1, Math.ceil((answerStartsAt - now) / 1000));
    countdown.textContent = `${tr("introUnlocking", "Answers unlock in")} ${seconds}s`;
}

export function renderOptions(question) {
    UI.optionsContainer.innerHTML = "";

    (question.options || []).forEach((option, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `option-btn opt-${index % 6}`;
        button.dataset.id = String(option.id);
        if (state.selectedIds.has(option.id)) {
            button.classList.add("selected");
        }
        button.innerHTML = `
            ${optionMarkerMarkup(option, index)}
            <span class="option-text">${esc(
                showQuestionsOnDevices() ? option.text || "" : tr("optionHiddenBody", "Match this answer on the main screen.")
            )}</span>
        `;
        button.addEventListener("click", () => optionClickHandler(button, option.id));
        UI.optionsContainer.appendChild(button);
    });
}

export function renderQuestion(question) {
    if (state.phase !== PHASES.QUESTION) {
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                ${buildQuestionCard(question)}
            </div>
        `;
        renderOptions(question);
        UI.optionsShell.style.display = "grid";
        state.phase = PHASES.QUESTION;
    }

    document.querySelectorAll(".option-btn").forEach((button) => {
        button.disabled = state.submitting;
    });
    updateCounter();
    setRoundHint(tr("questionPrompt", "Pick your answer before the timer runs out."));
    const endsAt = ts(question.ends_at);
    setTimerState(true, Math.max(0, endsAt - nowMs()));
}

export function renderWaiting(message) {
    if (state.phase !== PHASES.WAITING) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(state.currentQuestion);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(message)}</h1>
                <p class="phase-subtitle">${esc(tr("waitingBody", "Hold tight while the rest of the class answers."))}</p>
                <div class="waiting-progress">
                    <div class="waiting-progress__track">
                        <div class="waiting-progress__meter" data-waiting-meter></div>
                    </div>
                    <div class="waiting-progress__meta">
                        <span data-waiting-count></span>
                    </div>
                </div>
            </div>
        `;
        state.phase = PHASES.WAITING;
    }
    updateWaitingProgress();
    setRoundHint(tr("answerLocked", "Answer locked in"));
}

export function renderLocked() {
    if (state.phase !== PHASES.LOCKED) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(state.currentQuestion);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-kicker"><i class="fa-solid fa-hourglass-end"></i><span>Round closed</span></div>
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(tr("answerTimeout", "Time is up. Waiting for the round to close."))}</h1>
                <p class="phase-subtitle">${esc(tr("waitingBody", "Hold tight while the rest of the class answers."))}</p>
                <div class="waiting-progress">
                    <div class="waiting-progress__track">
                        <div class="waiting-progress__meter" data-waiting-meter></div>
                    </div>
                    <div class="waiting-progress__meta">
                        <span data-waiting-count></span>
                    </div>
                </div>
            </div>
        `;
        state.phase = PHASES.LOCKED;
    }
    updateWaitingProgress();
    setRoundHint(tr("answerTimeout", "Time is up. Waiting for the round to close."));
}

export function updateWaitingProgress() {
    const count = UI.phasePanelInner.querySelector("[data-waiting-count]");
    const meter = UI.phasePanelInner.querySelector("[data-waiting-meter]");
    const total = Math.max(0, Number(state.totalPlayers || 0));
    const answered = Math.max(0, Number(state.answeredCount || 0));
    if (count) {
        if (total > 0) {
            count.textContent = fmt(tr("waitingProgress", "{answered} of {total} answered"), {
                answered,
                total,
            });
        } else {
            count.textContent = tr("waitingBody", "Hold tight while the rest of the class answers.");
        }
    }
    if (meter) {
        const percent = total > 0 ? Math.max(0, Math.min(100, (answered / total) * 100)) : 0;
        meter.style.width = `${percent}%`;
    }
}

export function renderResult(payload) {
    clearTicker();
    hideOptions();
    setTimerState(false);
    setQuestionChip(state.currentQuestion);

    const personalResult = getPersonalResult(payload);
    const hasAnswer = Boolean(personalResult);
    const isCorrect = Boolean(personalResult && personalResult.is_correct);
    const title = isCorrect ? tr("resultCorrect", "Correct") : tr("resultIncorrect", "Incorrect");
    const icon = isCorrect ? "fa-check" : "fa-xmark";
    const rankText = hasAnswer && personalResult.answer_rank
        ? ordinal(personalResult.answer_rank)
        : tr("resultNoRank", "No rank");
    const points = hasAnswer ? Number(personalResult.awarded_points || 0) : 0;
    // IMPORTANT: guard against null before Number() — Number(null) === 0 and is
    // "finite", which used to zero every non-answering player's total score at
    // reveal time. Server payloads remain the source of truth; when neither a
    // personal result nor a pending score exists, keep the last known total.
    const personalTotalScore = hasAnswer && personalResult.total_score != null
        ? Number(personalResult.total_score)
        : NaN;
    const pendingScoreValue = state.pendingScore != null ? Number(state.pendingScore) : NaN;
    const totalScore = Number.isFinite(personalTotalScore)
        ? personalTotalScore
        : (Number.isFinite(pendingScoreValue) ? pendingScoreValue : Number(state.player.score) || 0);
    const resultSignature = [
        getRevealKey(payload),
        hasAnswer ? 1 : 0,
        isCorrect ? 1 : 0,
        points,
        totalScore,
        Number(personalResult?.answer_rank || 0),
    ].join(":");

    if (state.phase === PHASES.RESULT && state.resultSignature === resultSignature) {
        return;
    }

    setScore(totalScore);
    state.pendingScore = null;
    state.phase = PHASES.RESULT;
    state.resultSignature = resultSignature;

    const subtitle = hasAnswer
        ? `${tr("resultAnswered", "You answered")} ${rankText}`
        : tr("resultNoAnswer", "No answer submitted");

    UI.phasePanelInner.innerHTML = `
        <div class="result-shell ${isCorrect ? "is-correct" : "is-wrong"}">
            <div class="result-shell__icon"><i class="fa-solid ${icon}"></i></div>
            <h1 class="result-shell__title">${esc(title)}</h1>
            <div class="result-stats">
                <div class="result-stat">
                    <div class="result-stat__label">${esc(tr("resultEarned", "Earned"))}</div>
                    <div class="result-stat__value">${points > 0 ? `+${points}` : "0"}</div>
                </div>
                <div class="result-stat">
                    <div class="result-stat__label">${esc(tr("resultAnswered", "You answered"))}</div>
                    <div class="result-stat__value">${esc(rankText)}</div>
                </div>
            </div>
            <p class="result-shell__subtitle">${esc(subtitle)}</p>
        </div>
    `;

    setRoundHint(isCorrect ? tr("resultCorrect", "Correct") : subtitle);
}

export function renderLeaderboard(payload) {
    clearTicker();
    hideOptions();
    setTimerState(false);
    setQuestionChip(state.currentQuestion);

    const revealKey = getRevealKey(payload);
    const currentRows = normalizeTopRows(payload && payload.top).slice(0, LEADERBOARD_LIMIT);
    const previousRows = normalizeTopRows(
        payload && payload.previous_top && payload.previous_top.length ? payload.previous_top : state.lastTop
    );
    const leaderboardSignature = `${revealKey}|${topSignature(previousRows)}|${topSignature(currentRows)}`;

    if (state.phase === PHASES.LEADERBOARD && state.leaderboardSignature === leaderboardSignature) {
        return;
    }

    state.phase = PHASES.LEADERBOARD;
    state.revealPayload = payload;
    state.resultSignature = "";
    state.leaderboardSignature = leaderboardSignature;
    state.finalSignature = "";

    UI.phasePanelInner.innerHTML = `
        <div class="leaderboard-shell">
            <div class="phase-kicker"><i class="fa-solid fa-trophy"></i><span>${esc(tr("scoreboardTopFive", "Top 5 players"))}</span></div>
            <h1 class="leaderboard-shell__title">${esc(tr("scoreboardTitle", "Leaderboard"))}</h1>
            <p class="phase-subtitle">${esc(tr("scoreboardSubtitle", "Updated totals after this round."))}</p>
            <div class="leaderboard-list" id="leaderboardList"></div>
        </div>
    `;

    const list = document.getElementById("leaderboardList");
    if (!list) {
        setStoredTop(payload && payload.top);
        return;
    }

    if (!currentRows.length) {
        list.innerHTML = `<div class="final-row"><span class="final-row__name">${esc(tr("waitingForHost", "Waiting for the host to start the next round."))}</span></div>`;
        setStoredTop(payload && payload.top);
        return;
    }

    const previousRankMap = new Map(previousRows.map((row, index) => [row._key, index + 1]));
    const previousScoreMap = new Map(previousRows.map((row) => [row._key, row.score]));
    const currentRankMap = new Map(currentRows.map((row, index) => [row._key, index + 1]));

    const startRows = currentRows
        .slice()
        .sort((a, b) => {
            const aPrev = previousRankMap.get(a._key) || (100 + (currentRankMap.get(a._key) || 0));
            const bPrev = previousRankMap.get(b._key) || (100 + (currentRankMap.get(b._key) || 0));
            return aPrev - bPrev;
        });

    list.innerHTML = startRows
        .map((row) => {
            const currentRank = currentRankMap.get(row._key) || 0;
            const previousRank = previousRankMap.get(row._key) || 0;
            const movedUpBy = previousRank > 0 && previousRank > currentRank ? previousRank - currentRank : 0;
            const enteredTop = !previousRank;
            const movementLabel = movedUpBy > 0
                ? `↑ ${movedUpBy}`
                : (enteredTop ? "↑" : "");

            return `
                <article
                    class="leaderboard-row ${Number(row.player_id) === Number(state.player.id) ? "is-self" : ""} ${movementLabel ? "is-rising" : ""}"
                    data-player-key="${esc(row._key)}"
                    style="order:${previousRank || (100 + currentRank)}">
                    <div class="leaderboard-row__left">
                        <span class="leaderboard-row__rank" data-rank>${currentRank}</span>
                        <span class="leaderboard-row__avatar">${avatarMarkup(row, 44, "leaderboard-row__avatar-art")}</span>
                        <span class="leaderboard-row__name">${esc(row.nickname)}</span>
                    </div>
                    <div class="leaderboard-row__right">
                        <span class="leaderboard-row__score" data-score-value>${Math.round(row.score)}</span>
                        ${
                            movementLabel
                                ? `<span class="leaderboard-row__movement" aria-hidden="true">${esc(movementLabel)}</span>`
                                : ""
                        }
                    </div>
                </article>
            `;
        })
        .join("");

    const rowElements = new Map(
        Array.from(list.querySelectorAll("[data-player-key]")).map((element) => [element.dataset.playerKey, element])
    );

    const firstRects = new Map(
        Array.from(rowElements.entries()).map(([key, element]) => [key, element.getBoundingClientRect()])
    );

    currentRows.forEach((row, index) => {
        const element = rowElements.get(row._key);
        if (!element) return;
        element.style.order = String(index + 1);
        const rankEl = element.querySelector("[data-rank]");
        if (rankEl) {
            rankEl.textContent = String(index + 1);
        }
    });

    list.offsetHeight;

    const lastRects = new Map(
        Array.from(rowElements.entries()).map(([key, element]) => [key, element.getBoundingClientRect()])
    );

    rowElements.forEach((element, key) => {
        const firstRect = firstRects.get(key);
        const lastRect = lastRects.get(key);
        const deltaY = firstRect && lastRect ? firstRect.top - lastRect.top : 0;
        if (deltaY) {
            element.style.transition = "none";
            element.style.transform = `translateY(${deltaY}px)`;
        }
    });

    list.offsetHeight;

    rowElements.forEach((element) => {
        element.style.transition = "transform 680ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 240ms ease";
        element.style.transform = "translateY(0)";
    });

    currentRows.forEach((row) => {
        const element = rowElements.get(row._key);
        const scoreEl = element?.querySelector("[data-score-value]");
        const previousScore = previousScoreMap.get(row._key);
        if (!scoreEl) return;
        if (Number.isFinite(previousScore) && previousScore !== row.score) {
            animateNumber(scoreEl, previousScore, row.score, 920);
            return;
        }
        scoreEl.textContent = String(Math.round(row.score));
    });

    playLeaderboardSound(revealKey);

    setStoredTop(payload && payload.top);
    setRoundHint(tr("scoreboardTitle", "Leaderboard"));
}

export function renderFinal(payload) {
    const finalRows = normalizeTopRows(payload && payload.top);
    const finalSignature = `${String(payload?.finished_at || "")}|${topSignature(finalRows)}`;
    if (state.phase === PHASES.FINAL && state.finalSignature === finalSignature) {
        return;
    }

    clearTicker();
    clearPhaseTimer();
    stopStatePolling();
    hideOptions();
    setTimerState(false);
    setQuestionChip(null);
    state.phase = PHASES.FINAL;
    state.revealPayload = null;
    state.resultSignature = "";
    state.finalSignature = finalSignature;
    state.leaderboardSignature = "";
    playFinalSound(finalSignature || "final");

    const ownFinalRow = finalRows.find((row) => Number(row.player_id) === Number(state.player.id));
    if (ownFinalRow) {
        setScore(ownFinalRow.score);
    }

    const podiumPlaces = finalRows.slice(0, PODIUM_SIZE);
    const others = finalRows.slice(PODIUM_SIZE);
    const suffix = esc(tr("pointsSuffix", "pts"));

    const podiumOrder = [
        podiumPlaces[1] ? { ...podiumPlaces[1], place: 2, slot: "left" } : null,
        podiumPlaces[0] ? { ...podiumPlaces[0], place: 1, slot: "center" } : null,
        podiumPlaces[2] ? { ...podiumPlaces[2], place: 3, slot: "right" } : null,
    ].filter(Boolean);

    const podiumMarkup = podiumOrder.map(player => `
        <div class="final-podium-block final-podium-block--place-${player.place} final-podium-block--slot-${player.slot}">
            <div class="final-podium-card">
                ${player.place === 1 ? '<div class="final-podium-crown">👑</div>' : `<div class="final-podium-medal">${player.place}</div>`}
                <div class="final-podium-avatar">${avatarMarkup(player, player.place === 1 ? 80 : 64, "player-avatar")}</div>
                <div class="final-podium-name">${esc(player.nickname || "Player")}</div>
                <div class="final-podium-score">${Number(player.score || 0)} ${suffix}</div>
            </div>
            <div class="final-podium-stand">
                <div class="final-podium-stand__place">${player.place}</div>
            </div>
        </div>
    `).join("");

    const othersMarkup = others.map((player, index) => `
        <div class="final-row">
            <div class="final-row__meta">
                <span class="final-row__rank">${index + 4}</span>
                ${avatarMarkup(player, 44, "player-avatar")}
                <span class="final-row__name">${esc(player.nickname || "Player")}</span>
            </div>
            <span class="final-row__score">${Number(player.score || 0)} ${suffix}</span>
        </div>
    `).join("");

    UI.phasePanelInner.innerHTML = `
        <div class="final-shell">
            <div class="phase-kicker"><i class="fa-solid fa-flag-checkered"></i><span>${esc(tr("leaderboardTitle", "Top players"))}</span></div>
            <div class="final-shell__trophy">🏆</div>
            <h1 class="phase-title">${esc(tr("finalTitle", "Final results"))}</h1>
            <p class="phase-subtitle">${esc(tr("finalBody", "The live exam is complete."))}</p>
            <div class="final-podium-stage">${podiumMarkup}</div>
            ${others.length ? `<div class="final-others-title">${esc(tr("scoreboardTitle", "Leaderboard"))}</div>` : ""}
            <div class="final-leaderboard">${othersMarkup}</div>
        </div>
    `;
    setStoredTop(finalRows);
    setRoundHint(tr("finalTitle", "Final results"));
}
