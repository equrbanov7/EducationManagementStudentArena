/* time_setting.js — «Hər sual üçün vaxt: [30 s ▾]» (2026-10-08, L2).
 *
 * Müəllim vaxtı tapa bilmirdi və boş imtahan vaxtında oyun səssizcə 15 s götürürdü. İndi vaxt
 * lobbi səhnəsində (proyektorda görünür) və idarə panelində seçilir; oyun gedərkən də dəyişir —
 * yeni dəyər NÖVBƏTİ sualdan tətbiq olunur (server cari sualın vaxtını dondurur).
 *
 * Komponent native <select> deyil: aparıcı səhifələrində bootstrap_select yüklənmir, ona görə
 * buradakı seçicilər kimi (dil / musiqi) `hx-seg` seqment düymələri + xüsusi dəyər sahəsidir.
 * Bir neçə yer (`[data-time-setting]`) eyni vəziyyəti göstərir; hadisələr document-də delegasiya
 * ilə bir dəfə bağlanır (səhnə yenidən çəkiləndə dinləyici yığılmır).
 */
import { state } from './state.js?v=lx20261008';
import { postJson } from './api.js?v=lx20261008';
import { icon } from './icons.js?v=lx20261008';
import { showToast } from './toast.js?v=lx20261008';
import { controlsEnabled, esc, fmt, tr } from './utils.js?v=lx20261008';

const DEFAULTS = { default: 30, presets: [10, 20, 30, 60, 90, 120], min: 5, max: 300 };
let bound = false;
let pending = false;
let menuSeq = 0;

export const timeConfig = () => Object.assign({}, DEFAULTS, CONFIG.questionTime || {});

/** Aparıcının seçdiyi dəyər (saniyə) və ya `null` — «Standart». */
export function chosenSeconds() {
    const value = Number(state.sessionSettings?.question_time_seconds);
    return Number.isFinite(value) && value > 0 ? Math.round(value) : null;
}

/** Növbəti sualın vaxtı (seçim yoxdursa imtahanın standart vaxtı / 30 s). */
export const effectiveSeconds = () => chosenSeconds() || Number(timeConfig().default) || 30;

export const secondsLabel = (seconds) => fmt(tr("timeSecondsValue", "{seconds} san"), { seconds: Number(seconds) || 0 });

function valueLabel() {
    const chosen = chosenSeconds();
    return chosen ? secondsLabel(chosen) : fmt(tr("timeStandard", "Standart · {seconds} san"), { seconds: timeConfig().default });
}

function noteText() {
    if (state.sessionState === "question" || state.sessionState === "reveal") {
        return tr("timeNoteNext", "Dəyişiklik növbəti sualdan tətbiq olunur.");
    }
    return chosenSeconds()
        ? tr("timeNoteAll", "Hər sual bu qədər vaxt gedəcək.")
        : tr("timeNoteStandard", "Standart: sualın öz vaxtı, yoxdursa imtahanın vaxtı.");
}

function choiceMarkup(value, label, active) {
    return `<button type="button" class="hx-seg__btn" role="radio" aria-checked="${active ? "true" : "false"}" tabindex="${active ? 0 : -1}" data-time-choice="${value}">${esc(label)}</button>`;
}

function menuMarkup(id) {
    const cfg = timeConfig();
    const chosen = chosenSeconds();
    const presets = (cfg.presets || []).map((seconds) => choiceMarkup(seconds, secondsLabel(seconds), chosen === Number(seconds)));
    const custom = chosen && !(cfg.presets || []).map(Number).includes(chosen) ? chosen : "";
    return `
        <div class="hx-timeset__menu" id="${id}" data-time-menu role="dialog" aria-label="${esc(tr("timeLabel", "Hər sual üçün vaxt"))}" hidden>
            <div class="hx-seg hx-seg--wrap hx-timeset__choices" role="radiogroup" aria-label="${esc(tr("timeLabel", "Hər sual üçün vaxt"))}">
                ${choiceMarkup("", fmt(tr("timeStandard", "Standart · {seconds} san"), { seconds: cfg.default }), !chosen)}
                ${presets.join("")}
            </div>
            <form class="hx-timeset__custom" data-time-custom-form novalidate>
                <label class="hx-timeset__custom-label" for="${id}-custom">${esc(fmt(tr("timeCustom", "Digər ({min}–{max} san)"), { min: cfg.min, max: cfg.max }))}</label>
                <input id="${id}-custom" class="hx-timeset__input" type="number" inputmode="numeric" min="${cfg.min}" max="${cfg.max}" step="1" value="${custom}" data-time-custom>
                <button type="submit" class="hx-btn hx-btn--gold hx-timeset__apply">${esc(tr("timeApply", "Tətbiq et"))}</button>
            </form>
            <p class="hx-timeset__note" data-time-note>${esc(noteText())}</p>
        </div>
    `;
}

function mountMarkup(editable) {
    menuSeq += 1;
    const id = `hxTimeMenu${menuSeq}`;
    const label = `<span class="hx-timeset__label">${icon("timer")}<span>${esc(tr("timeLabel", "Hər sual üçün vaxt"))}:</span></span>`;
    if (!editable) {
        return `${label}<strong class="hx-timeset__value" data-time-value>${esc(valueLabel())}</strong>`;
    }
    return `
        ${label}
        <button type="button" class="hx-timeset__toggle" data-time-toggle aria-haspopup="dialog" aria-expanded="false" aria-controls="${id}">
            <strong data-time-value>${esc(valueLabel())}</strong>${icon("chevronDown")}
        </button>
        ${menuMarkup(id)}
    `;
}

/** Bütün `[data-time-setting]` yerlərini (lobbi səhnəsi, idarə paneli) cari vəziyyətlə yeniləyir. */
export function renderTimeSettings(root = document) {
    const editable = controlsEnabled() && Boolean(CONFIG?.urls?.settings);
    root.querySelectorAll("[data-time-setting]").forEach((mount) => {
        const signature = `${editable ? 1 : 0}:${chosenSeconds() || ""}:${state.sessionState}:${pending ? 1 : 0}`;
        const open = mount.classList.contains("is-open");
        if (mount.dataset.signature === signature && mount.firstElementChild) return;
        if (open && mount.dataset.signature) {
            // Menyu açıqdırsa yalnız dəyəri / seçimi yenilə (fokus itməsin).
            mount.querySelector("[data-time-value]").textContent = valueLabel();
            mount.querySelectorAll("[data-time-choice]").forEach((button) => {
                const active = Number(button.dataset.timeChoice || 0) === Number(chosenSeconds() || 0);
                button.setAttribute("aria-checked", active ? "true" : "false");
            });
            const note = mount.querySelector("[data-time-note]");
            if (note) note.textContent = noteText();
            mount.dataset.signature = signature;
            return;
        }
        mount.classList.add("hx-timeset");
        mount.classList.toggle("is-readonly", !editable);
        mount.classList.toggle("is-busy", pending);
        mount.innerHTML = mountMarkup(editable);
        mount.dataset.signature = signature;
    });
}

function setOpen(mount, open) {
    if (!mount) return;
    const menu = mount.querySelector("[data-time-menu]");
    const toggle = mount.querySelector("[data-time-toggle]");
    if (!menu || !toggle) return;
    mount.classList.toggle("is-open", open);
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
        const active = menu.querySelector("[data-time-choice][aria-checked='true']") || menu.querySelector("[data-time-choice]");
        window.requestAnimationFrame(() => active?.focus());
    }
}

function closeAll(except = null) {
    document.querySelectorAll("[data-time-setting].is-open").forEach((mount) => {
        if (mount !== except) setOpen(mount, false);
    });
}

async function apply(mount, value) {
    if (pending) return;
    const cfg = timeConfig();
    let seconds = value === "" || value == null ? null : Math.round(Number(value));
    if (seconds !== null && (!Number.isFinite(seconds) || seconds < cfg.min || seconds > cfg.max)) {
        const input = mount.querySelector("[data-time-custom]");
        input?.setCustomValidity(fmt(tr("timeInvalid", "{min}–{max} saniyə arası rəqəm yazın"), { min: cfg.min, max: cfg.max }));
        input?.reportValidity();
        return;
    }
    pending = true;
    setOpen(mount, false);
    renderTimeSettings();
    try {
        const result = await postJson(CONFIG.urls.settings, { question_time_seconds: seconds });
        if (result?.ok) showToast(fmt(tr("timeSaved", "Hər sual üçün vaxt: {value}"), { value: valueLabel() }), "ok");
        else showToast(result?.message || tr("timeSaveError", "Vaxt saxlanmadı. Yenidən cəhd edin."), "error");
    } finally {
        pending = false;
        renderTimeSettings();
        mount.querySelector("[data-time-toggle]")?.focus();
    }
}

export function bindTimeSettingEvents() {
    if (bound) return;
    bound = true;
    document.addEventListener("click", (event) => {
        const toggle = event.target.closest?.("[data-time-toggle]");
        if (toggle) {
            const mount = toggle.closest("[data-time-setting]");
            const open = !mount.classList.contains("is-open");
            closeAll(mount);
            setOpen(mount, open);
            return;
        }
        const choice = event.target.closest?.("[data-time-choice]");
        if (choice) {
            apply(choice.closest("[data-time-setting]"), choice.dataset.timeChoice);
            return;
        }
        if (!event.target.closest?.("[data-time-menu]")) closeAll();
    });
    document.addEventListener("submit", (event) => {
        const form = event.target.closest?.("[data-time-custom-form]");
        if (!form) return;
        event.preventDefault();
        apply(form.closest("[data-time-setting]"), form.querySelector("[data-time-custom]")?.value ?? "");
    });
    document.addEventListener("input", (event) => {
        if (event.target.matches?.("[data-time-custom]")) event.target.setCustomValidity("");
    });
    document.addEventListener("keydown", (event) => {
        const mount = event.target.closest?.("[data-time-setting].is-open");
        if (!mount) return;
        if (event.key === "Escape") {
            event.stopPropagation();
            setOpen(mount, false);
            mount.querySelector("[data-time-toggle]")?.focus();
            return;
        }
        if (!event.target.matches?.("[data-time-choice]") || !["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(event.key)) return;
        event.preventDefault();
        const list = Array.from(mount.querySelectorAll("[data-time-choice]"));
        const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
        list[(list.indexOf(event.target) + step + list.length) % list.length]?.focus();
    });
    window.addEventListener("live-host-state", () => renderTimeSettings());
}
