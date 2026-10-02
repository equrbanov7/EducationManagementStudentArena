import { state } from './state.js?v=lx20261002';
import { postJson } from './api.js?v=lx20261002';
import { icon } from './icons.js?v=lx20261002';
import { esc, tr } from './utils.js?v=lx20261002';

/* Tənzimləmə çekməcəsi → «Cavab rejimi» bölməsi:
 *   • çox seçimli suallarda bal: "partial" (qismən) | "strict" (hamısı düzgün);
 *   • yazılı cavablarda kiçik səhvlərə dözümlülük (typed_typo_tolerance);
 *   • uyğun suallar üçün «Yazılı cavab» açarı + qəbul edilən variant çipləri.
 * Hər yadda saxlamada TAM `typed_questions` xəritəsi göndərilir (server tam əvəz edir);
 * söndürülmüş sual xəritədən çıxarılır. Oyun başlayandan sonra redaktə bağlanır. */

const MAX_ITEMS = 10;
const MAX_LEN = 60;
let root = null;
let questions = [];
let draft = null;
let saveTimer = 0;
let saving = false;

function readQuestions() {
    try {
        const el = document.getElementById("hostQuestions");
        const data = el ? JSON.parse(el.textContent || "null") : null;
        return Array.isArray(data) ? data : [];
    } catch (error) {
        return [];
    }
}

const clean = (list) => (Array.isArray(list) ? list.map(String).filter(Boolean).slice(0, MAX_ITEMS) : []);

/** Server vəziyyəti: `typed_questions` (host-a məxsus açar) varsa o əsasdır; yoxdursa
 * host_questions kataloqundakı `typed` / `accepted` (boş = standart variantlar). */
function serverMap() {
    const raw = state.sessionSettings?.typed_questions;
    const map = {};
    if (raw && typeof raw === "object") {
        Object.entries(raw).forEach(([qid, value]) => {
            const list = clean(value?.accepted);
            if (list.length) map[String(qid)] = list;
        });
        return map;
    }
    questions.forEach((question) => {
        if (!question.typed || !question.typed_eligible) return;
        const list = clean(question.accepted?.length ? question.accepted : question.typed_default_accepted);
        if (list.length) map[String(question.id)] = list;
    });
    return map;
}

const editable = () => state.sessionState === "lobby";
const scoring = () => (String(state.sessionSettings?.multi_scoring || "partial") === "strict" ? "strict" : "partial");
const tolerance = () => state.sessionSettings?.typed_typo_tolerance !== false;

function chipsMarkup(qid, list) {
    const locked = !editable();
    const single = list.length <= 1;
    return `
        ${list
            .map(
                (value, index) => `
            <span class="hx-chip hx-chip--edit">
                <span class="hx-chip__text">${esc(value)}</span>
                <button type="button" class="hx-chip__remove" data-chip-remove="${index}" data-qid="${esc(qid)}" aria-label="${esc(tr("chipRemove", "Sil"))}: ${esc(value)}" ${locked || single ? "disabled" : ""}>${icon("close")}</button>
            </span>`
            )
            .join("")}
        ${
            list.length < MAX_ITEMS && !locked
                ? `<input type="text" class="hx-chips__input" data-chip-input data-qid="${esc(qid)}" maxlength="${MAX_LEN}" placeholder="${esc(tr("typedAdd", "Variant əlavə et və Enter bas"))}" aria-label="${esc(tr("typedAccepted", "Qəbul edilən cavablar"))}">`
                : ""
        }
    `;
}

function questionItem(question) {
    const qid = String(question.id);
    const list = draft[qid];
    const on = Array.isArray(list) && list.length > 0;
    const eligible = Boolean(question.typed_eligible);
    return `
        <li class="hx-typedq__item ${on ? "is-on" : ""} ${eligible ? "" : "is-na"}" data-qid="${esc(qid)}">
            <div class="hx-typedq__head">
                <span class="hx-typedq__num">${Number(question.index || 0)}</span>
                <span class="hx-typedq__text" title="${esc(question.text || "")}">${esc(question.text || "")}</span>
                ${
                    eligible
                        ? `<label class="hx-typedq__toggle">
                            <input type="checkbox" class="host-switch__input" data-typed-toggle="${esc(qid)}" ${on ? "checked" : ""} ${editable() ? "" : "disabled"}>
                            <span class="host-switch" aria-hidden="true"><span></span></span>
                            <span class="hx-sr">${esc(tr("typedToggle", "Yazılı cavab"))}</span>
                        </label>`
                        : `<span class="hx-typedq__na">${esc(tr("typedNotEligible", "Yalnız variantlı"))}</span>`
                }
            </div>
            ${on ? `<div class="hx-chips" data-chips="${esc(qid)}">${chipsMarkup(qid, list)}</div>` : ""}
        </li>
    `;
}

function render() {
    if (!root) return;
    const locked = !editable();
    const sc = scoring();
    root.innerHTML = `
        <div class="host-settings-group__title">${esc(tr("answerModeTitle", "Cavab rejimi"))}</div>
        <div class="host-settings-item host-settings-item--stack">
            <div class="host-settings-item__copy">
                <strong>${esc(tr("multiScoringLabel", "Çox seçimli suallarda bal"))}</strong>
                <span>${esc(sc === "strict" ? tr("multiStrictHelp", "Bal yalnız bütün düzgün variantlar seçiləndə verilir.") : tr("multiPartialHelp", "Hər düzgün seçilən variant üçün mütənasib bal verilir."))}</span>
            </div>
            <div class="hx-seg" role="radiogroup" aria-label="${esc(tr("multiScoringLabel", "Çox seçimli suallarda bal"))}">
                ${[["partial", tr("multiPartial", "Qismən bal")], ["strict", tr("multiStrict", "Hamısı düzgün olmalıdır")]]
                    .map(([value, label]) => `<button type="button" class="hx-seg__btn" role="radio" aria-checked="${sc === value}" data-multi-scoring="${value}" ${locked ? "disabled" : ""}>${esc(label)}</button>`)
                    .join("")}
            </div>
        </div>
        <label class="host-settings-item">
            <div class="host-settings-item__copy">
                <strong>${esc(tr("typoLabel", "Kiçik yazı səhvlərini qəbul et"))}</strong>
                <span>${esc(tr("typoHelp", "Yazılı cavablarda 1–2 hərflik səhv, böyük/kiçik hərf və artıq boşluqlar nəzərə alınmır."))}</span>
            </div>
            <input type="checkbox" class="host-switch__input" data-typo-toggle ${tolerance() ? "checked" : ""} ${locked ? "disabled" : ""}>
            <span class="host-switch" aria-hidden="true"><span></span></span>
        </label>
        ${
            questions.length
                ? `<div class="host-settings-item host-settings-item--stack">
                    <div class="host-settings-item__copy">
                        <strong>${esc(tr("typedListTitle", "Yazılı cavab"))}</strong>
                        <span>${esc(tr("typedListHelp", "Uyğun suallarda variantlar əvəzinə tələbə cavabı özü yazır."))} ${esc(tr("typedLimit", "Ən çox 10 variant, hər biri 1–60 simvol."))}</span>
                    </div>
                    <ol class="hx-typedq">${questions.map(questionItem).join("")}</ol>
                </div>`
                : ""
        }
        ${locked ? `<p class="hx-typedq__locked">${icon("lock")}${esc(tr("typedLocked", "Oyun başlayandan sonra dəyişmək olmur"))}</p>` : ""}
        <p class="hx-typedq__status" data-typed-status role="status" aria-live="polite"></p>
    `;
    root.hidden = false;
}

function flash(text, tone) {
    const el = root?.querySelector("[data-typed-status]");
    if (!el) return;
    el.textContent = text;
    el.dataset.tone = tone || "ok";
}

function scheduleSave() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
        saveTimer = 0;
        saveTyped();
    }, 450);
}

async function saveSettings(updates) {
    saving = true;
    const result = await postJson(CONFIG.urls.settings, updates);
    saving = false;
    if (result?.ok) {
        questions.forEach((question) => {
            const list = draft[String(question.id)];
            question.typed = Boolean(list && list.length);
            question.accepted = list ? list.slice() : [];
        });
        flash(tr("savedLabel", "Yadda saxlanıldı"), "ok");
    } else {
        draft = serverMap();
        render();
        flash(result?.message || tr("saveError", "Yadda saxlanılmadı"), "error");
    }
    return result;
}

function saveTyped() {
    const map = {};
    Object.entries(draft).forEach(([qid, list]) => {
        if (Array.isArray(list) && list.length) map[qid] = { accepted: list.slice(0, MAX_ITEMS) };
    });
    return saveSettings({ typed_questions: map });
}

function addChip(input) {
    const qid = input.dataset.qid;
    const value = String(input.value || "").replace(/\s+/g, " ").trim();
    const list = draft[qid] || [];
    if (!value) return;
    if (value.length > MAX_LEN) {
        flash(tr("typedLimit", "Ən çox 10 variant, hər biri 1–60 simvol."), "error");
        return;
    }
    if (list.some((item) => item.toLocaleLowerCase() === value.toLocaleLowerCase())) {
        input.value = "";
        return;
    }
    if (list.length >= MAX_ITEMS) return;
    draft[qid] = [...list, value];
    render();
    root.querySelector(`[data-chip-input][data-qid="${CSS.escape(qid)}"]`)?.focus();
    scheduleSave();
}

function bind() {
    root.addEventListener("click", (event) => {
        const seg = event.target.closest("[data-multi-scoring]");
        if (seg && editable()) {
            saveSettings({ multi_scoring: seg.dataset.multiScoring });
            return;
        }
        const remove = event.target.closest("[data-chip-remove]");
        if (remove && editable()) {
            const qid = remove.dataset.qid;
            const list = (draft[qid] || []).slice();
            if (list.length <= 1) return;
            list.splice(Number(remove.dataset.chipRemove), 1);
            draft[qid] = list;
            render();
            scheduleSave();
        }
    });
    root.addEventListener("change", (event) => {
        const toggle = event.target.closest("[data-typed-toggle]");
        if (toggle && editable()) {
            const qid = toggle.dataset.typedToggle;
            if (toggle.checked) {
                const question = questions.find((item) => String(item.id) === qid);
                const defaults = (question?.typed_default_accepted || []).map(String).filter(Boolean).slice(0, MAX_ITEMS);
                draft[qid] = defaults.length ? defaults : [];
                render();
                if (!draft[qid].length) {
                    root.querySelector(`[data-chip-input][data-qid="${CSS.escape(qid)}"]`)?.focus();
                    flash(tr("typedEmpty", "Ən azı bir qəbul edilən cavab yazın"), "error");
                    return;
                }
            } else {
                delete draft[qid];
                render();
            }
            scheduleSave();
            return;
        }
        if (event.target.closest("[data-typo-toggle]") && editable()) {
            saveSettings({ typed_typo_tolerance: Boolean(event.target.checked) });
        }
    });
    root.addEventListener("keydown", (event) => {
        const input = event.target.closest("[data-chip-input]");
        if (!input) return;
        if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            addChip(input);
        } else if (event.key === "Backspace" && !input.value) {
            const qid = input.dataset.qid;
            const list = (draft[qid] || []).slice();
            if (list.length > 1) {
                list.pop();
                draft[qid] = list;
                render();
                root.querySelector(`[data-chip-input][data-qid="${CSS.escape(qid)}"]`)?.focus();
                scheduleSave();
            }
        }
    });
    root.addEventListener("focusout", (event) => {
        const input = event.target.closest("[data-chip-input]");
        if (input && input.value.trim()) addChip(input);
    });
    window.addEventListener("live-host-state", () => {
        if (saving || saveTimer || root.contains(document.activeElement)) return;
        const next = serverMap();
        const nextSig = JSON.stringify([next, scoring(), tolerance(), editable()]);
        if (root.dataset.sig !== nextSig) {
            root.dataset.sig = nextSig;
            draft = next;
            render();
        }
    });
}

export function mountTypedDrawer() {
    root = document.getElementById("hostAnswerModeSection");
    if (!root || !CONFIG?.urls?.settings || CONFIG.controlsEnabled === false) return;
    questions = readQuestions();
    draft = serverMap();
    root.dataset.sig = JSON.stringify([draft, scoring(), tolerance(), editable()]);
    render();
    bind();
}
