import { UI } from './dom.js';
import { PHASES } from './constants.js';
import { state } from './state.js';
import { playRevealSound, playScoreboardSound } from './audio.js';
import { distributionLookup } from './lobby.js';
import { distributionBarMarkup, optionMarkerLabel } from './options.js';
import {
    avatarImageMarkup,
    controlsEnabled,
    esc,
    fmt,
    nowMs,
    progressLabel,
    revealKey,
    toMs,
    tr,
} from './utils.js';
import { clearPhaseLoop, schedulePhaseLoop, setPresentationMarkup, setSessionState } from './presentation.js';

let activeRevealChart = null;

export function destroyRevealChart() {
    if (activeRevealChart) {
        try { activeRevealChart.destroy(); } catch (_) {}
        activeRevealChart = null;
    }
}

function renderRevealStage(question, payload) {
    const distribution = distributionLookup(payload);
    const correctOptionIds = (payload?.correct_option_ids || []).map(value => Number(value));
    const answeredSummary = fmt(tr("playersAnswered", "{answered} answered"), { answered: distribution.totalAnswers });
    const noAnswersNote =
        distribution.totalAnswers > 0
            ? `<div class="distribution-note">${esc(answeredSummary)}</div>`
            : `<div class="distribution-note">${esc(tr("distributionNoAnswers", "No answers were submitted this round."))}</div>`;

    const sig = `${state.revealKey}:${PHASES.REVEAL}`;
    const willRender = !(state.phaseSignature === sig && state.phase === PHASES.REVEAL);

    setPresentationMarkup(
        PHASES.REVEAL,
        sig,
        `
            <section class="present-view present-view--quiz present-view--reveal-chart">
                <div class="quiz-shell quiz-shell--reveal">
                    <div class="quiz-shell__hud quiz-shell__hud--single">
                        <div class="quiz-shell__hud-left">
                            <div class="quiz-progress">${esc(progressLabel(question))}</div>
                        </div>
                    </div>
                    <div class="question-card question-card--reveal">
                        <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                    </div>
                </div>
                ${noAnswersNote}
                <div class="reveal-chart-area">
                    <canvas id="revealDistChart"></canvas>
                </div>
                <div class="distribution-chart">
                    ${(question?.options || [])
                        .map((option, index) => distributionBarMarkup(option, index, distribution, correctOptionIds))
                        .join("")}
                </div>
            </section>
        `
    );

    // Initialize Chart.js bar chart after DOM update
    if (willRender && typeof Chart !== "undefined") {
        requestAnimationFrame(() => {
            const canvas = document.getElementById("revealDistChart");
            if (!canvas) return;

            if (activeRevealChart) {
                try { activeRevealChart.destroy(); } catch (_) {}
                activeRevealChart = null;
            }

            const options = question?.options || [];
            const labels = options.map((opt, i) => optionMarkerLabel(opt, i));
            const counts = options.map(opt => Number(distribution.counts.get(Number(opt?.id || 0)) || 0));
            const barColors = ["#f0205f", "#2563eb", "#ff8b16", "#11b981"];
            const borderColors = ["#ff5b79", "#4f9cff", "#f8c325", "#4fd39a"];
            const bgColors = options.map((opt, i) => {
                const isCorrect = correctOptionIds.includes(Number(opt?.id || 0));
                const base = barColors[i % 4];
                return isCorrect ? base : base + "99";
            });
            const borders = options.map((opt, i) => {
                const isCorrect = correctOptionIds.includes(Number(opt?.id || 0));
                return isCorrect ? "#4ade80" : borderColors[i % 4];
            });

            activeRevealChart = new Chart(canvas, {
                type: "bar",
                data: {
                    labels,
                    datasets: [{
                        data: counts,
                        backgroundColor: bgColors,
                        borderColor: borders,
                        borderWidth: 2,
                        borderRadius: 12,
                        barPercentage: 0.7,
                        categoryPercentage: 0.75,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: {
                        duration: 800,
                        easing: "easeOutQuart",
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "rgba(15,23,42,0.92)",
                            titleFont: { size: 14, weight: "bold" },
                            bodyFont: { size: 13 },
                            cornerRadius: 10,
                            padding: 12,
                            callbacks: {
                                label(ctx) {
                                    const total = distribution.totalAnswers || 0;
                                    const pct = total > 0 ? Math.round((ctx.raw / total) * 100) : 0;
                                    const opt = options[ctx.dataIndex];
                                    const text = opt?.text || "";
                                    return [`${text}`, `${ctx.raw} (${pct}%)`];
                                },
                            },
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1,
                                color: "rgba(255,255,255,0.7)",
                                font: { size: 13, weight: "bold" },
                            },
                            grid: {
                                color: "rgba(255,255,255,0.08)",
                            },
                        },
                        x: {
                            ticks: {
                                color: "rgba(255,255,255,0.85)",
                                font: { size: 15, weight: "900" },
                            },
                            grid: { display: false },
                        },
                    },
                },
            });
        });
    }
}

function movementBadge(player, index, previousTop) {
    const previousIndex = (previousTop || []).findIndex(row => Number(row.player_id) === Number(player.player_id));
    if (previousIndex === -1) {
        return `<span class="scoreboard-row__movement scoreboard-row__movement--new">★ ${esc(
            tr("scoreboardNewEntry", "New in top 5")
        )}</span>`;
    }

    const moved = previousIndex - index;
    if (moved > 0) {
        return `<span class="scoreboard-row__movement">↑ ${moved}</span>`;
    }

    return "";
}

function renderScoreboardStage(payload) {
    const previousTop = payload?.previous_top || [];
    const rows = (payload?.top || []).slice(0, 5);
    const signature = `${state.revealKey}:${PHASES.SCOREBOARD}`;
    if (state.phase === PHASES.SCOREBOARD && state.phaseSignature === signature) {
        return;
    }
    playScoreboardSound(state.revealKey || `${payload?.question_id || "0"}:scoreboard`);

    setPresentationMarkup(
        PHASES.SCOREBOARD,
        signature,
        `
            <section class="present-view present-view--scoreboard">
                <div class="scoreboard-stage__header">
                    <div class="stage-pill">${esc(tr("scoreboardTitle", "Scoreboard"))}</div>
                    <h2 class="stage-title">${esc(tr("scoreboardSubtitle", "Top 5 players"))}</h2>
                </div>
                <div class="scoreboard-list">
                    ${rows
                        .map(
                            (player, index) => `
                                <article class="scoreboard-row ${index === 0 ? "is-first" : ""}">
                                    <div class="scoreboard-row__left">
                                        <div class="scoreboard-row__rank">${index + 1}</div>
                                        <div class="scoreboard-row__avatar">${avatarImageMarkup(
                                            player,
                                            58,
                                            "host-avatar-image--scoreboard"
                                        )}</div>
                                        <div class="scoreboard-row__meta">
                                            <div class="scoreboard-row__name">${esc(player.nickname || "")}</div>
                                            ${movementBadge(player, index, previousTop)}
                                        </div>
                                    </div>
                                    <div class="scoreboard-row__score">${Number(player.score || 0)}</div>
                                </article>
                            `
                        )
                        .join("")}
                </div>
            </section>
        `
    );
}

function syncRevealPresentation() {
    if (state.sessionState !== "reveal" || !state.currentReveal) {
        clearPhaseLoop();
        return;
    }

    const leaderboardStartsAt = toMs(state.currentReveal.leaderboard_starts_at);
    const now = nowMs();

    if (leaderboardStartsAt && now >= leaderboardStartsAt) {
        renderScoreboardStage(state.currentReveal);
        clearPhaseLoop();
    } else {
        renderRevealStage(state.currentQuestion, state.currentReveal);
    }
}

function scheduleAutoNext(payload) {
    clearTimeout(state.autoNextTimeout);
    if (!controlsEnabled() || !UI.autoMode.checked || !payload?.next_question_at) return;
    const ms = Math.max(0, toMs(payload.next_question_at) - nowMs());
    state.autoNextTimeout = setTimeout(() => {
        if (state.sessionState === "reveal") {
            UI.nextBtn.click();
        }
    }, ms + 120);
}

export function applyRevealState(payload, question) {
    if (!payload) return;

    const nextKey = revealKey(payload);
    const alreadyInReveal = state.sessionState === "reveal" && state.revealKey === nextKey;

    // Skip redundant reveal processing for the same reveal key
    if (alreadyInReveal && state.phase === PHASES.SCOREBOARD) {
        return;
    }

    if (question) {
        state.currentQuestion = question;
    }
    state.currentReveal = payload;

    const shouldRestart = state.revealKey !== nextKey || state.sessionState !== "reveal";
    if (state.revealKey !== nextKey) {
        playRevealSound(nextKey);
    }
    state.revealKey = nextKey;

    clearTimeout(state.autoRevealTimeout);
    setSessionState("reveal");
    scheduleAutoNext(payload);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncRevealPresentation);
    } else {
        syncRevealPresentation();
    }
}
