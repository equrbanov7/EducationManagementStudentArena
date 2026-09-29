/* wait_room_profile_sheet.js — gözləmə otağının «görünüşü dəyiş» alt vərəqi (LX-FE-PLAYER 2026-09-29).
 * wait_room_page.js-dən ayrılıb (600 sətir limiti). Ad sahəsi (sayğac; kilidli lobbidə bağlı),
 * avatar/aksesuar tabları (şəbəkələr yalnız ilk açılışda qurulur), önizləmə, yadda saxlama.
 * API: LiveWaitRoomProfileSheet.create(ctx) → {open, close, save, setPanel, renderPreview}.
 */
(function () {
    "use strict";

    const NICK_MAX = 32;

    function create(ctx) {
        const { dom, tr, config, catalog, avatar, nicknameTools, avatarLabels, accessoryLabels } = ctx;
        const { getState, applyLocked, onSaved, onFailed } = ctx;
        const $ = (id) => document.getElementById(id);
        let lastFocus = null;

        const avatarPicker = new window.LiveWaitRoomAvatarPicker($("waitRoomAvatarGrid"), {
            value: getState().me.avatar_key,
            previewAccessoryKey: getState().me.accessory_key,
            labels: avatarLabels,
            onChange: renderPreview,
        });
        const accessoryPicker = new window.LiveWaitRoomAccessoryPicker($("waitRoomAccessoryGrid"), {
            value: getState().me.accessory_key,
            labels: accessoryLabels,
            onChange: (value) => {
                avatarPicker.setPreviewAccessoryKey(value);
                renderPreview();
            },
        });

        function validate() {
            const messages = {
                required: tr("nicknameRequired", "Ad boş ola bilməz."),
                tooLong: tr("nicknameTooLong", "Ad çox uzundur."),
            };
            if (typeof nicknameTools.validateNickname === "function") {
                return nicknameTools.validateNickname(dom.nickInput.value, messages);
            }
            const value = String(dom.nickInput.value || "").trim();
            return { valid: Boolean(value), value, message: value ? "" : messages.required };
        }

        function renderPreview() {
            if (dom.preview) {
                dom.preview.innerHTML = avatar(
                    { avatar_key: avatarPicker.value, accessory_key: accessoryPicker.value },
                    112,
                    { crop: "full", className: "lxw-sheet__art", dance: "idle" }
                );
            }
            if (dom.nickCount) dom.nickCount.textContent = `${dom.nickInput.value.length}/${NICK_MAX}`;
        }

        function setPanel(key) {
            const active = key === "accessory" ? "accessory" : "avatar";
            document.querySelectorAll("[data-wait-room-panel-target]").forEach((tab) => {
                const on = tab.dataset.waitRoomPanelTarget === active;
                tab.classList.toggle("is-active", on);
                tab.setAttribute("aria-selected", on ? "true" : "false");
            });
            document.querySelectorAll("[data-wait-room-panel]").forEach((panel) => {
                const on = panel.dataset.waitRoomPanel === active;
                panel.classList.toggle("is-active", on);
                panel.hidden = !on || getState().settings.characters_enabled === false;
            });
        }

        let pickersRendered = false;

        function openSheet() {
            if (getState().done || !dom.sheet) return;
            if (!pickersRendered) {
                // 16 avatar SVG-si yalnız vərəq ilk dəfə açılanda qurulur (ilk yüklənmədə ~1100 DOM qovşağı azdır).
                pickersRendered = true;
                avatarPicker.render();
                accessoryPicker.render();
            }
            lastFocus = document.activeElement;
            dom.nickInput.value = getState().me.nickname || "";
            dom.nickError.textContent = "";
            avatarPicker.setValue(getState().me.avatar_key || catalog.defaultAvatarKey);
            accessoryPicker.setValue(getState().me.accessory_key || catalog.defaultAccessoryKey);
            avatarPicker.options.previewAccessoryKey = null;
            avatarPicker.setPreviewAccessoryKey(accessoryPicker.value);
            accessoryPicker.render();
            renderPreview();
            setPanel("avatar");
            applyLocked();
            dom.backdrop.hidden = false;
            dom.sheet.hidden = false;
            document.body.classList.add("lxw-sheet-open");
            window.requestAnimationFrame(() => dom.sheet.classList.add("is-open"));
            window.setTimeout(() => {
                (getState().locked ? dom.saveButton : dom.nickInput).focus({ preventScroll: true });
            }, 120);
        }

        function closeSheet() {
            if (!dom.sheet || dom.sheet.hidden) return;
            dom.sheet.classList.remove("is-open");
            document.body.classList.remove("lxw-sheet-open");
            dom.backdrop.hidden = true;
            dom.sheet.hidden = true;
            if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
        }

        async function saveProfile() {
            const validation = validate();
            dom.nickInput.value = validation.value;
            dom.nickError.textContent = validation.valid ? "" : validation.message;
            if (!validation.valid) return;
            dom.saveButton.disabled = true;
            try {
                const body = new FormData();
                body.append("nickname", getState().locked ? getState().me.nickname || validation.value : validation.value);
                body.append("avatar_key", avatarPicker.value);
                body.append("accessory_key", accessoryPicker.value);
                const response = await fetch(config.profileUrl, {
                    method: "POST",
                    headers: { "X-CSRFToken": config.csrf },
                    credentials: "same-origin",
                    body,
                });
                let data = {};
                try {
                    data = await response.json();
                } catch (error) {
                    data = {};
                }
                if (response.ok && data.ok) {
                    closeSheet();
                    onSaved(data.player || {});
                    return;
                }
                const message = String(data.message || "").trim();
                dom.nickError.textContent =
                    message && !/^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/.test(message)
                        ? message
                        : tr("saveFailed", "Dəyişiklikləri saxlamaq olmadı.");
                onFailed();
            } catch (error) {
                dom.nickError.textContent = tr("saveFailed", "Dəyişiklikləri saxlamaq olmadı.");
            } finally {
                dom.saveButton.disabled = false;
            }
        }

        return { open: openSheet, close: closeSheet, save: saveProfile, setPanel, renderPreview };
    }

    window.LiveWaitRoomProfileSheet = { create };
})();
