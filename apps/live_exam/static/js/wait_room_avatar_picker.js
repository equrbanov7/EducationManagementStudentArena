/* wait_room_avatar_picker.js — avatar seçicisi (LX-FE-PLAYER 2026-09-29).
 * Tək delegasiya dinləyicisi (stabil kök elementdə); düymələr aksesuar dəyişəndə yenidən qurulur.
 * Adlar i18n-dən (options.labels[key]) gəlir, yoxdursa kataloqdakı ad. */
(function () {
    "use strict";

    function esc(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    class AvatarPicker {
        constructor(root, options) {
            this.root = root;
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.value = this.options.value || this.catalog.defaultAvatarKey || "avatar_1";
            this.onChange = this.options.onChange || function () {};
            if (this.root && !this.root.dataset.lxBound) {
                this.root.dataset.lxBound = "1";
                this.root.addEventListener("click", (event) => {
                    const button = event.target.closest("[data-avatar-key]");
                    if (!button || !this.root.contains(button)) return;
                    this.setValue(button.dataset.avatarKey);
                    this.onChange(this.value);
                });
            }
        }

        label(avatarKey) {
            const labels = this.options.labels || {};
            return labels[avatarKey] || this.catalog.avatars?.[avatarKey]?.label || avatarKey;
        }

        render() {
            if (!this.root || !window.LiveAvatarRenderer) return;
            const accessory = this.options.previewAccessoryKey || this.catalog.defaultAccessoryKey || "accessory_none";
            this.root.innerHTML = (this.catalog.avatarKeys || [])
                .map((avatarKey) => {
                    const art = window.LiveAvatarRenderer.renderAvatarMarkup(
                        { avatar_key: avatarKey, accessory_key: accessory },
                        { size: Number(this.options.avatarSize || 60), className: "lxw-grid__art", interactive: false }
                    );
                    const selected = avatarKey === this.value;
                    return (
                        `<button type="button" class="lxw-grid__item${selected ? " is-selected" : ""}" data-avatar-key="${esc(avatarKey)}" ` +
                        `aria-pressed="${selected ? "true" : "false"}" aria-label="${esc(this.label(avatarKey))}" title="${esc(this.label(avatarKey))}">${art}</button>`
                    );
                })
                .join("");
        }

        setPreviewAccessoryKey(accessoryKey) {
            if (this.options.previewAccessoryKey === accessoryKey) return;
            this.options.previewAccessoryKey = accessoryKey;
            this.render();
        }

        setValue(value) {
            this.value = value;
            this.syncSelection();
        }

        syncSelection() {
            if (!this.root) return;
            this.root.querySelectorAll("[data-avatar-key]").forEach((button) => {
                const selected = button.dataset.avatarKey === this.value;
                button.classList.toggle("is-selected", selected);
                button.setAttribute("aria-pressed", selected ? "true" : "false");
            });
        }
    }

    window.LiveWaitRoomAvatarPicker = AvatarPicker;
})();
