(function () {
    class ReactionPanel {
        constructor(options) {
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.root = this.options.root;
            this.list = this.options.list;
            this.fab = this.options.fab;
            this.overlay = this.options.overlay;
            this.cooldownMs = this.options.cooldownMs || 1200;
            this.cooldownUntil = 0;
            this.cooldownTimer = null;
            this.onSend = this.options.onSend || (async function () {});
        }

        init() {
            if (!this.root || !this.list || !this.fab) return;
            this.renderButtons();
            this.fab.addEventListener("click", () => this.root.classList.toggle("is-open"));
            document.addEventListener("click", (event) => {
                if (!this.root.contains(event.target)) this.root.classList.remove("is-open");
            });
        }

        renderButtons() {
            this.list.innerHTML = "";
            (this.catalog.reactionKeys || []).forEach((reactionKey) => {
                const meta = this.catalog.reactions?.[reactionKey];
                const button = document.createElement("button");
                button.type = "button";
                button.className = "wait-room-reaction__button";
                button.dataset.reactionKey = reactionKey;
                button.innerHTML = `<span>${meta?.emoji || "✨"}</span>`;
                button.setAttribute("aria-label", meta?.label || reactionKey);
                button.addEventListener("click", async () => {
                    if (Date.now() < this.cooldownUntil) return;
                    this.cooldownUntil = Date.now() + this.cooldownMs;
                    this.syncCooldown();
                    this.root.classList.remove("is-open");
                    await this.onSend(reactionKey);
                });
                this.list.appendChild(button);
            });
            this.syncCooldown();
        }

        syncCooldown() {
            const disabled = Date.now() < this.cooldownUntil;
            this.list.querySelectorAll("button").forEach((button) => {
                button.disabled = disabled;
            });
            if (this.fab) {
                this.fab.disabled = disabled;
            }
            this.root?.classList.toggle("is-cooldown", disabled);
            if (disabled) {
                this.scheduleCooldownRelease();
            } else if (this.cooldownTimer) {
                window.clearTimeout(this.cooldownTimer);
                this.cooldownTimer = null;
            }
        }

        setCooldown(durationMs) {
            const nextCooldownUntil = Date.now() + Math.max(0, Number(durationMs) || 0);
            if (nextCooldownUntil > this.cooldownUntil) {
                this.cooldownUntil = nextCooldownUntil;
                this.root?.classList.remove("is-open");
            }
            this.syncCooldown();
        }

        scheduleCooldownRelease() {
            if (this.cooldownTimer) {
                window.clearTimeout(this.cooldownTimer);
            }
            const remaining = Math.max(0, this.cooldownUntil - Date.now());
            if (!remaining) {
                this.syncCooldown();
                return;
            }
            this.cooldownTimer = window.setTimeout(() => {
                this.cooldownTimer = null;
                this.syncCooldown();
            }, remaining + 40);
        }

        spawn(eventData) {
            if (!this.overlay) return;
            const meta = this.catalog.reactions?.[eventData?.reaction_key] || {};
            const node = document.createElement("div");
            node.className = "wait-room-reaction__burst";
            node.innerHTML = `<span>${meta.emoji || eventData?.emoji || "✨"}</span>`;
            const left = 12 + Math.random() * 72;
            const drift = -18 + Math.random() * 36;
            node.style.left = `${left}%`;
            node.style.setProperty("--reaction-drift", `${drift}px`);
            this.overlay.appendChild(node);
            window.setTimeout(() => node.remove(), 2100);
        }
    }

    window.LiveWaitRoomReactionPanel = ReactionPanel;
})();
