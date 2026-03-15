document.addEventListener("DOMContentLoaded", function () {
    const i18n = window.LIVE_EXAM_JOIN_I18N || {};
    const tr = (key, fallback) => i18n[key] || fallback;
    const catalog = window.LiveAvatarCatalog || {};
    const nicknameTools = window.LiveWaitRoomNicknameEditor || {};
    const rememberedPlayer = CONFIG.rememberedPlayer || null;
    const sessionSettings = Object.assign({}, CONFIG.sessionSettings || {});
    const charactersEnabled = sessionSettings.characters_enabled !== false;
    let themeSocket = null;
    let themeReconnectTimer = null;
    let themeReconnectAttempts = 0;

    const joinBtn = document.getElementById("joinBtn");
    const nicknameInput = document.getElementById("nickname");
    const nicknameError = document.getElementById("joinNicknameError");
    const joinStatus = document.getElementById("joinStatus");
    const preview = document.getElementById("joinPreview");
    const resumeNoticeBtn = document.getElementById("resumePlayerBtn");
    const resumePrompt = document.getElementById("joinResumePrompt");
    const resumeContinueBtn = document.getElementById("joinResumeContinue");
    const resumeRestartBtn = document.getElementById("joinResumeRestart");
    const resumeCloseBtn = document.getElementById("joinResumeClose");

    if (!joinBtn || !nicknameInput || !preview) {
        return;
    }

    const defaultAvatar = catalog.defaultAvatarKey || "avatar_1";
    const defaultAccessory = catalog.defaultAccessoryKey || "accessory_none";
    const accessoryChoices = (catalog.accessoryKeys || []).filter((key) => key && key !== defaultAccessory);
    const renderAvatarMarkup = (player, size, className) =>
        window.LiveAvatarRenderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });
    const randomChoice = (items, fallback) => {
        const source = Array.isArray(items) ? items.filter(Boolean) : [];
        if (!source.length) return fallback;
        return source[Math.floor(Math.random() * source.length)] || fallback;
    };
    const normalizeNickname = (value) =>
        typeof nicknameTools.normalizeNickname === "function" ? nicknameTools.normalizeNickname(value) : String(value || "").trim();
    const validateNickname = (value) =>
        typeof nicknameTools.validateNickname === "function"
            ? nicknameTools.validateNickname(value, {
                required: tr("nicknameRequired", "Nickname is required."),
                tooLong: tr("nicknameTooLong", "Nickname is too long."),
            })
            : { valid: Boolean(normalizeNickname(value)), value: normalizeNickname(value), message: "" };

    let selectedAvatar = charactersEnabled ? randomChoice(catalog.avatarKeys, defaultAvatar) : defaultAvatar;
    let selectedAccessory = charactersEnabled ? randomChoice(accessoryChoices, defaultAccessory) : defaultAccessory;
    let allowFreshJoin = !rememberedPlayer;
    let isJoining = false;

    if (!nicknameInput.value.trim() && CONFIG.generatedNickname) {
        nicknameInput.value = CONFIG.generatedNickname;
    }
    if (!nicknameInput.value.trim() && rememberedPlayer?.nickname) {
        nicknameInput.value = rememberedPlayer.nickname;
    }

    function applySessionSettings(nextSettings) {
        Object.assign(sessionSettings, nextSettings || {});
        document.body.dataset.liveTheme = sessionSettings.theme_key || "aurora";
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
                    78,
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
        focusNicknameInput();
    }

    function focusNicknameInput() {
        if (!nicknameInput || document.activeElement === nicknameInput) return;
        if (resumePrompt && !resumePrompt.hidden) return;
        window.requestAnimationFrame(() => {
            nicknameInput.focus({ preventScroll: true });
            const valueLength = nicknameInput.value.length;
            try {
                nicknameInput.setSelectionRange(valueLength, valueLength);
            } catch (error) {
                // Some mobile browsers block selection APIs on unsupported input modes.
            }
        });
    }

    function continuePreviousPlayer() {
        closeResumePrompt();
        if (CONFIG.resumeUrl) {
            window.location.href = CONFIG.resumeUrl;
        }
    }

    function rerollAppearance() {
        if (!charactersEnabled) {
            selectedAvatar = defaultAvatar;
            selectedAccessory = defaultAccessory;
            return;
        }
        selectedAvatar = randomChoice(catalog.avatarKeys, defaultAvatar);
        selectedAccessory = randomChoice(accessoryChoices, defaultAccessory);
    }

    function shouldOfferResume(normalizedNickname) {
        if (!rememberedPlayer || allowFreshJoin) return false;
        return (
            normalizeNickname(rememberedPlayer.nickname) === normalizedNickname
        );
    }

    function closeThemeSocket() {
        if (themeReconnectTimer) {
            window.clearTimeout(themeReconnectTimer);
            themeReconnectTimer = null;
        }
        if (themeSocket) {
            themeSocket.onclose = null;
            themeSocket.close();
            themeSocket = null;
        }
    }

    function themeWsUrl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}/ws/live/${encodeURIComponent(CONFIG.pin)}/lobby/`;
    }

    function connectThemeSocket() {
        closeThemeSocket();
        if (!CONFIG.pin) return;

        themeSocket = new WebSocket(themeWsUrl());

        themeSocket.onopen = function () {
            themeReconnectAttempts = 0;
        };

        themeSocket.onmessage = function (event) {
            try {
                const message = JSON.parse(event.data);
                const payload = message.data || message;
                if ((payload.type === "lobby_state" || payload.type === "session_settings") && payload.settings) {
                    applySessionSettings(payload.settings);
                }
            } catch (error) {
                console.error("join theme sync parse error", error);
            }
        };

        themeSocket.onclose = function () {
            if (themeReconnectAttempts >= 8) return;
            themeReconnectAttempts += 1;
            themeReconnectTimer = window.setTimeout(connectThemeSocket, Math.min(1000 * themeReconnectAttempts, 5000));
        };
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

    applySessionSettings(sessionSettings);
    renderPreview();
    setStatus("");
    window.setTimeout(focusNicknameInput, 140);

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
        rerollAppearance();
        renderPreview();
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

    connectThemeSocket();
    window.addEventListener("beforeunload", closeThemeSocket);
});
