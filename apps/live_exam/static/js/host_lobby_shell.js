document.addEventListener("DOMContentLoaded", () => {
    const controller = window.LiveHostLobbyController;
    if (!controller) return;

    const presentationMode = Boolean(typeof CONFIG !== "undefined" && CONFIG.presentationOnly);
    const controlsEnabled = typeof CONFIG === "undefined" ? true : CONFIG.controlsEnabled !== false;

    const dom = {
        body: document.body,
        controlBar: document.getElementById("controlBar"),
        sidebarToggle: document.getElementById("sidebarToggle"),
        sidebarEdgeToggle: document.getElementById("sidebarEdgeToggle"),
        sidebarBackdrop: document.getElementById("hostSidebarBackdrop"),
        quickActions: document.getElementById("hostQuickActions"),
        quickStartBtn: document.getElementById("quickStartBtn"),
        quickFlowBtn: document.getElementById("quickFlowBtn"),
        quickLockBtn: document.getElementById("quickLockBtn"),
        settingsBtn: document.getElementById("settingsBtn"),
        fullscreenBtn: document.getElementById("fullscreenBtn"),
        lockLobbyBtn: document.getElementById("lockLobbyBtn"),
        drawer: document.getElementById("hostSettingsDrawer"),
        drawerBackdrop: document.getElementById("hostDrawerBackdrop"),
        closeSettingsBtn: document.getElementById("closeSettingsBtn"),
        playersList: document.getElementById("playersList"),
        autoMode: document.getElementById("autoMode"),
        maxParticipants: document.getElementById("maxParticipants"),
        sfxVolumeSlider: document.getElementById("sfxVolumeSlider"),
        sfxVolumeLabel: document.getElementById("sfxVolumeLabel"),
        themeButtons: Array.from(document.querySelectorAll("[data-theme-key]")),
        drawerBody: document.querySelector(".host-settings-drawer__body"),
    };

    if (!controlsEnabled || !dom.controlBar) return;

    const checkboxControls = [
        ["settingShowQuestionsOnDevices", "show_questions_on_devices"],
        ["settingCharactersEnabled", "characters_enabled"],
        ["settingIncreaseContrast", "increase_contrast"],
        ["settingReactionsEnabled", "reactions_enabled"],
        ["settingRandomizeQuestions", "randomize_questions"],
        ["settingRandomizeAnswers", "randomize_answers"],
        ["settingAutoplay", "autoplay"],
        ["settingQnaEnabled", "qna_enabled"],
        ["settingTeamSelectionEnabled", "team_selection_enabled"],
        ["settingTeamTalkEnabled", "team_talk_enabled"],
        ["settingNicknameGenerator", "nickname_generator"],
        ["settingTwoStepJoin", "two_step_join"],
    ].map(([id, key]) => [document.getElementById(id), key]).filter(([element]) => Boolean(element));

    const selectControls = [
        ["settingLanguage", "language"],
        ["settingLobbyMusic", "lobby_music"],
    ].map(([id, key]) => [document.getElementById(id), key]).filter(([element]) => Boolean(element));

    const copy = (() => {
        const lang = String((typeof CONFIG !== "undefined" ? CONFIG.languageCode : "az") || "az").slice(0, 2).toLowerCase();
        const labels = {
            az: {
                open: "Lobbi açıqdır",
                locked: "Lobbi kilidlidir",
                skip: "Keç",
                next: "Növbəti",
            },
            en: {
                open: "Lobby open",
                locked: "Lobby locked",
                skip: "Skip",
                next: "Next",
            },
            ru: {
                open: "Лобби открыто",
                locked: "Лобби закрыто",
                skip: "Пропустить",
                next: "Далее",
            },
            tr: {
                open: "Lobi açık",
                locked: "Lobi kilitli",
                skip: "Atla",
                next: "Sonraki",
            },
        };
        return labels[lang] || labels.az;
    })();

    let currentState = controller.getState();
    let syncingControls = false;
    let startPending = false;
    let flowPending = false;
    let pendingFlowState = "";
    let pendingFlowPhase = "";

    function syncSidebarButtons() {
        const expanded = presentationMode
            ? dom.body.classList.contains("presentation-sidebar-open")
            : !dom.body.classList.contains("sidebar-collapsed");

        dom.sidebarToggle?.setAttribute("aria-expanded", expanded ? "true" : "false");
        dom.sidebarEdgeToggle?.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function setCollapsed(collapsed) {
        if (presentationMode) return;
        dom.body.classList.toggle("sidebar-collapsed", Boolean(collapsed));
        syncSidebarButtons();
        try {
            window.localStorage.setItem("liveHostSidebarCollapsed", collapsed ? "1" : "0");
        } catch (error) {
            console.debug("live host sidebar state skipped", error);
        }
    }

    function setPresentationSidebarOpen(open) {
        if (!presentationMode) return;
        dom.body.classList.toggle("presentation-sidebar-open", Boolean(open));
        if (dom.sidebarBackdrop) {
            dom.sidebarBackdrop.hidden = !open;
        }
        syncSidebarButtons();
        try {
            window.localStorage.setItem("liveHostPresentationSidebarOpen", open ? "1" : "0");
        } catch (error) {
            console.debug("live host presentation sidebar state skipped", error);
        }
    }

    function toggleSidebar() {
        if (presentationMode) {
            setPresentationSidebarOpen(!dom.body.classList.contains("presentation-sidebar-open"));
            return;
        }
        setCollapsed(!dom.body.classList.contains("sidebar-collapsed"));
    }

    function setDrawerOpen(open) {
        dom.body.classList.toggle("host-settings-open", Boolean(open));
        if (dom.drawer) {
            dom.drawer.setAttribute("aria-hidden", open ? "false" : "true");
        }
        if (dom.drawerBackdrop) {
            dom.drawerBackdrop.hidden = !open;
        }
        if (open && dom.drawerBody) {
            window.requestAnimationFrame(() => {
                dom.drawerBody.scrollTop = 0;
            });
        }
    }

    function setLockButton(locked) {
        if (dom.lockLobbyBtn) {
            dom.lockLobbyBtn.classList.toggle("is-locked", Boolean(locked));
            dom.lockLobbyBtn.setAttribute("aria-pressed", locked ? "true" : "false");
            dom.lockLobbyBtn.innerHTML = `
                <i class="fas ${locked ? "fa-lock" : "fa-lock-open"}"></i>
                <span>${locked ? copy.locked : copy.open}</span>
            `;
        }
        if (dom.quickLockBtn) {
            dom.quickLockBtn.classList.toggle("is-locked", Boolean(locked));
            dom.quickLockBtn.setAttribute("aria-pressed", locked ? "true" : "false");
            dom.quickLockBtn.setAttribute("aria-label", locked ? copy.locked : copy.open);
            dom.quickLockBtn.setAttribute("title", locked ? copy.locked : copy.open);
            dom.quickLockBtn.innerHTML = `<i class="fas ${locked ? "fa-lock" : "fa-lock-open"}"></i>`;
        }
    }

    function syncUi(snapshot) {
        currentState = snapshot;
        if (snapshot.sessionState !== "lobby") {
            startPending = false;
        }
        if (
            flowPending
            && (snapshot.sessionState !== pendingFlowState || snapshot.phase !== pendingFlowPhase)
        ) {
            flowPending = false;
            pendingFlowState = "";
            pendingFlowPhase = "";
        }
        syncingControls = true;
        dom.body.dataset.liveTheme = snapshot.settings?.theme_key || "aurora";

        checkboxControls.forEach(([element, key]) => {
            element.checked = Boolean(snapshot.settings?.[key]);
        });

        selectControls.forEach(([element, key]) => {
            element.value = snapshot.settings?.[key] || element.value;
        });

        dom.themeButtons.forEach((button) => {
            const active = button.dataset.themeKey === (snapshot.settings?.theme_key || "aurora");
            button.classList.toggle("is-active", active);
        });

        if (dom.autoMode) {
            dom.autoMode.checked = Boolean(snapshot.settings?.autoplay);
        }
        if (dom.maxParticipants) {
            dom.maxParticipants.value = String(snapshot.settings?.max_participants || 100);
        }
        if (dom.sfxVolumeSlider && snapshot.settings?.sfx_volume != null) {
            const vol = Number(snapshot.settings.sfx_volume);
            dom.sfxVolumeSlider.value = vol;
            if (dom.sfxVolumeLabel) dom.sfxVolumeLabel.textContent = `${vol}%`;
            if (typeof setSfxVolume === "function") setSfxVolume(vol);
        }

        const showLobbyActions = snapshot.sessionState === "lobby";
        const showFlowAction = snapshot.sessionState === "question" || snapshot.sessionState === "reveal";

        if (dom.quickStartBtn) {
            dom.quickStartBtn.hidden = !showLobbyActions || startPending;
            dom.quickStartBtn.disabled = startPending;
            dom.quickStartBtn.style.display = !showLobbyActions || startPending ? "none" : "";
        }
        if (dom.quickLockBtn) {
            dom.quickLockBtn.hidden = !showLobbyActions;
            dom.quickLockBtn.style.display = showLobbyActions ? "" : "none";
        }
        if (dom.quickFlowBtn) {
            dom.quickFlowBtn.hidden = !showFlowAction;
            dom.quickFlowBtn.disabled = !showFlowAction || flowPending;
            dom.quickFlowBtn.style.display = showFlowAction ? "" : "none";
            const isQuestionFlow = snapshot.sessionState === "question";
            const flowLabel = isQuestionFlow ? copy.skip : copy.next;
            const flowIcon = isQuestionFlow ? "fa-forward-fast" : "fa-forward-step";
            dom.quickFlowBtn.setAttribute("aria-label", flowLabel);
            dom.quickFlowBtn.setAttribute("title", flowLabel);
            dom.quickFlowBtn.innerHTML = `<i class="fas ${flowIcon}"></i><span>${flowLabel}</span>`;
        }
        if (dom.quickActions) {
            dom.quickActions.hidden = !showLobbyActions && !showFlowAction;
            dom.quickActions.style.display = !showLobbyActions && !showFlowAction ? "none" : "";
        }

        setLockButton(snapshot.isLocked);
        syncingControls = false;
    }

    async function updateSettings(updates) {
        const result = await controller.updateSettings(updates);
        if (!result?.ok) {
            syncUi(controller.getState());
        }
        return result;
    }

    checkboxControls.forEach(([element, key]) => {
        element.addEventListener("change", () => {
            if (syncingControls) return;
            updateSettings({ [key]: Boolean(element.checked) });
        });
    });

    selectControls.forEach(([element, key]) => {
        element.addEventListener("change", () => {
            if (syncingControls) return;
            updateSettings({ [key]: element.value });
        });
    });

    if (dom.sfxVolumeSlider) {
        const initVol = Number(currentState.settings?.sfx_volume ?? 70);
        dom.sfxVolumeSlider.value = initVol;
        if (dom.sfxVolumeLabel) dom.sfxVolumeLabel.textContent = `${initVol}%`;
        if (typeof setSfxVolume === "function") setSfxVolume(initVol);

        dom.sfxVolumeSlider.addEventListener("input", () => {
            const vol = Number(dom.sfxVolumeSlider.value) || 0;
            if (dom.sfxVolumeLabel) dom.sfxVolumeLabel.textContent = `${vol}%`;
            if (typeof setSfxVolume === "function") setSfxVolume(vol);
        });
        dom.sfxVolumeSlider.addEventListener("change", () => {
            if (syncingControls) return;
            const vol = Number(dom.sfxVolumeSlider.value) || 0;
            updateSettings({ sfx_volume: vol });
        });
    }

    dom.themeButtons.forEach((button) => {
        button.addEventListener("click", () => {
            updateSettings({ theme_key: button.dataset.themeKey || "aurora" });
        });
    });

    dom.sidebarToggle?.addEventListener("click", toggleSidebar);
    dom.sidebarEdgeToggle?.addEventListener("click", toggleSidebar);
    dom.sidebarBackdrop?.addEventListener("click", () => setPresentationSidebarOpen(false));

    dom.settingsBtn?.addEventListener("click", () => setDrawerOpen(true));
    dom.closeSettingsBtn?.addEventListener("click", () => setDrawerOpen(false));
    dom.drawerBackdrop?.addEventListener("click", () => setDrawerOpen(false));
    dom.lockLobbyBtn?.addEventListener("click", () => controller.toggleLock(!currentState.isLocked));
    dom.quickLockBtn?.addEventListener("click", () => controller.toggleLock(!currentState.isLocked));
    dom.quickStartBtn?.addEventListener("click", async () => {
        if (startPending) return;
        startPending = true;
        syncUi(currentState);
        try {
            const result = await controller.startGame?.();
            if (!result?.ok) {
                startPending = false;
                syncUi(currentState);
            }
        } catch (error) {
            startPending = false;
            syncUi(currentState);
        }
    });
    dom.quickFlowBtn?.addEventListener("click", async () => {
        if (flowPending) return;
        const actionState = currentState.sessionState;
        if (actionState !== "question" && actionState !== "reveal") return;

        flowPending = true;
        pendingFlowState = actionState;
        pendingFlowPhase = currentState.phase || "";
        syncUi(currentState);

        try {
            const shouldSkipIntro = actionState === "question"
                && ["intro", "countdown", "question"].includes(currentState.phase);
            const result = shouldSkipIntro
                ? await controller.skipQuestionIntro?.()
                : actionState === "question"
                    ? await controller.revealQuestion?.()
                    : await controller.nextQuestion?.();
            if (!result?.ok) {
                flowPending = false;
                pendingFlowState = "";
                pendingFlowPhase = "";
                syncUi(currentState);
            }
        } catch (error) {
            flowPending = false;
            pendingFlowState = "";
            pendingFlowPhase = "";
            syncUi(currentState);
        }
    });
    dom.fullscreenBtn?.addEventListener("click", async () => {
        const root = document.documentElement;
        if (!root?.requestFullscreen) return;
        if (document.fullscreenElement) {
            document.exitFullscreen?.().catch?.(() => {});
            return;
        }
        try {
            await root.requestFullscreen({ navigationUI: "hide" });
        } catch (error) {
            console.debug("live host fullscreen skipped", error);
        }
    });

    dom.maxParticipants?.addEventListener("focus", function onFocus() {
        this.select();
    });
    dom.maxParticipants?.addEventListener("blur", () => {
        const cap = Number((typeof CONFIG !== "undefined" ? CONFIG.maxParticipantsCap : 100) || 100);
        let value = parseInt(dom.maxParticipants.value, 10) || 1;
        value = Math.max(1, Math.min(value, cap));
        dom.maxParticipants.value = String(value);
        if (!syncingControls) {
            updateSettings({ max_participants: value });
        }
    });
    dom.maxParticipants?.addEventListener("keydown", (event) => {
        if ([8, 46, 9, 27, 13, 37, 38, 39, 40].includes(event.keyCode)) return;
        if ((event.ctrlKey || event.metaKey) && [65, 67, 86, 88].includes(event.keyCode)) return;
        if ((event.keyCode >= 48 && event.keyCode <= 57) || (event.keyCode >= 96 && event.keyCode <= 105)) return;
        event.preventDefault();
    });

    dom.playersList?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-remove-player-id]");
        if (!button || currentState.sessionState !== "lobby") return;
        button.disabled = true;
        await controller.removePlayer(button.dataset.removePlayerId);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (dom.body.classList.contains("host-settings-open")) {
            setDrawerOpen(false);
            return;
        }
        if (presentationMode && dom.body.classList.contains("presentation-sidebar-open")) {
            setPresentationSidebarOpen(false);
        }
    });

    try {
        if (presentationMode) {
            setPresentationSidebarOpen(window.localStorage.getItem("liveHostPresentationSidebarOpen") === "1");
        } else {
            setCollapsed(window.localStorage.getItem("liveHostSidebarCollapsed") === "1");
        }
    } catch (error) {
        console.debug("live host sidebar state load skipped", error);
        syncSidebarButtons();
    }

    controller.subscribe(syncUi);
});
