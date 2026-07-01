import { UI } from './dom.js';
import { PHASES } from './constants.js';
import { state } from './state.js';
import { playCountdownSound, playIntroSound } from './audio.js';
import { answerOptionMarkup } from './options.js';
import {
    buildQuestionPlan,
    updateAnsweredCounter,
    updateQuestionIntroProgress,
    updateTimerBadge,
} from './lobby.js';
import {
    answerWord,
    controlsEnabled,
    esc,
    fmt,
    nowMs,
    progressBadgeMarkup,
    progressLabel,
    questionKey,
    toMs,
    tr,
    usesPresentationStageLayout,
} from './utils.js';
import { clearPhaseLoop, schedulePhaseLoop, setPresentationMarkup, setSessionState } from './presentation.js';

function renderIntroStage() {
    playIntroSound(`${state.questionKey}:quiz`);
    setPresentationMarkup(
        PHASES.INTRO,
        `${state.questionKey}:${PHASES.INTRO}`,
        `
            <section class="present-view present-view--center">
                <h1 class="stage-hero stage-hero--wordmark">${esc(tr("introTitle", "Quiz"))}</h1>
            </section>
        `
    );
}

function renderCountdownStage(question, number) {
    playCountdownSound(`${state.questionKey}:${number}`);
    setPresentationMarkup(
        PHASES.COUNTDOWN,
        `${state.questionKey}:${PHASES.COUNTDOWN}:${number}`,
        `
            <section class="present-view present-view--center">
                <div class="countdown-number" aria-label="${esc(
                    fmt(tr("countdownNumberLabel", "Round starts in {value}"), { value: number })
                )}">${number}</div>
            </section>
        `
    );
}

function renderQuestionOnlyStage(question) {
    const presentationLayout = usesPresentationStageLayout();
    setPresentationMarkup(
        PHASES.QUESTION,
        `${state.questionKey}:${PHASES.QUESTION}`,
        `
            <section class="present-view present-view--quiz">
                <div class="quiz-shell quiz-shell--question">
                    ${
                        presentationLayout
                            ? `
                                <div class="question-card question-card--solo">
                                    <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                                </div>
                            `
                            : `
                                <div class="quiz-shell__hud quiz-shell__hud--single">
                                    <div class="quiz-shell__hud-left">
                                        <div class="quiz-progress">${esc(progressLabel(question))}</div>
                                    </div>
                                </div>
                                <div class="question-card question-card--solo">
                                    <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                                </div>
                            `
                    }
                    <div class="question-only-bar" aria-hidden="true">
                        <span id="questionOnlyBarFill"></span>
                    </div>
                </div>
            </section>
        `
    );
}

function renderAnswersStage(question) {
    const presentationLayout = usesPresentationStageLayout();
    setPresentationMarkup(
        PHASES.ANSWERS,
        `${state.questionKey}:${PHASES.ANSWERS}`,
        `
            <section class="present-view present-view--quiz">
                <div class="quiz-shell">
                    <div class="${presentationLayout ? "quiz-stage-frame" : "quiz-shell__hud"}">
                        ${
                            presentationLayout
                                ? `
                                    <div class="quiz-stage-side quiz-stage-side--left">
                                        <div id="answerTimerBadge" class="quiz-orb quiz-orb--timer">
                                            <strong id="answerTimerValue">0</strong>
                                            <span>${esc(tr("secondsLabel", "seconds"))}</span>
                                        </div>
                                    </div>
                                    <div class="quiz-stage-main">
                                        <div class="question-card">
                                            <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                                        </div>
                                    </div>
                                    <div class="quiz-stage-side quiz-stage-side--right">
                                        <div class="quiz-stage-stack">
                                            ${progressBadgeMarkup(question)}
                                            <div class="quiz-orb quiz-orb--counter">
                                                <strong id="answerCounterNumber">0</strong>
                                                <span id="answerCounterLabel">${esc(answerWord(0))}</span>
                                            </div>
                                        </div>
                                    </div>
                                `
                                : `
                                    <div class="quiz-shell__hud-left">
                                        <div class="quiz-progress">${esc(progressLabel(question))}</div>
                                    </div>
                                    <div class="quiz-shell__hud-right">
                                        <div id="answerTimerBadge" class="quiz-orb quiz-orb--timer">
                                            <strong id="answerTimerValue">0</strong>
                                            <span>${esc(tr("secondsLabel", "seconds"))}</span>
                                        </div>
                                        <div class="quiz-orb quiz-orb--counter">
                                            <strong id="answerCounterNumber">0</strong>
                                            <span id="answerCounterLabel">${esc(answerWord(0))}</span>
                                        </div>
                                    </div>
                                `
                        }
                    </div>
                    ${
                        presentationLayout
                            ? ""
                            : `
                                <div class="question-card">
                                    <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                                </div>
                            `
                    }
                </div>
                <div class="host-options-grid host-options-grid--kahoot">
                    ${(question?.options || []).map(answerOptionMarkup).join("")}
                </div>
            </section>
        `
    );

    updateAnsweredCounter();
}

function syncQuestionPresentation() {
    if (state.sessionState !== "question" || !state.currentQuestion || !state.questionPlan) {
        clearPhaseLoop();
        return;
    }

    const now = nowMs();
    const plan = state.questionPlan;

    if (plan.hasCountdown && now < plan.quizEnd) {
        renderIntroStage();
    } else if (plan.hasCountdown && now < plan.countdownEnd && plan.countdownEnd > plan.countdownStart) {
        const remainingSeconds = Math.max(1, Math.ceil((plan.countdownEnd - now) / 1000));
        const nextValue = Math.min(3, remainingSeconds);
        if (state.countdownValue !== nextValue) {
            state.countdownValue = nextValue;
            renderCountdownStage(state.currentQuestion, nextValue);
        }
    } else if (now < plan.answerStart) {
        renderQuestionOnlyStage(state.currentQuestion);
        updateAnsweredCounter();
        updateTimerBadge(now);
        updateQuestionIntroProgress(now);
    } else {
        renderAnswersStage(state.currentQuestion);
        updateAnsweredCounter();
        updateTimerBadge(now);
    }
}

function scheduleAutoReveal(question) {
    clearTimeout(state.autoRevealTimeout);
    if (!controlsEnabled() || !UI.autoMode.checked || !question?.ends_at) return;
    const ms = Math.max(0, toMs(question.ends_at) - nowMs());
    state.autoRevealTimeout = setTimeout(() => {
        if (state.sessionState === "question") {
            UI.revealBtn.click();
        }
    }, ms + 180);
}

export function applyQuestionState(question, answeredCount, totalPlayers) {
    if (!question) return;

    state.totalPlayers = Number(totalPlayers || state.totalPlayers || 0);
    state.answeredCount = Number(answeredCount || 0);
    state.currentQuestion = question;
    state.currentReveal = null;
    state.questionPlan = buildQuestionPlan(question);

    const nextKey = questionKey(question);
    const shouldRestart = state.questionKey !== nextKey || state.sessionState !== "question";
    state.questionKey = nextKey;
    state.countdownValue = null;

    setSessionState("question");
    updateAnsweredCounter();
    scheduleAutoReveal(question);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncQuestionPresentation);
    } else {
        syncQuestionPresentation();
    }
}
