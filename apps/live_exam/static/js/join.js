document.addEventListener("DOMContentLoaded", function () {
    const i18n = window.LIVE_EXAM_JOIN_I18N || {};
    const tr = (key, fallback) => i18n[key] || fallback;
    const catalog = window.LiveAvatarCatalog || {};
    const nicknameTools = window.LiveWaitRoomNicknameEditor || {};
    const rememberedPlayer = CONFIG.rememberedPlayer || null;

    const avatarGrid = document.getElementById("avatarGrid");
    const accessoryGrid = document.getElementById("accessoryGrid");
    const joinBtn = document.getElementById("joinBtn");
    const accessoryTab = document.getElementById("joinTabAccessory");
    const nicknameInput = document.getElementById("nickname");
    const nicknameError = document.getElementById("joinNicknameError");
    const joinStatus = document.getElementById("joinStatus");
    const preview = document.getElementById("joinPreview");
    const resumeNoticeBtn = document.getElementById("resumePlayerBtn");
    const resumePrompt = document.getElementById("joinResumePrompt");
    const resumeContinueBtn = document.getElementById("joinResumeContinue");
    const resumeRestartBtn = document.getElementById("joinResumeRestart");
    const resumeCloseBtn = document.getElementById("joinResumeClose");

    if (!avatarGrid || !accessoryGrid || !joinBtn || !nicknameInput || !preview) {
        return;
    }

    const defaultAvatar = catalog.defaultAvatarKey || "avatar_1";
    const defaultAccessory = catalog.defaultAccessoryKey || "accessory_none";
    const renderAvatarMarkup = (player, size, className) =>
        window.LiveAvatarRenderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });
    const normalizeNickname = (value) =>
        typeof nicknameTools.normalizeNickname === "function" ? nicknameTools.normalizeNickname(value) : String(value || "").trim();
    const validateNickname = (value) =>
        typeof nicknameTools.validateNickname === "function"
            ? nicknameTools.validateNickname(value, {
                required: tr("nicknameRequired", "Nickname is required."),
                tooLong: tr("nicknameTooLong", "Nickname is too long."),
            })
            : { valid: Boolean(normalizeNickname(value)), value: normalizeNickname(value), message: "" };

    let selectedAvatar = rememberedPlayer?.avatar_key || defaultAvatar;
    let selectedAccessory = rememberedPlayer?.accessory_key || defaultAccessory;
    let allowFreshJoin = !rememberedPlayer;
    let isJoining = false;

    if (!nicknameInput.value.trim() && rememberedPlayer?.nickname) {
        nicknameInput.value = rememberedPlayer.nickname;
    }

    function setStatus(message, kind) {
        if (!joinStatus) return;
        joinStatus.textContent = message || "";
        joinStatus.classList.remove("is-error", "is-success");
        if (kind) {
            joinStatus.classList.add(`is-${kind}`);
        }
    }

    function setNicknameError(message) {
        if (!nicknameError) return;
        nicknameError.textContent = message || "";
        nicknameInput.setAttribute("aria-invalid", message ? "true" : "false");
        nicknameInput.style.borderColor = message ? "#dc2626" : "";
        nicknameInput.style.boxShadow = message ? "0 0 0 4px rgba(220, 38, 38, 0.12)" : "";
    }

    function renderPreview() {
        const nickname = normalizeNickname(nicknameInput.value) || "Player";
        preview.innerHTML = `
            <div class="join-preview__avatar-shell">
                ${renderAvatarMarkup(
                    {
                        avatar_key: selectedAvatar,
                        accessory_key: selectedAccessory,
                    },
                    92,
                    "join-preview__avatar"
                )}
            </div>
            <div class="join-preview__player">
                <span class="join-preview__player-label">Player</span>
                <strong class="join-preview__player-name">${nickname}</strong>
            </div>
        `;
    }

    function setJoiningState(active) {
        isJoining = Boolean(active);
        joinBtn.disabled = isJoining;
        joinBtn.innerHTML = isJoining
            ? `<i class="fas fa-spinner fa-spin"></i><span>${tr("buttonJoining", "Joining...")}</span>`
            : `<i class="fas fa-play"></i><span>${tr("joinReady", "Join game")}</span>`;
    }

    function openResumePrompt() {
        if (!resumePrompt) return;
        resumePrompt.hidden = false;
        document.body.classList.add("join-modal-open");
    }

    function closeResumePrompt() {
        if (!resumePrompt) return;
        resumePrompt.hidden = true;
        document.body.classList.remove("join-modal-open");
    }

    function continuePreviousPlayer() {
        closeResumePrompt();
        if (CONFIG.resumeUrl) {
            window.location.href = CONFIG.resumeUrl;
        }
    }

    function shouldOfferResume(normalizedNickname) {
        if (!rememberedPlayer || allowFreshJoin) return false;
        return (
            normalizeNickname(rememberedPlayer.nickname) === normalizedNickname &&
            String(rememberedPlayer.avatar_key || defaultAvatar) === String(selectedAvatar) &&
            String(rememberedPlayer.accessory_key || defaultAccessory) === String(selectedAccessory)
        );
    }

    function switchPanel(target) {
        document.querySelectorAll("[data-join-panel-target]").forEach((button) => {
            const active = button.dataset.joinPanelTarget === target;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });

        document.querySelectorAll("[data-join-panel]").forEach((panel) => {
            const active = panel.dataset.joinPanel === target;
            panel.classList.toggle("is-active", active);
            panel.hidden = !active;
        });
    }

    async function submitJoin(forceFresh) {
        const validation = validateNickname(nicknameInput.value);
        const normalizedNickname = validation.value;
        nicknameInput.value = normalizedNickname;

        if (!validation.valid) {
            setNicknameError(validation.message);
            setStatus(validation.message, "error");
            nicknameInput.focus();
            renderPreview();
            return;
        }

        setNicknameError("");
        renderPreview();

        if (!forceFresh && shouldOfferResume(normalizedNickname)) {
            openResumePrompt();
            return;
        }

        setJoiningState(true);
        setStatus(tr("buttonJoining", "Joining..."));

        try {
            const formData = new FormData();
            formData.append("nickname", normalizedNickname);
            formData.append("avatar_key", selectedAvatar);
            formData.append("accessory_key", selectedAccessory);

            const response = await fetch(CONFIG.joinUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": CONFIG.csrf,
                },
                body: formData,
            });

            const data = await response.json();
            if (data.ok) {
                setStatus("");
                window.location.href = data.redirect;
                return;
            }

            setStatus(data.message || tr("errorUnknown", "An error occurred"), "error");
        } catch (error) {
            console.error(error);
            setStatus(tr("errorConnection", "Connection error"), "error");
        } finally {
            setJoiningState(false);
        }
    }

    const avatarPicker = typeof window.LiveWaitRoomAvatarPicker === "function"
        ? new window.LiveWaitRoomAvatarPicker(avatarGrid, {
            value: selectedAvatar,
            previewAccessoryKey: selectedAccessory,
            onChange: function (value) {
                selectedAvatar = value;
                renderPreview();
            },
        })
        : null;

    const accessoryPicker = typeof window.LiveWaitRoomAccessoryPicker === "function"
        ? new window.LiveWaitRoomAccessoryPicker(accessoryGrid, {
            value: selectedAccessory,
            onChange: function (value) {
                selectedAccessory = value;
                avatarPicker?.setPreviewAccessoryKey(selectedAccessory);
                renderPreview();
            },
        })
        : null;

    avatarPicker?.render();
    accessoryPicker?.render();
    if (accessoryTab) {
        accessoryTab.textContent = tr("accessoryLabel", "Accessory");
    }
    renderPreview();
    setStatus("");

    document.querySelectorAll("[data-join-panel-target]").forEach((button) => {
        button.addEventListener("click", function () {
            switchPanel(button.dataset.joinPanelTarget || "avatar");
        });
    });

    joinBtn.addEventListener("click", function () {
        if (!isJoining) {
            submitJoin(false);
        }
    });

    nicknameInput.addEventListener("input", function () {
        setNicknameError("");
        setStatus("");
        renderPreview();
    });

    nicknameInput.addEventListener("blur", function () {
        const normalizedNickname = normalizeNickname(nicknameInput.value);
        nicknameInput.value = normalizedNickname;
        renderPreview();
    });

    nicknameInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            joinBtn.click();
        }
    });

    resumeNoticeBtn?.addEventListener("click", continuePreviousPlayer);
    resumeContinueBtn?.addEventListener("click", continuePreviousPlayer);
    resumeRestartBtn?.addEventListener("click", function () {
        allowFreshJoin = true;
        closeResumePrompt();
        submitJoin(true);
    });
    resumeCloseBtn?.addEventListener("click", closeResumePrompt);

    resumePrompt?.addEventListener("click", function (event) {
        if (event.target === resumePrompt) {
            closeResumePrompt();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeResumePrompt();
        }
    });
});
