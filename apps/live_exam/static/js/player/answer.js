import { BOOTSTRAP } from './config.js';
import { applyRevealState, handleAnswerSaved } from './flow.js';
import { fetchInitialState } from './api.js';
import { renderQuestion } from './render.js';
import { getPlaySocket } from './sockets.js';
import { state } from './state.js';
import { disableOptions, setRoundHint, updateCounter } from './ui.js';
import { isMulti, maxSelect, nowMs, tr, ts } from './utils.js';
import { unlockAudio } from './audio.js';

export function handleOptionClick(button, optionId) {
    unlockAudio();

    if (state.phase !== "question" || state.submitting || state.currentAnswer) return;

    if (!isMulti(state.currentQuestion)) {
        state.selectedIds = new Set([optionId]);
        document.querySelectorAll(".option-btn").forEach((item) => item.classList.remove("selected"));
        button.classList.add("selected");
        window.setTimeout(() => {
            if (state.phase === "question" && !state.currentAnswer && !state.submitting) {
                submitAnswer();
            }
        }, 120);
        return;
    }

    const maximum = maxSelect(state.currentQuestion);
    if (state.selectedIds.has(optionId)) {
        state.selectedIds.delete(optionId);
        button.classList.remove("selected");
    } else {
        if (state.selectedIds.size >= maximum) return;
        state.selectedIds.add(optionId);
        button.classList.add("selected");
    }
    updateCounter();
}

export function submitAnswer() {
    unlockAudio();

    if (!state.currentQuestion || !state.selectedIds.size || state.submitting || state.currentAnswer) return;

    state.submitting = true;
    disableOptions();
    setRoundHint(tr("answerSending", "Locking in your answer..."));

    const answerStart = ts(state.currentQuestion.answer_starts_at) || ts(state.currentQuestion.started_at) || nowMs();
    const answerMs = Math.max(0, nowMs() - answerStart);

    const payload = {
        type: "answer",
        question_id: state.currentQuestion.id,
        answer_ms: answerMs,
    };

    if (isMulti(state.currentQuestion)) {
        payload.option_ids = Array.from(state.selectedIds);
    } else {
        payload.option_id = Array.from(state.selectedIds)[0];
    }

    const playWS = getPlaySocket();
    try {
        if (playWS && playWS.readyState === WebSocket.OPEN) {
            playWS.send(JSON.stringify(payload));
            return;
        }
        submitAnswerFallback(payload);
    } catch (error) {
        submitAnswerFallback(payload);
    }
}

async function submitAnswerFallback(payload) {
    try {
        const response = await fetch(BOOTSTRAP.answerUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-CSRFToken": BOOTSTRAP.csrf,
            },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.message || "Unable to send your answer.");
        }
        handleAnswerSaved(data.answer || {});
        if (data.reveal) {
            applyRevealState(data.reveal);
            return;
        }
        fetchInitialState();
    } catch (error) {
        state.submitting = false;
        renderQuestion(state.currentQuestion);
        setRoundHint(error && error.message ? error.message : "Unable to send your answer.");
    }
}
