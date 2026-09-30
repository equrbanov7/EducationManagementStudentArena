// LX-FE-PLAYER (2026-09-29): raund görünüşləri — «Hazır ol», giriş (sual oxunur), cavab plitələri
// (tək/çox seçim, yazılı cavab), «cavab qəbul edildi» və «vaxt bitdi». Hər görünüş açarla qurulur
// (views.js) — eyni açarla təkrar çağırış yalnız dinamik hissələri (saniyə, sayğac) yeniləyir.
import { PHASES, TEXT_ANSWER_MAX_LENGTH } from './config.js?v=lx20260930';
import { playSound } from './audio.js?v=lx20260930';
import { state } from './state.js?v=lx20260930';
import { shapeKey, shapeLabel, shapeSvg, toneIndex } from './shapes.js?v=lx20260930';
import { announce, setQuestionChip, setTimer, startTimeBar, stopTimeBar } from './ui.js?v=lx20260930';
import {
    esc,
    fmt,
    isMulti,
    isTextQuestion,
    maxSelect,
    nowMs,
    showQuestionsOnDevices,
    toInt,
    tr,
    ts,
} from './utils.js?v=lx20260930';
import { currentViewEl, mountView } from './views.js?v=lx20260930';

export const CHECK_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const SEND_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 12l15-7-4.5 15-3-6.2z" fill="currentColor"/></svg>';
const HOURGLASS_SVG =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M6 3h12M6 21h12M7 3c0 4.5 5 6.5 5 9s-5 4.5-5 9M17 3c0 4.5-5 6.5-5 9s5 4.5 5 9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

export const questionKeyOf = (question) => `${question.id}:${question.started_at || ""}`;

function lengthClass(text) {
    const n = String(text || "").length;
    if (n <= 40) return "s";
    if (n <= 90) return "m";
    if (n <= 180) return "l";
    return "xl";
}

function waitingMessage(question) {
    const pool = [
        tr("waitMsg1", "Barmaqlarını çarpaz saxla 🤞"),
        tr("waitMsg2", "Görək nə olacaq…"),
        tr("waitMsg3", "Cəsarətli seçim!"),
        tr("waitMsg4", "Digərləri hələ düşünür…"),
        tr("waitMsg5", "Nəticəni birlikdə görəcəyik!"),
    ];
    return pool[Math.abs(toInt(question && question.index, 0)) % pool.length];
}

function roundKicker(question) {
    const parts = [
        `<span class="lxp-kicker__q">${esc(fmt(tr("questionCounter", "Sual {index} / {total}"), {
            index: question.index || "?",
            total: question.total || "?",
        }))}</span>`,
    ];
    if (isTextQuestion(question)) {
        parts.push(`<span class="lxp-badge">${esc(tr("typedBadge", "Yazılı cavab"))}</span>`);
    } else if (isMulti(question)) {
        parts.push(`<span class="lxp-badge">${esc(tr("multiBadge", "Bir neçə cavab"))}</span>`);
    }
    return `<p class="lxp-kicker">${parts.join("")}</p>`;
}

export function questionCardMarkup(question, { compact = false } = {}) {
    const show = showQuestionsOnDevices();
    const text = show ? String(question.text || "") : tr("questionHiddenBody", "Sual böyük ekrandadır — oradan oxu");
    const long = show && text.length > (compact ? 110 : 220);
    return (
        `<div class="lxp-qcard notranslate${compact ? " is-compact" : ""}${long ? " is-clamped" : ""}${show ? "" : " is-hidden-text"}" translate="no" data-len="${lengthClass(text)}">` +
        `<p class="lxp-qcard__text">${esc(text)}</p>` +
        (long
            ? `<button type="button" class="lxp-qcard__more" data-lxp-expand aria-expanded="false">${esc(tr("expandQuestion", "Tam oxu"))}</button>`
            : "") +
        `</div>`
    );
}

function tilesMarkup(question) {
    const options = Array.isArray(question.options) ? question.options : [];
    const show = showQuestionsOnDevices();
    const longest = options.reduce((max, option) => Math.max(max, String(option.text || "").length), 0);
    const layout = !show ? "shapes" : options.length <= 4 && longest <= 18 ? "grid" : "list";
    const multi = isMulti(question);
    const tiles = options
        .map((option, index) => {
            const key = shapeKey(option, index);
            const label = shapeLabel(key);
            const text = show ? String(option.text || "") : "";
            const optionId = Number(option.id);
            const selected = state.selectedIds.has(optionId);
            return (
                `<button type="button" class="lxp-tile option-btn${selected ? " is-selected" : ""}" data-option-id="${optionId}" ` +
                `data-tone="${toneIndex(option, index)}" data-len="${lengthClass(text)}" aria-pressed="${selected ? "true" : "false"}" ` +
                `aria-label="${esc(text ? `${label}: ${text}` : label)}">` +
                `<span class="lxp-tile__shape">${shapeSvg(key)}</span>` +
                (text ? `<span class="lxp-tile__text">${esc(text)}</span>` : "") +
                (multi ? `<span class="lxp-tile__check" aria-hidden="true">${CHECK_SVG}</span>` : "") +
                `</button>`
            );
        })
        .join("");
    return `<div class="lxp-tiles notranslate" translate="no" data-layout="${layout}" data-count="${options.length}" role="group" aria-label="${esc(tr("answersLabel", "Cavab variantları"))}">${tiles}</div>`;
}

function multiBarMarkup(question) {
    return (
        `<div class="lxp-multibar" data-lxp-multibar>` +
        `<span class="lxp-multibar__count" data-lxp-multicount aria-live="polite"></span>` +
        `<button type="button" class="lxp-btn lxp-btn--primary lxp-multibar__send" data-lxp-submit id="submitBtn" disabled>` +
        `${SEND_SVG}<span>${esc(tr("submitAnswer", "Cavabı göndər"))}</span></button>` +
        `</div>`
    );
}

function typedMarkup(question) {
    const max = toInt(question.text_max_length, TEXT_ANSWER_MAX_LENGTH) || TEXT_ANSWER_MAX_LENGTH;
    const draft = esc(state.typedDraft || "");
    return (
        `<form class="lxp-typed" data-lxp-typed novalidate autocomplete="off">` +
        `<label class="lxp-sr" for="lxpTypedInput">${esc(tr("typedLabel", "Cavabını yaz"))}</label>` +
        `<input id="lxpTypedInput" class="lxp-typed__input" data-lxp-typed-input type="text" inputmode="text" ` +
        `enterkeyhint="send" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" ` +
        `maxlength="${max}" data-max="${max}" value="${draft}" placeholder="${esc(tr("typedPlaceholder", "Cavabını bura yaz…"))}">` +
        `<div class="lxp-typed__row">` +
        `<span class="lxp-typed__count" data-lxp-typed-count aria-live="polite">${String(state.typedDraft || "").length}/${max}</span>` +
        `<button type="submit" class="lxp-btn lxp-btn--primary" data-lxp-typed-send${state.typedDraft ? "" : " disabled"}>` +
        `${SEND_SVG}<span>${esc(tr("typedSend", "Göndər"))}</span></button>` +
        `</div></form>`
    );
}

// --- «Hazır ol» (yalnız 1-ci sual) ---------------------------------------------------------
export function renderGetReady(question, msLeft) {
    const key = `ready:${questionKeyOf(question)}`;
    const seconds = Math.max(1, Math.ceil(msLeft / 1000));
    const { el, created } = mountView(
        key,
        `<div class="lxp-ready">` +
            roundKicker(question) +
            `<div class="lxp-ready__ring" aria-hidden="true"><span class="lxp-ready__num" data-lxp-count>${seconds}</span></div>` +
            `<h1 class="lxp-title">${esc(tr("getReadyTitle", "Hazır ol!"))}</h1>` +
            `<p class="lxp-sub">${esc(tr("getReadyBody", "İlk sual gəlir…"))}</p>` +
            `</div>`,
        { tone: "ready" }
    );
    state.phase = PHASES.GET_READY;
    if (created) {
        setQuestionChip(question);
        setTimer(false);
        stopTimeBar();
        announce(tr("getReadyTitle", "Hazır ol!"));
    }
    const counter = el.querySelector("[data-lxp-count]");
    if (counter && counter.textContent !== String(seconds)) {
        counter.textContent = String(seconds);
        counter.classList.remove("is-pulse");
        void counter.offsetWidth;
        counter.classList.add("is-pulse");
    }
    playSound("count", `${key}:${seconds}`);
}

// --- Giriş: sual oxunur, cavablar bir neçə saniyədən sonra açılır ----------------------------
export function renderIntro(question, msLeft, totalMs) {
    const key = `intro:${questionKeyOf(question)}:${showQuestionsOnDevices() ? 1 : 0}`;
    const show = showQuestionsOnDevices();
    const { el, created } = mountView(
        key,
        `<div class="lxp-intro">` +
            roundKicker(question) +
            questionCardMarkup(question) +
            `<div class="lxp-meter" aria-hidden="true"><span class="lxp-meter__fill" data-lxp-intro-fill></span></div>` +
            `<p class="lxp-intro__hint" data-lxp-intro-hint></p>` +
            `</div>`,
        { tone: "intro" }
    );
    state.phase = PHASES.INTRO;
    if (created) {
        setQuestionChip(question);
        setTimer(false);
        stopTimeBar();
        playSound("question", questionKeyOf(question));
        announce(
            show
                ? fmt(tr("announceQuestion", "Sual {index}: {text}"), { index: question.index || "", text: question.text || "" })
                : tr("introHintMainScreen", "Suala böyük ekranda bax")
        );
        const fill = el.querySelector("[data-lxp-intro-fill]");
        if (fill) {
            const total = Math.max(1, totalMs);
            fill.style.transition = "none";
            fill.style.transform = `scaleX(${Math.min(1, Math.max(0, 1 - msLeft / total)).toFixed(4)})`;
            void fill.offsetWidth;
            fill.style.transition = `transform ${Math.max(0, msLeft)}ms linear`;
            fill.style.transform = "scaleX(1)";
        }
    }
    const hint = el.querySelector("[data-lxp-intro-hint]");
    if (hint) {
        const seconds = Math.max(1, Math.ceil(msLeft / 1000));
        const text = fmt(tr("introUnlocking", "Cavablar {seconds} san sonra açılır"), { seconds });
        if (hint.textContent !== text) hint.textContent = text;
    }
}

// --- Sual: cavab plitələri ------------------------------------------------------------------
export function updateSelectionUI(root = currentViewEl()) {
    const question = state.currentQuestion;
    if (!root || !question) return;
    root.querySelectorAll("[data-option-id]").forEach((tile) => {
        const selected = state.selectedIds.has(Number(tile.dataset.optionId));
        tile.classList.toggle("is-selected", selected);
        tile.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    if (!isMulti(question)) return;
    const max = maxSelect(question);
    const count = state.selectedIds.size;
    const tiles = root.querySelector(".lxp-tiles");
    if (tiles) tiles.classList.toggle("is-full", count >= max);
    const counter = root.querySelector("[data-lxp-multicount]");
    if (counter) {
        counter.textContent = fmt(tr("multiCounter", "{count}/{max} seçildi"), { count, max });
        counter.classList.toggle("is-full", count >= max);
    }
    const submit = root.querySelector("[data-lxp-submit]");
    if (submit) submit.disabled = count === 0 || Boolean(state.pendingSubmit);
}

export function renderQuestion(question, msLeft) {
    const key = `question:${questionKeyOf(question)}:${showQuestionsOnDevices() ? 1 : 0}`;
    const typed = isTextQuestion(question);
    const multi = !typed && isMulti(question);
    const hint = typed
        ? ""
        : multi
          ? `<p class="lxp-hint">${esc(fmt(tr("multiHint", "Ən çox {max} cavab seç, sonra «Göndər»"), { max: maxSelect(question) }))}</p>`
          : "";
    const { el, created } = mountView(
        key,
        `<div class="lxp-round${typed ? " is-typed" : ""}">` +
            questionCardMarkup(question, { compact: true }) +
            hint +
            (typed ? typedMarkup(question) : tilesMarkup(question) + (multi ? multiBarMarkup(question) : "")) +
            `</div>`,
        { tone: "question", className: "lxp-view--top" }
    );
    state.phase = PHASES.QUESTION;
    const endsAt = ts(question.ends_at);
    const answerStartsAt = ts(question.answer_starts_at) || endsAt - msLeft;
    if (created) {
        setQuestionChip(question);
        playSound("go", questionKeyOf(question));
        startTimeBar(`q:${questionKeyOf(question)}`, msLeft, Math.max(msLeft, endsAt - answerStartsAt));
        announce(
            fmt(tr("announceAnswersOpen", "Cavab ver! {seconds} saniyə"), { seconds: Math.ceil(msLeft / 1000) })
        );
        if (typed) {
            const input = el.querySelector("[data-lxp-typed-input]");
            if (input) {
                window.setTimeout(() => {
                    try {
                        input.focus({ preventScroll: true });
                    } catch (error) {
                        input.focus();
                    }
                }, 60);
            }
        }
    }
    setTimer(true, msLeft);
    updateSelectionUI(el);
    const seconds = Math.ceil(msLeft / 1000);
    if (seconds >= 1 && seconds <= 5) {
        playSound("tick", `${questionKeyOf(question)}:${seconds}`);
    }
}

// --- Cavab verilib (göndərilir / qəbul edildi) -----------------------------------------------
function chosenChipsMarkup(question, answer) {
    if (isTextQuestion(question)) {
        const text = String(
            (answer && (answer.your_text || answer.text)) ||
                (state.pendingSubmit && state.pendingSubmit.payload.text) ||
                ""
        );
        if (!text) return "";
        // Oyunçu mətni YALNIZ textContent ilə yazılır (renderLocked doldurur) — LX-SEC tələbi.
        return `<p class="lxp-typed-echo" data-lxp-echo></p>`;
    }
    const ids = new Set(
        (answer && Array.isArray(answer.choice_ids) && answer.choice_ids.length
            ? answer.choice_ids
            : Array.from(state.selectedIds)
        ).map(Number)
    );
    const options = Array.isArray(question.options) ? question.options : [];
    const show = showQuestionsOnDevices();
    const chips = options
        .map((option, index) => ({ option, index }))
        .filter(({ option }) => ids.has(Number(option.id)))
        .map(({ option, index }) => {
            const key = shapeKey(option, index);
            const label = show && option.text ? option.text : shapeLabel(key);
            return `<span class="lxp-chip" data-tone="${toneIndex(option, index)}">${shapeSvg(key, "lxp-chip__shape")}<span>${esc(label)}</span></span>`;
        })
        .join("");
    if (!chips) return "";
    return `<div class="lxp-choice"><span class="lxp-choice__label">${esc(tr("youChose", "Sənin seçimin"))}</span><div class="lxp-choice__chips">${chips}</div></div>`;
}

export function renderLocked(question, msLeft) {
    const key = `locked:${questionKeyOf(question)}`;
    const sending = Boolean(state.pendingSubmit) && !state.currentAnswer;
    const { el, created } = mountView(
        key,
        `<div class="lxp-locked">` +
            `<div class="lxp-locked__badge" data-lxp-lockbadge aria-hidden="true"><span class="lxp-spinner"></span>${CHECK_SVG}</div>` +
            `<h1 class="lxp-title" data-lxp-locktitle></h1>` +
            `<div data-lxp-choice></div>` +
            `<p class="lxp-sub">${esc(waitingMessage(question))}</p>` +
            `<div class="lxp-dots" aria-hidden="true"><span></span><span></span><span></span></div>` +
            `</div>`,
        { tone: "locked" }
    );
    state.phase = PHASES.LOCKED;
    const badge = el.querySelector("[data-lxp-lockbadge]");
    const title = el.querySelector("[data-lxp-locktitle]");
    const status = sending ? "sending" : "saved";
    if (badge && badge.dataset.state !== status) {
        badge.dataset.state = status;
        title.textContent = sending
            ? tr("answerSending", "Göndərilir…")
            : tr("answerLocked", "Cavabın qəbul edildi!");
        if (!sending) announce(tr("answerLocked", "Cavabın qəbul edildi!"));
    }
    const choice = el.querySelector("[data-lxp-choice]");
    if (choice) {
        const markup = chosenChipsMarkup(question, state.currentAnswer);
        const typedText = isTextQuestion(question)
            ? String(
                  (state.currentAnswer && (state.currentAnswer.your_text || state.currentAnswer.text)) ||
                      (state.pendingSubmit && state.pendingSubmit.payload.text) ||
                      ""
              )
            : "";
        const signature = `${markup}|${typedText}`;
        if (choice.dataset.signature !== signature) {
            choice.dataset.signature = signature;
            choice.innerHTML = markup;
            const echo = choice.querySelector("[data-lxp-echo]");
            if (echo) echo.textContent = fmt(tr("yourAnswer", "Cavabın: «{text}»"), { text: typedText });
        }
    }
    if (created) setQuestionChip(question);
    if (msLeft > 0) {
        setTimer(true, msLeft);
    } else {
        setTimer(false);
        stopTimeBar();
    }
}

// --- Vaxt bitdi (cavab verilməyib) -----------------------------------------------------------
export function renderTimeUp(question) {
    const key = `timeup:${questionKeyOf(question)}`;
    const { created } = mountView(
        key,
        `<div class="lxp-timeup">` +
            `<div class="lxp-timeup__badge" aria-hidden="true">${HOURGLASS_SVG}</div>` +
            `<h1 class="lxp-title">${esc(tr("timeUpTitle", "Vaxt bitdi!"))}</h1>` +
            `<p class="lxp-sub">${esc(tr("timeUpBody", "Bu sualı cavablandırmadın. Növbəti sualda uğurlar!"))}</p>` +
            `<div class="lxp-dots" aria-hidden="true"><span></span><span></span><span></span></div>` +
            `</div>`,
        { tone: "timeup" }
    );
    state.phase = PHASES.TIMEUP;
    if (created) {
        setQuestionChip(question);
        setTimer(false);
        stopTimeBar();
        playSound("timeup", questionKeyOf(question));
        announce(tr("timeUpTitle", "Vaxt bitdi!"));
    }
}

export function phaseMsLeft(question) {
    return Math.max(0, ts(question.ends_at) - nowMs());
}
