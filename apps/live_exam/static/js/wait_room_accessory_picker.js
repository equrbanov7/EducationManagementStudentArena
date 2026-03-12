(function () {
    class AccessoryPicker {
        constructor(root, options) {
            this.root = root;
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.value = this.options.value || this.catalog.defaultAccessoryKey || "accessory_none";
            this.onChange = this.options.onChange || function () {};
        }

        render() {
            if (!this.root) return;
            this.root.innerHTML = "";
            (this.catalog.accessoryKeys || []).forEach((accessoryKey) => {
                const meta = this.catalog.accessories?.[accessoryKey] || { label: accessoryKey, icon: "○" };
                const button = document.createElement("button");
                button.type = "button";
                button.className = "wait-room-picker__chip";
                button.dataset.accessoryKey = accessoryKey;
                button.setAttribute("aria-pressed", accessoryKey === this.value ? "true" : "false");
                button.innerHTML = `
                    <span class="wait-room-picker__chip-icon">${meta.icon}</span>
                    <span class="wait-room-picker__chip-label">${meta.label}</span>
                `;
                button.addEventListener("click", () => {
                    const nextValue =
                        accessoryKey === this.value && accessoryKey !== (this.catalog.defaultAccessoryKey || "accessory_none")
                            ? this.catalog.defaultAccessoryKey || "accessory_none"
                            : accessoryKey;
                    this.setValue(nextValue);
                    this.onChange(this.value);
                });
                button.title = meta.label;
                this.root.appendChild(button);
            });
            this.syncSelection();
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
