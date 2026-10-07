import { UI } from './dom.js?v=lx20261008';
import { PHASES } from './constants.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { playRevealSound } from './audio.js?v=lx20261008';
import { icon } from './icons.js?v=lx20261008';
import { answerTileMarkup, distributionBarsMarkup, tilesGridClass } from './options.js?v=lx20261008';
import { nextQuestion } from './api.js?v=lx20261008';
import { renderScoreboardStage } from './scoreboard.js?v=lx20261008';
import { isFinalReveal, renderFinalSuspenseStage } from './finale_suspense.js?v=lx20261008';
import {
    avatarImageMarkup,
    controlsEnabled,
    countUp,
    esc,
    fitAll,
    fmt,
    formatNumber,
    formatSeconds,
    lengthClass,
    nowMs,
    progressLabel,
    revealKey,
    toMs,
    tr,
} from './utils.js?v=lx20261008';
import { clearPhaseLoop, isCurrentPhase, schedulePhaseLoop, setPresentationMarkup, setSessionState } from './presentation.js?v=lx20261008';

export function destroyRevealChart() {
    /* Chart.js artıq işlədilmir (xüsusi CSS sütunları) — köhnə çağırışlar üçün no-op. */
}

export function distributionLookup(payload) {
    const counts = new Map();
    (payload?.distribution?.counts || []).forEach((row) => {
        counts.set(Number(row.option_id || 0), Number(row.count || 0));
    });
    return { counts, totalAnswers: Number(payload?.distribution?.total_answers || 0) };
}

const isText = (question, payload) => String(payload?.answer_input || question?.answer_input || "choice") === "text";

/** Düzgün cavab sayı — yalnız tam məlumat olanda (təxmin YOX). */
function correctCount(question, payload, distribution) {
    const results = Array.isArray(payload?.results) ? payload.results : null;
    if (results && results.length === distribution.totalAnswers) {
        return results.filter((row) => row.is_correct).length;
    }
    if (isText(question, payload) && Array.isArray(payload?.typed_summary)) {
        return payload.typed_summary.filter((row) => row.correct).reduce((sum, row) => sum + Number(row.count || 0), 0);
    }
    if (!question?.multi) {
        const correctIds = (payload?.correct_option_ids || []).map(Number);
        return correctIds.reduce((sum, id) => sum + Number(distribution.counts.get(id) || 0), 0);
    }
    return null;
}

function fastestCorrect(payload, distribution) {
    if (payload?.fastest_correct && payload.fastest_correct.nickname != null) return payload.fastest_correct;
    const results = Array.isArray(payload?.results) ? payload.results : [];
    if (!results.length || results.length !== distribution.totalAnswers) return null;
    return results.filter((row) => row.is_correct).sort((a, b) => Number(a.answer_ms) - Number(b.answer_ms))[0] || null;
}

function footMarkup(question, payload, distribution) {
    const parts = [];
    const total = distribution.totalAnswers;
    if (total <= 0) {
        parts.push(`<span class="hx-stat hx-stat--muted">${esc(tr("noAnswers", "Bu raundda cavab verilmədi"))}</span>`);
    } else {
        const correct = correctCount(question, payload, distribution);
        if (correct != null) {
            parts.push(
                `<span class="hx-stat hx-stat--correct">${icon("check")}<span>${esc(fmt(tr("correctSummary", "{correct} / {total} düzgün cavab"), { correct: formatNumber(correct), total: formatNumber(total) }))}</span></span>`
            );
        }
        const fastest = fastestCorrect(payload, distribution);
        if (fastest) {
            parts.push(
                `<span class="hx-stat hx-stat--fastest">${icon("bolt")}<span>${esc(tr("fastest", "Ən sürətli"))}:</span>${avatarImageMarkup(fastest, 36, "hx-stat__avatar")}<strong>${esc(fastest.nickname || "")}</strong><span>${esc(formatSeconds(fastest.answer_ms))} ${esc(tr("secondsShort", "san"))}</span></span>`
            );
        }
    }
    const scoring = String(payload?.multi_scoring || "");
    if (question?.multi && (scoring === "partial" || scoring === "strict")) {
        const text = scoring === "partial"
            ? tr("partialCredit", "Qismən bal: hər düzgün seçim bal gətirir")
            : tr("strictCredit", "Bal yalnız bütün düzgün variantlar seçiləndə verilir");
        parts.push(`<span class="hx-stat hx-stat--note">${icon("sparkle")}<span>${esc(text)}</span></span>`);
    }
    return parts.length ? `<footer class="hx-reveal__foot">${parts.join("")}</footer>` : "";
}

function headMarkup(question, payload) {
    const multi = question?.multi
        ? `<span class="hx-badge hx-badge--multi">${icon("check")}${esc(tr("multiBadge", "Bir neçə düzgün cavab"))}</span>`
        : "";
    const text = isText(question, payload)
        ? `<span class="hx-badge hx-badge--text">${icon("keyboard")}${esc(tr("textBadge", "Yazılı cavab"))}</span>`
        : "";
    return `<header class="hx-qhead"><span class="hx-pill">${esc(progressLabel(question))}</span>${multi}${text}</header>`;
}

function cardMarkup(question) {
    const text = String(question?.text || "");
    return `<div class="hx-qcard hx-qcard--reveal notranslate" translate="no" data-len="${lengthClass(text)}"><h2 class="hx-qcard__text" data-fit>${esc(text)}</h2></div>`;
}

function typedMarkup(payload) {
    const accepted = (Array.isArray(payload?.accepted_answers) ? payload.accepted_answers : []).map(String).filter(Boolean);
    const summary = (Array.isArray(payload?.typed_summary) ? payload.typed_summary : [])
        .slice()
        .sort((a, b) => Number(b.count || 0) - Number(a.count || 0))
        .slice(0, 8);
    const max = Math.max(1, ...summary.map((row) => Number(row.count || 0)));
    const main = accepted[0] || "";
    return `
        <div class="hx-accepted">
            <span class="hx-accepted__label">${icon("check")}${esc(accepted.length > 1 ? tr("correctAnswers", "Düzgün cavablar") : tr("correctAnswer", "Düzgün cavab"))}</span>
            <strong class="hx-accepted__main" data-fit>${esc(main || "—")}</strong>
            ${
                accepted.length > 1
                    ? `<div class="hx-accepted__alts"><span class="hx-accepted__alts-label">${esc(tr("acceptedAlso", "Qəbul edilən variantlar"))}:</span>${accepted
                          .slice(1, 10)
                          .map((value) => `<span class="hx-chip">${esc(value)}</span>`)
                          .join("")}</div>`
                    : ""
            }
        </div>
        ${
            summary.length
                ? `<div class="hx-typedsum">
                    <h3 class="hx-typedsum__title">${esc(tr("typedTop", "Ən çox yazılan cavablar"))}</h3>
                    <ol class="hx-typedsum__list">
                        ${summary
                            .map(
                                (row) => `
                            <li class="hx-typedsum__row ${row.correct ? "is-correct" : "is-wrong"}" data-ratio="${(Number(row.count || 0) / max).toFixed(4)}">
                                <span class="hx-typedsum__bar" aria-hidden="true"></span>
                                <span class="hx-typedsum__text">${esc(row.text || "")}</span>
                                <strong class="hx-typedsum__count">${formatNumber(row.count || 0)}</strong>
                                <span class="hx-typedsum__verdict" role="img" aria-label="${esc(row.correct ? tr("correctTag", "Düzgün") : tr("wrongTag", "Səhv"))}">${icon(row.correct ? "check" : "cross")}</span>
                            </li>`
                            )
                            .join("")}
                    </ol>
                </div>`
                : ""
        }
    `;
}

function animateBars(root) {
    root.querySelectorAll("[data-ratio]").forEach((el) => {
        el.style.setProperty("--k", el.dataset.ratio || "0");
    });
    root.querySelectorAll(".hx-bar").forEach((bar, index) => {
        const target = Number(bar.dataset.count || 0);
        const el = bar.querySelector("[data-bar-count]");
        window.setTimeout(() => countUp(el, 0, target, 700), 250 + index * 90);
    });
}

function renderRevealStage(question, payload) {
    if (isCurrentPhase(PHASES.REVEAL, `${state.revealKey}:${PHASES.REVEAL}`)) return;
    const distribution = distributionLookup(payload);
    const correctIds = (payload?.correct_option_ids || []).map(Number);
    const options = question?.options || [];
    const text = isText(question, payload);
    setPresentationMarkup(
        PHASES.REVEAL,
        `${state.revealKey}:${PHASES.REVEAL}`,
        `
            <section class="hx-scene hx-reveal ${text ? "hx-reveal--text" : ""}" aria-live="polite">
                ${headMarkup(question, payload)}
                ${cardMarkup(question)}
                ${
                    text
                        ? typedMarkup(payload)
                        : `
                            <div class="hx-bars hx-bars--n${Math.min(6, options.length)}">${distributionBarsMarkup(options, distribution, correctIds)}</div>
                            <div class="hx-tiles notranslate ${tilesGridClass(options.length)} is-reveal" translate="no">
                                ${options.map((option, index) => answerTileMarkup(option, index, correctIds.includes(Number(option?.id || 0)) ? "correct" : "wrong")).join("")}
                            </div>
                        `
                }
                ${footMarkup(question, payload, distribution)}
            </section>
        `,
        (root) => {
            fitAll(root, "[data-fit]", { min: 18 });
            fitAll(root, ".hx-tile__text", { min: 14 });
            animateBars(root);
        }
    );
}

function updateStreaks(payload) {
    const key = revealKey(payload);
    if (state.streakRevealKey === key) return;
    state.streakRevealKey = key;
    const results = Array.isArray(payload?.results) ? payload.results : [];
    const complete = results.length === Number(payload?.distribution?.total_answers || 0) && results.length < 50;
    const seen = new Set();
    results.forEach((row) => {
        const id = Number(row.player_id || 0);
        seen.add(id);
        state.streaks.set(id, row.is_correct ? (state.streaks.get(id) || 0) + 1 : 0);
    });
    if (complete) {
        state.streaks.forEach((_, id) => {
            if (!seen.has(id)) state.streaks.set(id, 0);
        });
    }
}

function syncRevealPresentation() {
    if (state.sessionState !== "reveal" || !state.currentReveal) {
        clearPhaseLoop();
        return;
    }
    const leaderboardStartsAt = toMs(state.currentReveal.leaderboard_starts_at);
    if (leaderboardStartsAt && nowMs() >= leaderboardStartsAt) {
        // Sahib 2026-09-30: son sualdan sonra liderlər lövhəsi YOX — «Nəticələr…» → final səhnəsi.
        if (isFinalReveal(state.currentReveal, state.currentQuestion)) {
            renderFinalSuspenseStage(state.currentReveal);
        } else {
            renderScoreboardStage(state.currentReveal, state.currentQuestion);
        }
        clearPhaseLoop();
    } else {
        renderRevealStage(state.currentQuestion, state.currentReveal);
    }
}

function scheduleAutoNext(payload) {
    clearTimeout(state.autoNextTimeout);
    state.autoNextTimeout = 0;
    if (!controlsEnabled() || !UI.autoMode?.checked || !payload?.next_question_at) return;
    const key = revealKey(payload);
    const ms = Math.max(0, toMs(payload.next_question_at) - nowMs());
    state.autoNextTimeout = setTimeout(() => {
        if (state.sessionState === "reveal" && state.revealKey === key) nextQuestion();
    }, ms + 150);
}

export function applyRevealState(payload, question) {
    if (!payload) return;
    const nextKey = revealKey(payload);
    const alreadyInReveal = state.sessionState === "reveal" && state.revealKey === nextKey;
    if (alreadyInReveal && (state.phase === PHASES.SCOREBOARD || state.phase === PHASES.SUSPENSE)) return;

    if (question) state.currentQuestion = question;
    // Snapshot-dan gələn reveal WS paketindən kasıb ola bilər — mövcud sahələri itirmə.
    state.currentReveal = alreadyInReveal ? Object.assign({}, state.currentReveal || {}, payload) : payload;
    const shouldRestart = state.revealKey !== nextKey || state.sessionState !== "reveal";
    state.revealKey = nextKey;
    playRevealSound(`reveal:${nextKey}`);
    updateStreaks(state.currentReveal);

    clearTimeout(state.autoRevealTimeout);
    clearTimeout(state.allAnsweredTimeout);
    state.allAnsweredTimeout = 0;
    setSessionState("reveal");
    scheduleAutoNext(payload);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncRevealPresentation);
    } else {
        syncRevealPresentation();
    }
}
