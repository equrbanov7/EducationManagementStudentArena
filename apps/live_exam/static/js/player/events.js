// LX-FE-PLAYER (2026-09-29): hadisələr — hamısı delegasiya ilə (EMSDelegate.on; view-lar
// dəyişdikcə yeni düymələr avtomatik tutulur, dinləyici yığılmır).
import { TEXT_ANSWER_MAX_LENGTH } from './config.js?v=lx20260929';
import { handleOptionTap, submitAnswer } from './answer.js?v=lx20260929';
import { fetchState } from './api.js?v=lx20260929';
import { isMuted, onAudioChange, playSound, setMuted, unlockAudio } from './audio.js?v=lx20260929';
import { markUserActivation } from './haptics.js?v=lx20260929';
import { isSocketOpen, reconnectNow } from './sockets.js?v=lx20260929';
import { state } from './state.js?v=lx20260929';
import { renderSoundToggle, setNetStatus } from './ui.js?v=lx20260929';
import { toInt, tr } from './utils.js?v=lx20260929';

function delegate(type, selector, handler) {
    if (window.EMSDelegate && typeof window.EMSDelegate.on === "function") {
        window.EMSDelegate.on(type, selector, handler);
        return;
    }
    document.addEventListener(type, (event) => {
        const match = event.target && event.target.closest ? event.target.closest(selector) : null;
        if (match) handler.call(match, event, match);
    });
}

const inLeavingView = (el) => Boolean(el && el.closest(".lxp-view.is-leaving"));

function syncTypedControls(input) {
    const form = input.closest("[data-lxp-typed]");
    if (!form) return;
    const max = toInt(input.dataset.max, TEXT_ANSWER_MAX_LENGTH) || TEXT_ANSWER_MAX_LENGTH;
    const length = input.value.length;
    const counter = form.querySelector("[data-lxp-typed-count]");
    if (counter) {
        counter.textContent = `${length}/${max}`;
        counter.classList.toggle("is-near", length >= max - 5);
    }
    const send = form.querySelector("[data-lxp-typed-send]");
    if (send) send.disabled = !input.value.trim() || Boolean(state.pendingSubmit);
}

function bindKeyboardAwareness() {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => {
        const keyboard = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
        document.documentElement.style.setProperty("--lxp-kb", `${Math.round(keyboard)}px`);
        const open = keyboard > 120;
        document.body.classList.toggle("lxp-kb-open", open);
        const active = document.activeElement;
        if (open && active && active.matches && active.matches("[data-lxp-typed-input]")) {
            const form = active.closest("[data-lxp-typed]");
            if (form) form.scrollIntoView({ block: "end", behavior: "smooth" });
        }
    };
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
}

export function bindPlayerEvents() {
    delegate("click", "[data-option-id]", (event, tile) => {
        if (inLeavingView(tile)) return;
        handleOptionTap(Number(tile.dataset.optionId));
    });
    delegate("click", "[data-lxp-submit]", (event, button) => {
        if (inLeavingView(button)) return;
        submitAnswer();
    });
    delegate("submit", "[data-lxp-typed]", (event, form) => {
        event.preventDefault();
        if (inLeavingView(form)) return;
        const input = form.querySelector("[data-lxp-typed-input]");
        if (submitAnswer({ text: input ? input.value : "" }) && input) input.blur();
    });
    delegate("input", "[data-lxp-typed-input]", (event, input) => {
        state.typedDraft = input.value;
        syncTypedControls(input);
    });
    delegate("click", "[data-lxp-expand]", (event, button) => {
        const card = button.closest(".lxp-qcard");
        if (!card) return;
        const expanded = card.classList.toggle("is-expanded");
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
        button.textContent = expanded ? tr("collapseQuestion", "Qısalt") : tr("expandQuestion", "Tam oxu");
    });
    delegate("click", "#soundToggle", () => {
        unlockAudio();
        setMuted(!isMuted());
        renderSoundToggle();
        if (!isMuted()) window.setTimeout(() => playSound("tap"), 60);
    });

    // Brauzerin autoplay siyasəti: səs konteksti ilk toxunuşda açılır.
    const onFirstGesture = () => {
        markUserActivation();
        unlockAudio();
        renderSoundToggle();
    };
    ["pointerdown", "touchstart", "keydown"].forEach((name) => {
        document.addEventListener(name, onFirstGesture, { passive: true, capture: true });
    });
    onAudioChange(renderSoundToggle);

    window.addEventListener("offline", () => setNetStatus("offline"));
    window.addEventListener("online", () => {
        // Brauzer oflayn rejimdə WS-i həmişə bağlamır — açıqdırsa zolaq sadəcə yığılır.
        if (isSocketOpen()) {
            setNetStatus("online");
        } else {
            setNetStatus("reconnecting");
            reconnectNow();
        }
        fetchState();
    });
    document.addEventListener("visibilitychange", () => {
        if (document.hidden || state.removed) return;
        reconnectNow();
        fetchState();
    });
    window.addEventListener("pageshow", (event) => {
        if (event.persisted && !state.removed) {
            reconnectNow();
            fetchState();
        }
    });
    bindKeyboardAwareness();
}
