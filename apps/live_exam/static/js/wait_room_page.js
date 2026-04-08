document.addEventListener("DOMContentLoaded", function () {
    const config = window.LiveWaitRoomConfig || {};
    const i18n = window.LIVE_EXAM_WAIT_ROOM_I18N || {};
    const tr = (key, fallback) => i18n[key] || fallback;
    const STATE_POLL_INTERVAL_MS = 2500;

    const state = {
        myPlayer: config.myPlayer || {},
        players: [],
        sessionSettings: Object.assign({}, config.sessionSettings || {}),
        socket: null,
        reconnectTimer: null,
        reconnectAttempts: 0,
        pollTimer: null,
        activePanel: "avatar"
    };

    const dom = {
        heroAvatar: document.getElementById("waitRoomHeroAvatar"),
        heroNickname: document.getElementById("waitRoomHeroNickname"),
        footerAvatar: document.getElementById("waitRoomFooterAvatar"),
        footerNickname: document.getElementById("waitRoomFooterNickname"),
        footerCount: document.getElementById("waitRoomPlayersCount"),
        wsStatus: document.getElementById("waitRoomWsStatus"),
        editButton: document.getElementById("waitRoomEditButton"),
        modal: document.getElementById("waitRoomEditModal"),
        modalBackdrop: document.getElementById("waitRoomModalBackdrop"),
        modalCloseButtons: document.querySelectorAll("[data-wait-room-close]"),
        nicknameInput: document.getElementById("waitRoomNicknameInput"),
        nicknameError: document.getElementById("waitRoomNicknameError"),
        saveButton: document.getElementById("waitRoomSaveButton"),
        preview: document.getElementById("waitRoomPreview"),
        avatarGrid: document.getElementById("waitRoomAvatarGrid"),
        accessoryGrid: document.getElementById("waitRoomAccessoryGrid"),
        appearanceSection: document.getElementById("waitRoomAppearanceSection"),
        panelButtons: document.querySelectorAll("[data-wait-room-panel-target]"),
        pickerPanels: document.querySelectorAll("[data-wait-room-panel]"),
        reactionRoot: document.getElementById("waitRoomReactionDock"),
        reactionList: document.getElementById("waitRoomReactionList"),
        reactionFab: document.getElementById("waitRoomReactionFab"),
        reactionOverlay: document.getElementById("waitRoomReactionOverlay"),
        feedback: document.getElementById("waitRoomFeedback")
    };

    const initialData = document.getElementById("initialPlayers");
    if (initialData) {
        try {
            state.players = JSON.parse(initialData.textContent || "[]");
        } catch (error) {
            console.error("wait room initial players parse error", error);
        }
    }

    const avatarPicker = new window.LiveWaitRoomAvatarPicker(dom.avatarGrid, {
        value: state.myPlayer.avatar_key,
        previewAccessoryKey: state.myPlayer.accessory_key,
        onChange: function () {
            renderEditPreview();
        }
    });
    const accessoryPicker = new window.LiveWaitRoomAccessoryPicker(dom.accessoryGrid, {
        value: state.myPlayer.accessory_key,
        onChange: function (value) {
            avatarPicker.setPreviewAccessoryKey(value);
            renderEditPreview();
        }
    });
    const reactionPanel = new window.LiveWaitRoomReactionPanel({
        root: dom.reactionRoot,
        list: dom.reactionList,
        fab: dom.reactionFab,
        overlay: dom.reactionOverlay,
        cooldownMs: 900,
        onSend: sendReaction
    });

    avatarPicker.render();
    accessoryPicker.render();
    reactionPanel.init();

    function applySessionSettings(nextSettings) {
        state.sessionSettings = Object.assign({}, state.sessionSettings, nextSettings || {});
        const charactersEnabled = state.sessionSettings.characters_enabled !== false;
        const reactionsEnabled = state.sessionSettings.reactions_enabled !== false;
        document.body.dataset.liveTheme = state.sessionSettings.theme_key || "aurora";

        if (dom.reactionRoot) {
            dom.reactionRoot.hidden = !reactionsEnabled;
        }

        if (dom.appearanceSection) {
            dom.appearanceSection.hidden = !charactersEnabled;
        }

        if (!charactersEnabled) {
            setActivePanel("avatar");
        }
    }

    function setFeedback(message, kind) {
        if (!dom.feedback) return;
        dom.feedback.textContent = message || "";
        dom.feedback.className = "wait-room-feedback" + (kind ? ` is-${kind}` : "");
    }

    function renderHero() {
        if (dom.heroAvatar) {
            dom.heroAvatar.innerHTML = window.LiveAvatarRenderer.renderAvatarMarkup(state.myPlayer, {
                size: 128,
                className: "wait-room-hero__avatar-frame"
            });
        }
        if (dom.heroNickname) {
            dom.heroNickname.textContent = state.myPlayer.nickname || tr("defaultPlayer", "Player");
        }
        if (dom.footerAvatar) {
            dom.footerAvatar.innerHTML = window.LiveAvatarRenderer.renderAvatarMarkup(state.myPlayer, {
                size: 54,
                className: "wait-room-footer__avatar-frame",
                interactive: false
            });
        }
        if (dom.footerNickname) {
            dom.footerNickname.textContent = state.myPlayer.nickname || tr("defaultPlayer", "Player");
        }
    }

    function renderPlayers(players, totalCount) {
        state.players = Array.isArray(players) ? players : [];
        const expectedTotal = Number.isFinite(Number(totalCount)) ? Number(totalCount) : state.players.length;
        const me = state.players.find(function (player) {
            return Number(player?.id) === Number(state.myPlayer?.id);
        });
        if (!me && expectedTotal <= state.players.length) {
            setFeedback(tr("removedFromLobby", "You were removed from the lobby."), "error");
            window.setTimeout(function () {
                window.location.replace(config.joinPageUrl || window.location.href);
            }, 450);
            return;
        }
        if (me) {
            state.myPlayer = Object.assign({}, state.myPlayer, me);
            renderHero();
        }
        if (dom.footerCount) {
            const otherPlayersCount = Math.max(expectedTotal - 1, 0);
            dom.footerCount.textContent = String(Math.max(otherPlayersCount, 0));
        }
    }

    function renderEditPreview() {
        const nicknameState = window.LiveWaitRoomNicknameEditor.validateNickname(dom.nicknameInput.value, {
            required: tr("nicknameRequired", "Nickname is required."),
            tooLong: tr("nicknameTooLong", "Nickname is too long.")
        });
        const previewPlayer = {
            nickname: nicknameState.value || state.myPlayer.nickname,
            avatar_key: avatarPicker.value,
            accessory_key: accessoryPicker.value
        };
        if (dom.preview) {
            dom.preview.innerHTML = window.LiveAvatarRenderer.renderAvatarMarkup(previewPlayer, {
                size: 104,
                className: "wait-room-preview__avatar"
            });
        }
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function setWsStatus(kind, message) {
        if (!dom.wsStatus) return;
        dom.wsStatus.className = `wait-room-topbar__status is-${kind}`;
        dom.wsStatus.querySelector("[data-wait-room-status-label]").textContent = message;
    }

    function setActivePanel(panelKey) {
        state.activePanel = panelKey === "accessory" ? "accessory" : "avatar";
        dom.panelButtons.forEach(function (button) {
            const active = button.dataset.waitRoomPanelTarget === state.activePanel;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
        });
        dom.pickerPanels.forEach(function (panel) {
            const active = panel.dataset.waitRoomPanel === state.activePanel;
            panel.classList.toggle("is-active", active);
            panel.hidden = !active;
        });
    }

    function openModal() {
        dom.modal?.classList.add("is-open");
        dom.modalBackdrop?.classList.add("is-open");
        document.body.classList.add("wait-room-modal-open");
        dom.nicknameInput.value = state.myPlayer.nickname || "";
        dom.nicknameError.textContent = "";
        avatarPicker.setValue(state.myPlayer.avatar_key || window.LiveAvatarCatalog.defaultAvatarKey);
        accessoryPicker.setValue(state.myPlayer.accessory_key || window.LiveAvatarCatalog.defaultAccessoryKey);
        avatarPicker.setPreviewAccessoryKey(accessoryPicker.value);
        renderEditPreview();
        setActivePanel("avatar");
        setFeedback("", "");
        window.setTimeout(function () {
            dom.nicknameInput?.focus();
            dom.nicknameInput?.select();
        }, 80);
    }

    function closeModal() {
        dom.modal?.classList.remove("is-open");
        dom.modalBackdrop?.classList.remove("is-open");
        document.body.classList.remove("wait-room-modal-open");
    }

    async function saveProfile() {
        const validation = window.LiveWaitRoomNicknameEditor.validateNickname(dom.nicknameInput.value, {
            required: tr("nicknameRequired", "Nickname is required."),
            tooLong: tr("nicknameTooLong", "Nickname is too long.")
        });
        dom.nicknameInput.value = validation.value;
        dom.nicknameError.textContent = validation.message || "";
        if (!validation.valid) return;

        dom.saveButton.disabled = true;
        setFeedback(tr("saving", "Saving changes..."), "muted");

        try {
            const body = new FormData();
            body.append("nickname", validation.value);
            body.append("avatar_key", avatarPicker.value);
            body.append("accessory_key", accessoryPicker.value);

            const response = await fetch(config.profileUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": config.csrf
                },
                body: body
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.message || tr("saveFailed", "Unable to save right now."));
            }

            state.myPlayer = data.player;
            renderHero();
            renderEditPreview();
            setFeedback(tr("saved", "Saved"), "success");
            window.setTimeout(closeModal, 280);
        } catch (error) {
            dom.nicknameError.textContent = error.message || tr("saveFailed", "Unable to save right now.");
            setFeedback("", "");
        } finally {
            dom.saveButton.disabled = false;
        }
    }

    async function sendReaction(reactionKey) {
        try {
            setFeedback("", "");
            const body = new FormData();
            body.append("reaction_key", reactionKey);
            const response = await fetch(config.reactionUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": config.csrf
                },
                body: body
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                if (response.status === 429) {
                    const retryAfter = Number(response.headers.get("Retry-After") || 0);
                    if (retryAfter > 0) {
                        reactionPanel.setCooldown(retryAfter * 1000);
                    }
                }
                throw new Error(data.message || tr("reactionFailed", "Reaction could not be sent."));
            }
        } catch (error) {
            setFeedback(error.message || tr("reactionFailed", "Reaction could not be sent."), "error");
        }
    }

    function getWsUrl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}${config.wsPath}`;
    }

    async function syncLobbyState() {
        if (!config.stateUrl) return null;
        try {
            const response = await fetch(config.stateUrl, {
                headers: { Accept: "application/json" }
            });
            if (!response.ok) {
                return null;
            }
            const snapshot = await response.json();
            if (!snapshot || !snapshot.ok) {
                return null;
            }
            applySessionSettings(snapshot.settings);
            if (snapshot.state && snapshot.state !== "lobby") {
                window.location.href = config.playerScreenUrl;
                return snapshot;
            }
            state.players = Array.isArray(snapshot.players) ? snapshot.players : state.players;
            renderPlayers(state.players, snapshot.total_players || state.players.length);
            return snapshot;
        } catch (error) {
            console.error("wait room state sync failed", error);
            return null;
        }
    }

    function stopStatePolling() {
        if (state.pollTimer) {
            window.clearInterval(state.pollTimer);
            state.pollTimer = null;
        }
    }

    function startStatePolling() {
        if (state.pollTimer) return;
        state.pollTimer = window.setInterval(function () {
            if (!document.hidden) {
                syncLobbyState();
            }
        }, STATE_POLL_INTERVAL_MS);
    }

    function connectWebSocket() {
        if (state.reconnectTimer) {
            window.clearTimeout(state.reconnectTimer);
            state.reconnectTimer = null;
        }

        setWsStatus("connecting", tr("wsConnecting", "Connecting"));
        state.socket = new WebSocket(getWsUrl());

        state.socket.onopen = function () {
            state.reconnectAttempts = 0;
            setWsStatus("online", tr("wsOnline", "Online"));
        };

        state.socket.onmessage = function (event) {
            try {
                const message = JSON.parse(event.data);
                const payload = message.data || message;
                if (payload.type === "game_started" && payload.redirect) {
                    setWsStatus("online", tr("wsStarting", "Starting"));
                    window.location.href = payload.redirect;
                    return;
                }
                if (payload.type === "lobby_state") {
                    applySessionSettings(payload.settings);
                    state.players = Array.isArray(payload.players) ? payload.players : [];
                    renderPlayers(state.players, payload.count);
                    return;
                }
                if (payload.type === "session_settings" && payload.settings) {
                    applySessionSettings(payload.settings);
                    return;
                }
                if (payload.type === "reaction_event") {
                    reactionPanel.spawn(payload);
                }
            } catch (error) {
                console.error("wait room message parse error", error);
            }
        };

        state.socket.onerror = function () {
            setWsStatus("offline", tr("wsError", "Error"));
        };

        state.socket.onclose = function () {
            setWsStatus("offline", tr("wsDisconnected", "Disconnected"));
            if (state.reconnectAttempts >= 10) return;
            state.reconnectAttempts += 1;
            const delay = Math.min(1000 * state.reconnectAttempts, 5000);
            state.reconnectTimer = window.setTimeout(connectWebSocket, delay);
        };
    }

    applySessionSettings(state.sessionSettings);
    renderHero();
    renderPlayers(state.players, state.players.length);
    dom.editButton?.addEventListener("click", openModal);
    dom.modalCloseButtons.forEach(function (button) {
        button.addEventListener("click", closeModal);
    });
    dom.modalBackdrop?.addEventListener("click", closeModal);
    dom.nicknameInput?.addEventListener("input", function () {
        dom.nicknameError.textContent = "";
        renderEditPreview();
    });
    dom.saveButton?.addEventListener("click", saveProfile);
    dom.panelButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            setActivePanel(button.dataset.waitRoomPanelTarget);
        });
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeModal();
    });

    connectWebSocket();
    syncLobbyState();
    startStatePolling();
    window.addEventListener("beforeunload", function () {
        stopStatePolling();
        if (state.reconnectTimer) {
            window.clearTimeout(state.reconnectTimer);
            state.reconnectTimer = null;
        }
        if (state.socket) state.socket.close();
    });
});
