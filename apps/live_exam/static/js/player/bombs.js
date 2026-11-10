// Optional game effect: the server owns all score/penalty decisions.
const BOMB_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="11" cy="14" r="7" fill="#1b1d29"/><path d="M14.5 7.5l2.2-2.2M16.7 5.3c1.4-1.3 2.9-.9 3.6.4" fill="none" stroke="#c9a46a" stroke-width="2" stroke-linecap="round"/><circle cx="21" cy="4.5" r="1.6" fill="#ffd166"/></svg>';
const SHARDS = 16;

/** Partlayış qırıntılarının yolu — deterministik, CSP-safe (`style.setProperty`, inline `style=` yox). */
export function shardVars(index, count = SHARDS) {
    return {
        "--a": `${Math.round((index / count) * 360 + (index % 2) * 11)}deg`,
        "--d": `${34 + (index % 5) * 8}vmin`,
        "--s": String(0.6 + (index % 4) * 0.25),
        "--t": `${0.55 + (index % 3) * 0.12}s`,
    };
}

export function createBombUI({ state, pin, document, storage, reducedMotion = () => false, labels = {}, onExplode }) {
    const seen = new Set();
    const message = labels.result || "Bomba partladı — bu oyundakı xalın sıfırlandı.";
    function refresh() {
        const question = state.currentQuestion;
        const active = document.querySelector(".lxp-view:not(.is-leaving)") || document;
        // 2026-11-10: qayda mətni yalnız raund görünüşlərində («Hazır ol», giriş, sual) — nəticə/liderlər/final
        // ekranlarına yazılmır; güc nişanı sırası (`data-no-bomb-rule`) da qayda üçün deyil.
        const kicker = active.querySelector(
            ".lxp-ready .lxp-kicker:not([data-no-bomb-rule]), .lxp-intro .lxp-kicker:not([data-no-bomb-rule]), .lxp-round .lxp-kicker:not([data-no-bomb-rule])"
        );
        if (question?.is_bomb && kicker && !kicker.parentNode.querySelector("[data-bomb-rule]")) {
            const rule = document.createElement("p");
            rule.className = "lxp-bomb-rule";
            rule.dataset.bombRule = "";
            rule.textContent = (labels.rule || "💣 Bomba sualı: səhv və ya qismən düzgün cavab bu oyundakı xalını sıfırlayır.").replace(/^💣\s*/, "");
            rule.insertAdjacentHTML("afterbegin", BOMB_ICON);
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
        if (typeof onExplode === "function") {
            try { onExplode(key); } catch (_) { /* səs/vibrasiya effekti görünüşü sındırmasın */ }
        }
        // Static notice remains for reduced-motion users; no flashes or audio.
        if (reducedMotion()) return;
        // 2026-11-10: zəngin partlayış — flaş, iki dalğa, bomba nüvəsi, qırıntılar + ekran titrəyişi.
        const burst = document.createElement("span");
        burst.className = "lxp-bomb-burst";
        burst.setAttribute("aria-hidden", "true");
        const shards = Array.from({ length: SHARDS }, (_, i) => `<i class="lxp-bomb-burst__shard" data-shard="${i}"></i>`).join("");
        burst.innerHTML =
            `<span class="lxp-bomb-burst__flash"></span><span class="lxp-bomb-burst__wave"></span>` +
            `<span class="lxp-bomb-burst__wave lxp-bomb-burst__wave--2"></span><span class="lxp-bomb-burst__core">${BOMB_ICON}</span>${shards}`;
        burst.querySelectorAll("[data-shard]").forEach((shard) => {
            const vars = shardVars(Number(shard.dataset.shard));
            Object.keys(vars).forEach((name) => shard.style.setProperty(name, vars[name]));
        });
        result.appendChild(burst);
        const body = document.body;
        if (body) {
            body.classList.add("lxp-shake");
            setTimeout(() => body.classList.remove("lxp-shake"), 720);
        }
        burst.addEventListener("animationend", (event) => { if (event.target === burst) burst.remove(); }, { once: true });
        setTimeout(() => burst.isConnected && burst.remove(), 2600);
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
