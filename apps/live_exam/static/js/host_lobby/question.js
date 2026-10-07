import { $, UI } from './dom.js?v=lx20261008';
import { PHASES } from './constants.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { playAllAnswered, playCountdownSound, playIntroSound, playTick, playTimeUp, playWhoosh } from './audio.js?v=lx20261008';
import { icon } from './icons.js?v=lx20261008';
import { answerTileMarkup, tilesGridClass } from './options.js?v=lx20261008';
import { revealQuestion } from './api.js?v=lx20261008';
import { playWipe } from './transitions.js?v=lx20261008';
import { secondsLabel } from './time_setting.js?v=lx20261008';
import {
    controlsEnabled,
    esc,
    fitAll,
    fmt,
    formatNumber,
    lengthClass,
    nowMs,
    progressLabel,
    questionKey,
    toMs,
    tr,
} from './utils.js?v=lx20261008';
import { clearPhaseLoop, isCurrentPhase, schedulePhaseLoop, setPresentationMarkup, setSessionState } from './presentation.js?v=lx20261008';

const isTextQuestion = (question) => String(question?.answer_input || "choice") === "text";

export function buildQuestionPlan(question) {
    const startedAt = toMs(question?.started_at);
    const getReadyMs = Math.max(0, Number(question?.get_ready_duration_ms || 0));
    const introMs = Math.max(0, Number(question?.intro_duration_ms || 0));
    const readyEndsAt = toMs(question?.ready_ends_at) || startedAt + getReadyMs;
    const answerStart = toMs(question?.answer_starts_at) || readyEndsAt + introMs;
    const endsAt = toMs(question?.ends_at);
    const hasCountdown = getReadyMs > 0 && readyEndsAt > startedAt;
    // «Hazır olun» ekranı, sonra son 3 saniyə geri sayım.
    const countdownStart = hasCountdown ? Math.max(startedAt, readyEndsAt - 3000) : readyEndsAt;
    return {
        startedAt,
        quizEnd: hasCountdown ? countdownStart : startedAt,
        countdownStart,
        countdownEnd: readyEndsAt,
        readyEndsAt,
        answerStart,
        endsAt,
        hasCountdown,
        getReadyMs,
        introMs,
        answerMs: Math.max(1, endsAt - answerStart),
    };
}

function badgesMarkup(question) {
    const badges = [];
    if (isTextQuestion(question)) {
        badges.push(`<span class="hx-badge hx-badge--text">${icon("keyboard")}${esc(tr("textBadge", "Yazılı cavab"))}</span>`);
    } else if (question?.multi) {
        const max = Number(question?.max_select || 0);
        const label = max > 1 ? fmt(tr("multiPick", "{count} cavab seçin"), { count: max }) : tr("multiBadge", "Bir neçə düzgün cavab");
        badges.push(`<span class="hx-badge hx-badge--multi">${icon("check")}${esc(label)}</span>`);
    }
    return badges.join("");
}

/** 2026-10-08 (L2): cari sualın vaxtı proyektorda HƏMİŞƏ görünür (server nəşrdə dondurur). */
function timePillMarkup(question) {
    const seconds = Number(question?.time_limit || 0);
    if (!seconds) return "";
    return `<span class="hx-pill hx-pill--time" title="${esc(tr("timeLabel", "Hər sual üçün vaxt"))}">${icon("timer")}<span>${esc(secondsLabel(seconds))}</span></span>`;
}

/** 2026-10-08 (L3): gec qoşulma açıqdırsa PIN oyun gedərkən də görünür (gecikən tələbə qoşula bilsin). */
function lateJoinPinMarkup() {
    if (state.sessionSettings?.late_join_enabled === false || state.isLocked) return "";
    const hint = tr("lateJoinPinHint", "Gecikənlər bu PIN ilə qoşula bilər");
    return `<span class="hx-pill hx-pill--pin" title="${esc(hint)}" aria-label="${esc(hint)}: ${esc(CONFIG.pin)}">${icon("users")}<span>PIN</span><strong>${esc(CONFIG.pin)}</strong></span>`;
}

function headMarkup(question) {
    return `
        <header class="hx-qhead">
            <span class="hx-pill">${esc(progressLabel(question))}</span>
            ${timePillMarkup(question)}
            ${badgesMarkup(question)}
            ${lateJoinPinMarkup()}
        </header>
    `;
}

function cardMarkup(question, compact) {
    const text = String(question?.text || "");
    return `
        <div class="hx-qcard notranslate ${compact ? "hx-qcard--compact" : ""}" translate="no" data-len="${lengthClass(text)}">
            <h2 class="hx-qcard__text" data-fit>${esc(text)}</h2>
        </div>
    `;
}

const fitQuestion = (root) => fitAll(root, "[data-fit]", { min: 18 });

function renderIntroStage(question) {
    if (isCurrentPhase(PHASES.INTRO, `${state.questionKey}:${PHASES.INTRO}`)) return;
    playIntroSound(`${state.questionKey}:intro`);
    const total = Number(question?.total || 0);
    setPresentationMarkup(
        PHASES.INTRO,
        `${state.questionKey}:${PHASES.INTRO}`,
        `
            <section class="hx-scene hx-getready" aria-live="polite">
                <div class="hx-getready__burst" aria-hidden="true"></div>
                <span class="hx-kicker">${esc(CONFIG.examTitle || tr("introTitle", "Viktorina"))}</span>
                <h1 class="hx-getready__title">${esc(tr("getReady", "Hazır olun!"))}</h1>
                <p class="hx-getready__sub">${esc(fmt(tr("getReadySub", "{count} sual · telefonunuzu hazır saxlayın"), { count: total }))}</p>
                <div class="hx-getready__loader" aria-hidden="true"><span></span><span></span><span></span></div>
            </section>
        `
    );
}

function renderCountdownStage(number) {
    playCountdownSound(`${state.questionKey}:${number}`);
    setPresentationMarkup(
        PHASES.COUNTDOWN,
        `${state.questionKey}:${PHASES.COUNTDOWN}:${number}`,
        `
            <section class="hx-scene hx-countdown" aria-live="assertive">
                <div class="hx-countdown__ring" aria-hidden="true"></div>
                <div class="hx-countdown__num" data-n="${number}" aria-label="${esc(fmt(tr("countdownNumberLabel", "Raund {value} saniyəyə başlayır"), { value: number }))}">${number}</div>
            </section>
        `
    );
}

function renderQuestionOnlyStage(question) {
    if (isCurrentPhase(PHASES.QUESTION, `${state.questionKey}:${PHASES.QUESTION}`)) return;
    const fresh = setPresentationMarkup(
        PHASES.QUESTION,
        `${state.questionKey}:${PHASES.QUESTION}`,
        `
            <section class="hx-scene hx-question hx-question--reading" aria-live="polite">
                ${headMarkup(question)}
                ${cardMarkup(question, false)}
                <div class="hx-readbar" aria-hidden="true">
                    <span class="hx-readbar__track"><span class="hx-readbar__fill" data-read-fill></span></span>
                    <span class="hx-readbar__label">${esc(tr("readTime", "Sualı oxuyun…"))}</span>
                </div>
            </section>
        `,
        fitQuestion
    );
    if (fresh && Number(question?.index || 0) > 1) {
        playWipe(`wipe:${state.questionKey}`, progressLabel(question));
        playWhoosh(`whoosh:${state.questionKey}`);
    }
}

function hudMarkup() {
    return `
        <div class="hx-timer" data-timer role="timer" aria-live="off">
            <svg class="hx-timer__ring" viewBox="0 0 120 120" aria-hidden="true" focusable="false">
                <circle class="hx-timer__track" cx="60" cy="60" r="52"></circle>
                <circle class="hx-timer__arc" data-timer-arc cx="60" cy="60" r="52" pathLength="100"></circle>
            </svg>
            <strong class="hx-timer__value" data-timer-value>0</strong>
            <span class="hx-timer__unit">${esc(tr("secondsShort", "san"))}</span>
        </div>
    `;
}

function answeredMarkup() {
    return `
        <div class="hx-answered" data-answered aria-live="off">
            <span class="hx-answered__icon">${icon("users")}</span>
            <strong class="hx-answered__count" data-answered-count>0</strong>
            <span class="hx-answered__total">/ <b data-answered-total>0</b></span>
            <span class="hx-answered__label">${esc(tr("answersLabel", "cavab"))}</span>
        </div>
    `;
}

function typedIllustration() {
    return `
        <div class="hx-typed" aria-hidden="true">
            <span class="hx-typed__device">${icon("keyboard")}</span>
            <div class="hx-typed__field">
                <span class="hx-typed__placeholder">${esc(tr("textPlaceholder", "Cavabınızı yazın…"))}</span>
                <span class="hx-typed__caret"></span>
            </div>
            <p class="hx-typed__prompt">${esc(tr("textPrompt", "Cavabı telefonunuzda yazın"))}</p>
        </div>
    `;
}

function renderAnswersStage(question) {
    if (isCurrentPhase(PHASES.ANSWERS, `${state.questionKey}:${PHASES.ANSWERS}`)) return;
    const text = isTextQuestion(question);
    const options = question?.options || [];
    setPresentationMarkup(
        PHASES.ANSWERS,
        `${state.questionKey}:${PHASES.ANSWERS}`,
        `
            <section class="hx-scene hx-question hx-question--answers ${text ? "is-text" : ""}">
                ${headMarkup(question)}
                <div class="hx-qrow">
                    ${hudMarkup()}
                    ${cardMarkup(question, true)}
                    ${answeredMarkup()}
                </div>
                ${
                    text
                        ? typedIllustration()
                        : `<div class="hx-tiles notranslate ${tilesGridClass(options.length)}" translate="no">${options.map((option, index) => answerTileMarkup(option, index)).join("")}</div>`
                }
                <div class="hx-banner" data-banner role="status" hidden></div>
            </section>
        `,
        (root) => {
            fitQuestion(root);
            fitAll(root, ".hx-tile__text", { min: 16 });
        }
    );
    state.lastTimerSecond = -1;
    updateAnsweredCounter();
}

function showBanner(kind, text) {
    const banner = UI.presentationContent?.querySelector("[data-banner]");
    if (!banner || banner.dataset.kind === kind) return;
    banner.dataset.kind = kind;
    banner.innerHTML = `${icon(kind === "timeup" ? "timer" : "check")}<span>${esc(text)}</span>`;
    banner.hidden = false;
}

function updateTimer(now) {
    const plan = state.questionPlan;
    const arc = $("presentationContent")?.querySelector("[data-timer-arc]");
    const value = $("presentationContent")?.querySelector("[data-timer-value]");
    if (!plan || !arc || !value) return;
    const left = Math.max(0, plan.endsAt - now);
    const ratio = Math.max(0, Math.min(1, left / plan.answerMs));
    arc.style.setProperty("--p", ratio.toFixed(4));
    const seconds = Math.ceil(left / 1000);
    if (seconds !== state.lastTimerSecond) {
        state.lastTimerSecond = seconds;
        value.textContent = String(seconds);
        const timer = arc.closest("[data-timer]");
        timer?.classList.toggle("is-warning", seconds <= 10 && seconds > 5);
        timer?.classList.toggle("is-danger", seconds <= 5);
        if (seconds >= 1 && seconds <= 5) playTick(`${state.questionKey}:tick:${seconds}`, seconds <= 3);
    }
    if (left <= 0 && state.sessionState === "question") {
        playTimeUp(`${state.questionKey}:timeup`);
        showBanner("timeup", tr("timeUp", "Vaxt bitdi!"));
    }
}

function updateReadBar(now) {
    const fill = UI.presentationContent?.querySelector("[data-read-fill]");
    const plan = state.questionPlan;
    if (!fill || !plan) return;
    const start = Number(plan.readyEndsAt || 0);
    const duration = Math.max(1, Number(plan.answerStart || 0) - start);
    const progress = Math.max(0, Math.min(1, (now - start) / duration));
    fill.style.setProperty("--p", progress.toFixed(4));
}

export function updateAnsweredCounter() {
    const answered = Number(state.answeredCount || 0);
    const total = Number(state.totalPlayers || 0);
    if (UI.answeredText) UI.answeredText.textContent = `${answered} / ${total}`;
    const root = UI.presentationContent;
    const countEl = root?.querySelector("[data-answered-count]");
    if (countEl && countEl.textContent !== formatNumber(answered)) {
        countEl.textContent = formatNumber(answered);
        const box = countEl.closest("[data-answered]");
        box?.classList.remove("is-bump");
        void box?.offsetWidth;
        box?.classList.add("is-bump");
    }
    const totalEl = root?.querySelector("[data-answered-total]");
    if (totalEl) totalEl.textContent = formatNumber(total);
    checkAllAnswered();
}

// LXNET 2026-10-02: müəllim panelində «sualı alan telefonlar» (zəif şəbəkəli oyunçular görünür).
export function updateReceivedCounter() {
    const el = UI.receivedText;
    if (!el) return;
    const total = Number(state.totalPlayers || 0);
    const received = Math.min(Number(state.receivedCount || 0), total || Number(state.receivedCount || 0));
    const active = state.sessionState === "question" && total > 0;
    el.hidden = !active;
    if (!active) return;
    el.textContent = fmt(tr("receivedCounter", "{received}/{total} aldı"), { received, total });
    el.classList.toggle("is-lagging", received < total);
}

function checkAllAnswered() {
    if (state.sessionState !== "question" || state.phase !== PHASES.ANSWERS) return;
    const total = Number(state.totalPlayers || 0);
    if (total <= 0 || Number(state.answeredCount || 0) < total) return;
    playAllAnswered(`${state.questionKey}:all`);
    showBanner("all", tr("allAnswered", "Hamı cavab verdi!"));
    // Server hamı cavab verəndə reveal-i ÖZÜ açır; bu yalnız ehtiyat yoludur
    // (əvvəl dərhal POST edilirdi → 409 Conflict konsol xətası).
    if (controlsEnabled() && !state.allAnsweredTimeout) {
        const key = state.questionKey;
        state.allAnsweredTimeout = window.setTimeout(() => {
            state.allAnsweredTimeout = 0;
            if (state.sessionState === "question" && state.questionKey === key) revealQuestion();
        }, 1800);
    }
}

function syncQuestionPresentation() {
    if (state.sessionState !== "question" || !state.currentQuestion || !state.questionPlan) {
        clearPhaseLoop();
        return;
    }
    const now = nowMs();
    const plan = state.questionPlan;
    if (plan.hasCountdown && now < plan.countdownStart) {
        renderIntroStage(state.currentQuestion);
    } else if (plan.hasCountdown && now < plan.countdownEnd) {
        const value = Math.max(1, Math.min(3, Math.ceil((plan.countdownEnd - now) / 1000)));
        if (state.countdownValue !== value) {
            state.countdownValue = value;
            renderCountdownStage(value);
        }
    } else if (now < plan.answerStart) {
        renderQuestionOnlyStage(state.currentQuestion);
        updateReadBar(now);
    } else {
        renderAnswersStage(state.currentQuestion);
        updateTimer(now);
    }
}

function scheduleAutoReveal(question) {
    clearTimeout(state.autoRevealTimeout);
    state.autoRevealTimeout = 0;
    if (!controlsEnabled() || !UI.autoMode?.checked || !question?.ends_at) return;
    const key = questionKey(question);
    const ms = Math.max(0, toMs(question.ends_at) - nowMs());
    // Server `ends_at`-dan sonra `answer_grace_ms` (şəbəkə gecikməsi) ərzində cavab qəbul edir —
    // açıqlama bu pəncərə bitənə qədər gözləyir ki, son saniyənin qanuni cavabları itməsin.
    const graceMs = Math.max(0, Number(question.answer_grace_ms) || 0);
    state.autoRevealTimeout = setTimeout(() => {
        if (state.sessionState === "question" && state.questionKey === key) revealQuestion();
    }, ms + graceMs + 250);
}

export function applyQuestionState(question, answeredCount, totalPlayers) {
    if (!question) return;
    state.totalPlayers = Number(totalPlayers ?? state.totalPlayers ?? 0);
    state.answeredCount = Number(answeredCount || 0);
    state.currentQuestion = question;
    state.currentReveal = null;
    state.questionPlan = buildQuestionPlan(question);

    const nextKey = questionKey(question);
    const shouldRestart = state.questionKey !== nextKey || state.sessionState !== "question";
    if (state.questionKey !== nextKey) {
        clearTimeout(state.allAnsweredTimeout);
        state.allAnsweredTimeout = 0;
    }
    state.questionKey = nextKey;
    state.countdownValue = null;
    if (Number(state.receivedQuestionId) !== Number(question.id)) {
        state.receivedQuestionId = Number(question.id);
        state.receivedCount = 0;
    }

    setSessionState("question");
    scheduleAutoReveal(question);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncQuestionPresentation);
    } else {
        syncQuestionPresentation();
        if (!state.frameId) schedulePhaseLoop(syncQuestionPresentation);
    }
    updateAnsweredCounter();
    updateReceivedCounter();
}
