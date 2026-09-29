/* wait_room_accessory_picker.js — aksesuar çipləri (LX-FE-PLAYER 2026-09-29).
 * İkon: LiveAvatarRenderer.renderAccessoryIcon (SVG; LX-FE-STAGE), yoxdursa kataloq simvolu.
 * Eyni çipə təkrar toxunuş aksesuarı çıxarır («yoxdur»). */
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

    class AccessoryPicker {
        constructor(root, options) {
            this.root = root;
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.none = this.catalog.defaultAccessoryKey || "accessory_none";
            this.value = this.options.value || this.none;
            this.onChange = this.options.onChange || function () {};
            if (this.root && !this.root.dataset.lxBound) {
                this.root.dataset.lxBound = "1";
                this.root.addEventListener("click", (event) => {
                    const button = event.target.closest("[data-accessory-key]");
                    if (!button || !this.root.contains(button)) return;
                    const key = button.dataset.accessoryKey;
                    this.setValue(key === this.value && key !== this.none ? this.none : key);
                    this.onChange(this.value);
                });
            }
        }

        label(key) {
            const labels = this.options.labels || {};
            return labels[key] || this.catalog.accessories?.[key]?.label || key;
        }

        icon(key) {
            const renderer = window.LiveAvatarRenderer;
            if (renderer && typeof renderer.renderAccessoryIcon === "function") {
                return renderer.renderAccessoryIcon(key, 30);
            }
            return esc(this.catalog.accessories?.[key]?.icon || "○");
        }

        render() {
            if (!this.root) return;
            this.root.innerHTML = (this.catalog.accessoryKeys || [])
                .map((key) => {
                    const selected = key === this.value;
                    return (
                        `<button type="button" class="lxw-chipbtn${selected ? " is-selected" : ""}" data-accessory-key="${esc(key)}" aria-pressed="${selected ? "true" : "false"}">` +
                        `<span class="lxw-chipbtn__icon" aria-hidden="true">${this.icon(key)}</span>` +
                        `<span class="lxw-chipbtn__label">${esc(this.label(key))}</span></button>`
                    );
                })
                .join("");
        }

        setValue(value) {
            this.value = value;
            this.syncSelection();
        }

        syncSelection() {
            if (!this.root) return;
            this.root.querySelectorAll("[data-accessory-key]").forEach((button) => {
                const selected = button.dataset.accessoryKey === this.value;
                button.classList.toggle("is-selected", selected);
                button.setAttribute("aria-pressed", selected ? "true" : "false");
            });
        }
    }

    window.LiveWaitRoomAccessoryPicker = AccessoryPicker;
})();
