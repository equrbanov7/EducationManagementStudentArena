(function () {
    class AvatarPicker {
        constructor(root, options) {
            this.root = root;
            this.options = options || {};
            this.catalog = window.LiveAvatarCatalog || {};
            this.value = this.options.value || this.catalog.defaultAvatarKey || "avatar_1";
            this.onChange = this.options.onChange || function () {};
        }

        render() {
            if (!this.root) return;
            this.root.innerHTML = "";
            (this.catalog.avatarKeys || []).forEach((avatarKey) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "wait-room-picker__item";
                button.dataset.avatarKey = avatarKey;
                button.setAttribute("aria-pressed", avatarKey === this.value ? "true" : "false");
                button.innerHTML = window.LiveAvatarRenderer.renderAvatarMarkup(
                    { avatar_key: avatarKey, accessory_key: this.options.previewAccessoryKey || "accessory_none" },
                    {
                        size: Number(this.options.avatarSize || 62),
                        className: "wait-room-picker__avatar",
                        interactive: false,
                    }
                );
                button.addEventListener("click", () => {
                    this.setValue(avatarKey);
                    this.onChange(this.value);
                });
                this.root.appendChild(button);
            });
            this.syncSelection();
        }

        setPreviewAccessoryKey(accessoryKey) {
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
