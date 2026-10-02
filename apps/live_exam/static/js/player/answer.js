// LX-FE-PLAYER (2026-09-29): cavab seçimi və göndərişi.
//  * Tək seçim: ilk toxunuşda DƏRHAL kilidlənir (ikiqat toxunuş / iki variant yarışı yoxdur).
//  * Çox seçim: `max_select`-ə qədər seçim; limitdə «rədd» titrəyişi + səs + xəbərdarlıq.
//  * Yazılı cavab: `text` sahəsi (serverin eyni «answer» mesajı).
//  * WS ilə göndərilib ACK_TIMEOUT_MS ərzində `answer_saved` gəlməsə — HTTP ehtiyat yolu
//    (server təkrar cavabı «artıq cavab verilib» kimi qəbul edir → idempotent).
import { ACK_TIMEOUT_MS, BOOTSTRAP, PHASES, TEXT_ANSWER_MAX_LENGTH } from './config.js?v=lx20261002';
import { playSound, unlockAudio } from './audio.js?v=lx20261002';
import { fetchWithTimeout } from './api.js?v=lx20261002';
import { buzz, HAPTIC } from './haptics.js?v=lx20261002';
import { isSocketSuspect, sendJson, smoothedRttMs } from './sockets.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { clearAckTimer } from './timers.js?v=lx20261002';
import { showToast } from './ui.js?v=lx20261002';
import { fmt, isMulti, isTextQuestion, maxSelect, nowMs, toInt, tr, ts } from './utils.js?v=lx20261002';

const noop = () => {};
// Server mesajı tərcümə olunmayıbsa (msgid açarı) oyunçuya xam açar göstərilmir.
const UNTRANSLATED = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;
const serverText = (message, fallback) => {
    const text = String(message || "").trim();
    return !text || UNTRANSLATED.test(text) ? fallback : text;
};
let hooks = {
    onSelectionChange: noop,
    onSelectionDenied: noop,
    onSubmitStarted: noop,
    onAnswerSaved: noop,
    onSubmitFailed: noop,
    onReveal: noop,
};

export function setAnswerHooks(next) {
    hooks = Object.assign({}, hooks, next || {});
}

export function canAnswer() {
    return Boolean(
        state.currentQuestion && state.phase === PHASES.QUESTION && !state.pendingSubmit && !state.currentAnswer
    );
}

function withinWindow() {
    const endsAt = ts(state.currentQuestion && state.currentQuestion.ends_at);
    return !endsAt || nowMs() < endsAt + 1500;
}

export function handleOptionTap(optionId) {
    unlockAudio();
    if (!canAnswer() || !Number.isFinite(optionId)) return;
    const question = state.currentQuestion;
    if (isTextQuestion(question)) return;
    if (!isMulti(question)) {
        state.selectedIds = new Set([optionId]);
        playSound("lock");
        buzz(HAPTIC.lock);
        submitAnswer();
        return;
    }
    const max = maxSelect(question);
    if (state.selectedIds.has(optionId)) {
        state.selectedIds.delete(optionId);
        playSound("deselect");
        buzz(HAPTIC.select);
    } else if (state.selectedIds.size >= max) {
        playSound("denied");
        buzz(HAPTIC.denied);
        showToast(fmt(tr("multiMaxReached", "Ən çox {max} variant seçə bilərsən"), { max }), "warn", 2200);
        hooks.onSelectionDenied(optionId);
        return;
    } else {
        state.selectedIds.add(optionId);
        playSound("select");
        buzz(HAPTIC.select);
    }
    hooks.onSelectionChange();
}

function buildPayload(question, text) {
    // LXNET: vaxt plitələrin BU telefonda açıldığı andan (gec çatan sualda pəncərə açılışından sonra).
    const startedAt =
        Math.max(ts(question.answer_starts_at) || 0, Number(state.answerOpenedAt) || 0) ||
        ts(question.started_at) ||
        nowMs();
    const payload = {
        type: "answer",
        question_id: question.id,
        answer_ms: Math.max(0, Math.round(nowMs() - startedAt)),
    };
    if (isTextQuestion(question)) {
        const max = toInt(question.text_max_length, TEXT_ANSWER_MAX_LENGTH) || TEXT_ANSWER_MAX_LENGTH;
        const value = String(text == null ? "" : text)
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, max);
        if (!value) return null;
        payload.text = value;
        return payload;
    }
    if (!state.selectedIds.size) return null;
    if (isMulti(question)) {
        payload.option_ids = Array.from(state.selectedIds);
    } else {
        payload.option_id = Array.from(state.selectedIds)[0];
    }
    return payload;
}

export function submitAnswer({ text } = {}) {
    unlockAudio();
    if (!canAnswer()) return false;
    const question = state.currentQuestion;
    const payload = buildPayload(question, text);
    if (!payload) {
        if (isTextQuestion(question)) {
            showToast(tr("typedEmpty", "Əvvəlcə cavabını yaz"), "warn", 2000);
            buzz(HAPTIC.denied);
        }
        return false;
    }
    state.pendingSubmit = { questionId: Number(question.id), payload, sentAt: Date.now(), attempts: 0 };
    if (isMulti(question) || isTextQuestion(question)) {
        playSound("lock");
        buzz(HAPTIC.lock);
    }
    hooks.onSubmitStarted();
    dispatch(state.pendingSubmit);
    return true;
}

// LXNET: təsdiq gözləmə müddəti ölçülmüş RTT-yə uyğunlaşır (sağlam slow 3G-də ~2 s, əvvəl sabit 3.5 s).
export function ackTimeoutMs() {
    const rtt = Number(smoothedRttMs()) || 0;
    return rtt ? Math.min(ACK_TIMEOUT_MS, Math.max(1500, Math.round(rtt * 3 + 800))) : ACK_TIMEOUT_MS;
}

function dispatch(pending) {
    clearAckTimer();
    pending.attempts += 1;
    // Socket ilişibsə (ping cavabsız) cavab gözləmədən HTTP ilə gedir; server təkrarı idempotent qəbul edir.
    if (pending.attempts === 1 && !isSocketSuspect() && sendJson(pending.payload)) {
        pending.via = "ws";
        state.ackTimer = window.setTimeout(() => {
            state.ackTimer = null;
            if (state.pendingSubmit === pending) sendHttp(pending);
        }, ackTimeoutMs());
        return;
    }
    sendHttp(pending);
}

async function sendHttp(pending) {
    pending.via = "http";
    const { type, ...body } = pending.payload;
    try {
        // LXNET: ilişən sorğu 6 s-dən sonra ləğv olunur → təkrar cəhd təzə bağlantı ilə (server
        // təkrar cavabı «artıq cavab verilib» kimi idempotent qəbul edir).
        const response = await fetchWithTimeout(
            BOOTSTRAP.answerUrl,
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "application/json",
                    "X-CSRFToken": BOOTSTRAP.csrf || "",
                },
                body: JSON.stringify(Object.assign({ type }, body)),
            },
            6000
        );
        let data = {};
        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }
        if (state.pendingSubmit !== pending) return; // artıq WS ilə təsdiqlənib
        if (response.ok && data.ok) {
            handleAnswerSaved(Object.assign({ question_id: pending.questionId }, data.answer || {}));
            if (data.reveal) hooks.onReveal(data.reveal);
            return;
        }
        failSubmit(pending, serverText(data.message, tr("errorSend", "Cavab göndərilmədi. Yenidən cəhd et.")));
    } catch (error) {
        if (state.pendingSubmit !== pending) return;
        if (pending.attempts < 3 && withinWindow()) {
            window.setTimeout(() => {
                if (state.pendingSubmit !== pending) return;
                pending.attempts += 1;
                sendHttp(pending);
            }, 1200);
            return;
        }
        failSubmit(pending, tr("errorSendOffline", "Cavab göndərilmədi — internet bağlantısını yoxla."));
    }
}

function failSubmit(pending, message) {
    if (state.pendingSubmit !== pending) return;
    clearAckTimer();
    state.pendingSubmit = null;
    if (!isMulti(state.currentQuestion) && !isTextQuestion(state.currentQuestion)) {
        state.selectedIds = new Set();
    }
    showToast(message, "error");
    playSound("denied");
    buzz(HAPTIC.denied);
    hooks.onSubmitFailed();
}

// WS `answer_saved` və ya HTTP cavabı — yalnız cari sual üçün.
export function handleAnswerSaved(data) {
    if (!data) return;
    if (data.player_id != null && Number(data.player_id) !== Number(state.player.id)) return;
    const question = state.currentQuestion;
    const pending = state.pendingSubmit;
    const questionId = Number(data.question_id || (pending && pending.questionId) || (question && question.id) || 0);
    if (!question || Number(question.id) !== questionId) return;
    clearAckTimer();
    state.pendingSubmit = null;
    const sent = pending ? pending.payload : {};
    const choiceIds =
        Array.isArray(data.choice_ids) && data.choice_ids.length
            ? data.choice_ids.map(Number)
            : Array.isArray(sent.option_ids)
              ? sent.option_ids.map(Number)
              : sent.option_id != null
                ? [Number(sent.option_id)]
                : (state.currentAnswer && state.currentAnswer.choice_ids) || [];
    state.currentAnswer = Object.assign({}, state.currentAnswer || {}, data, {
        saved: true,
        choice_ids: choiceIds,
        your_text: data.your_text || data.text || sent.text || (state.currentAnswer && state.currentAnswer.your_text) || "",
    });
    hooks.onAnswerSaved();
}

// WS `error` mesajı: gözləyən cavab varsa — rədd edildi; yoxdursa sadəcə bildiriş.
export function handleAnswerError(message) {
    const pending = state.pendingSubmit;
    if (pending) {
        failSubmit(pending, serverText(message, tr("errorSend", "Cavab göndərilmədi. Yenidən cəhd et.")));
        return;
    }
    const text = serverText(message, "");
    if (text) showToast(text, "error");
}
