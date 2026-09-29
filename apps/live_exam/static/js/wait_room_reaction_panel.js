/* wait_room_reaction_panel.js — reaksiya sırası (LX-FE-PLAYER 2026-09-29).
 * Açılan FAB yerinə birbaşa 5 iri düymə (baş barmaq zonası). Soyuma (cooldown) hamısını
 * söndürür; server 429 verəndə Retry-After-a qədər sakitcə gözləyir. Uçan emojilər: eyni anda
 * ən çox 14 (zəif telefonlarda DOM şişməsin). */
(function () {
    "use strict";

    const MAX_BURSTS = 14;

    class ReactionPanel {
        constructor(options) {
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.root = this.options.root;
            this.list = this.options.list;
            this.overlay = this.options.overlay;
            this.cooldownMs = this.options.cooldownMs || 1200;
            this.cooldownUntil = 0;
            this.cooldownTimer = null;
            this.onSend = this.options.onSend || function () {};
        }

        init() {
            if (!this.root || !this.list) return;
            this.renderButtons();
            if (!this.list.dataset.lxBound) {
                this.list.dataset.lxBound = "1";
                this.list.addEventListener("click", (event) => {
                    const button = event.target.closest("[data-reaction-key]");
                    if (!button || button.disabled) return;
                    if (Date.now() < this.cooldownUntil) return;
                    this.setCooldown(this.cooldownMs);
                    button.classList.remove("is-sent");
                    void button.offsetWidth;
                    button.classList.add("is-sent");
                    this.onSend(button.dataset.reactionKey);
                });
            }
        }

        renderButtons() {
            this.list.textContent = "";
            (this.catalog.reactionKeys || []).forEach((reactionKey) => {
                const meta = this.catalog.reactions?.[reactionKey] || {};
                const button = document.createElement("button");
                button.type = "button";
                button.className = "lxw-react__btn";
                button.dataset.reactionKey = reactionKey;
                button.textContent = meta.emoji || "✨";
                button.setAttribute("aria-label", meta.label || reactionKey);
                this.list.appendChild(button);
            });
            this.syncCooldown();
        }

        setEnabled(enabled) {
            if (this.root) this.root.hidden = !enabled;
        }

        syncCooldown() {
            const disabled = Date.now() < this.cooldownUntil;
            this.list.querySelectorAll("button").forEach((button) => {
                button.disabled = disabled;
            });
            if (this.root) this.root.classList.toggle("is-cooldown", disabled);
            window.clearTimeout(this.cooldownTimer);
            this.cooldownTimer = null;
            if (disabled) {
                this.cooldownTimer = window.setTimeout(() => this.syncCooldown(), this.cooldownUntil - Date.now() + 40);
            }
        }

        setCooldown(durationMs) {
            const until = Date.now() + Math.max(0, Number(durationMs) || 0);
            if (until > this.cooldownUntil) this.cooldownUntil = until;
            this.syncCooldown();
        }

        spawn(eventData) {
            if (!this.overlay) return;
            if (this.overlay.childElementCount >= MAX_BURSTS) {
                this.overlay.firstElementChild.remove();
            }
            const meta = this.catalog.reactions?.[eventData?.reaction_key] || {};
            const node = document.createElement("span");
            node.className = "lxw-burst";
            node.textContent = meta.emoji || "✨";
            node.style.setProperty("--x", `${Math.round(8 + Math.random() * 80)}vw`);
            node.style.setProperty("--drift", `${Math.round(-24 + Math.random() * 48)}px`);
            this.overlay.appendChild(node);
            window.setTimeout(() => node.remove(), 2300);
        }
    }

    window.LiveWaitRoomReactionPanel = ReactionPanel;
})();
