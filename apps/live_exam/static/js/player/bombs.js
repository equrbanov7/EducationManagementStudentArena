// Optional game effect: the server owns all score/penalty decisions.
export function createBombUI({ state, pin, document, storage, reducedMotion = () => false, labels = {} }) {
    const seen = new Set();
    const message = labels.result || "Bomba partladı — bu oyundakı xalın sıfırlandı.";
    function refresh() {
        const question = state.currentQuestion;
        const active = document.querySelector(".lxp-view:not(.is-leaving)") || document;
        const kicker = active.querySelector(".lxp-kicker");
        if (question?.is_bomb && kicker && !kicker.parentNode.querySelector("[data-bomb-rule]")) {
            const rule = document.createElement("p");
            rule.className = "lxp-bomb-rule";
            rule.dataset.bombRule = "";
            rule.textContent = labels.rule || "💣 Bomba sualı: səhv və ya qismən düzgün cavab bu oyundakı xalını sıfırlayır.";
            kicker.insertAdjacentElement("afterend", rule);
        }
        const result = active.querySelector(".lxp-result");
        const answer = state.currentAnswer;
        if (!result || !question || answer?.bomb_triggered !== true) return;
        if (!result.querySelector("[data-bomb-result]")) {
            const notice = document.createElement("p");
            notice.className = "lxp-bomb-notice";
            notice.dataset.bombResult = "";
            notice.setAttribute("role", "status");
            notice.textContent = message;
            result.appendChild(notice);
        }
        const key = `live-bomb:${pin}:${state.player.id}:${question.id}`;
        let stored = false;
        try { stored = storage?.getItem(key) === "seen"; } catch (_) { /* storage can be unavailable */ }
        if (seen.has(key) || stored) return;
        seen.add(key);
        try { storage?.setItem(key, "seen"); } catch (_) { /* memory guard still prevents repeats */ }
        // Static notice remains for reduced-motion users; no flashes or audio.
        if (reducedMotion()) return;
        const burst = document.createElement("span");
        burst.className = "lxp-bomb-burst";
        burst.setAttribute("aria-hidden", "true");
        burst.textContent = "💥";
        result.appendChild(burst);
        burst.addEventListener("animationend", () => burst.remove(), { once: true });
    }
    return { refresh };
}

export function installBombUI(options) {
    const ui = createBombUI(options);
    const root = options.document.getElementById("lxpViews");
    if (!root) return;
    const observer = new MutationObserver(() => ui.refresh());
    observer.observe(root, { childList: true, subtree: true });
    ui.refresh();
    window.addEventListener("beforeunload", () => observer.disconnect(), { once: true });
}
