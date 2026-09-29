/* host_lobby_shell.js — aparıcının idarə «qabığı»: sol panel, tənzimləmə çekməcəsi,
 * sürətli düymələr (Başla / Keç / Növbəti / Kilid). KLASSİK skript; host_lobby.entry.js
 * modulu (window.LiveHostLobbyController, window.LiveHostIcons) ondan ƏVVƏL işləyir.
 * 2026-09-29 (LX-FE-STAGE): Font Awesome → xüsusi SVG; native <select> → seqment
 * düymələri (data-setting-choice); mətnlər LIVE_EXAM_HOST_I18N-dən (gettext yox).
 */
document.addEventListener("DOMContentLoaded", () => {
    const controller = window.LiveHostLobbyController;
    if (!controller) return;

    const presentationMode = Boolean(typeof CONFIG !== "undefined" && CONFIG.presentationOnly);
    const controlsEnabled = typeof CONFIG === "undefined" ? true : CONFIG.controlsEnabled !== false;
    const I18N = window.LIVE_EXAM_HOST_I18N || {};
    const tr = (key, fallback) => {
        const value = I18N[key];
        return value && !/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(value) ? value : fallback;
    };
    const icons = window.LiveHostIcons || { icon: () => "" };
    const icon = (name) => icons.icon(name);

    const dom = {
        body: document.body,
        controlBar: document.getElementById("controlBar"),
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
        autoMode: document.getElementById("autoMode"),
        maxParticipants: document.getElementById("maxParticipants"),
        sfxVolumeSlider: document.getElementById("sfxVolumeSlider"),
        sfxVolumeLabel: document.getElementById("sfxVolumeLabel"),
        themeButtons: Array.from(document.querySelectorAll("[data-theme-key]")),
        choiceGroups: Array.from(document.querySelectorAll("[data-setting-choice]")),
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

    const copy = {
        open: tr("lobbyOpenLabel", "Lobbi açıqdır"),
        locked: tr("lobbyLockedLabel", "Lobbi bağlıdır"),
        skip: tr("skipLabel", "Keç"),
        next: tr("nextLabel", "Növbəti"),
    };

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
        dom.sidebarEdgeToggle?.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function remember(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (error) {
            /* yaddaş əlçatmazdır — vəziyyət yalnız bu səhifədə qalır */
        }
    }

    function setCollapsed(collapsed) {
        if (presentationMode) return;
        dom.body.classList.toggle("sidebar-collapsed", Boolean(collapsed));
        syncSidebarButtons();
        remember("liveHostSidebarCollapsed", collapsed ? "1" : "0");
    }

    function setPresentationSidebarOpen(open) {
        if (!presentationMode) return;
        dom.body.classList.toggle("presentation-sidebar-open", Boolean(open));
        if (dom.sidebarBackdrop) dom.sidebarBackdrop.hidden = !open;
        syncSidebarButtons();
        remember("liveHostPresentationSidebarOpen", open ? "1" : "0");
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
        if (dom.drawer) dom.drawer.setAttribute("aria-hidden", open ? "false" : "true");
        if (dom.drawerBackdrop) dom.drawerBackdrop.hidden = !open;
        if (open && dom.drawerBody) {
            window.requestAnimationFrame(() => {
                dom.drawerBody.scrollTop = 0;
                dom.closeSettingsBtn?.focus();
            });
        }
    }

    function setLockButton(locked) {
        const label = locked ? copy.locked : copy.open;
        if (dom.lockLobbyBtn) {
            dom.lockLobbyBtn.classList.toggle("is-locked", Boolean(locked));
            dom.lockLobbyBtn.setAttribute("aria-pressed", locked ? "true" : "false");
            dom.lockLobbyBtn.innerHTML = `<span class="hx-i">${icon(locked ? "lock" : "unlock")}</span><span>${label}</span>`;
        }
        if (dom.quickLockBtn) {
            dom.quickLockBtn.classList.toggle("is-locked", Boolean(locked));
            dom.quickLockBtn.setAttribute("aria-pressed", locked ? "true" : "false");
            dom.quickLockBtn.setAttribute("aria-label", label);
            dom.quickLockBtn.setAttribute("title", label);
            dom.quickLockBtn.innerHTML = `<span class="hx-i">${icon(locked ? "lock" : "unlock")}</span>`;
        }
    }

    function showQuick(element, visible) {
        if (!element) return;
        element.hidden = !visible;
    }

    function syncUi(snapshot) {
        currentState = snapshot;
        if (snapshot.sessionState !== "lobby") startPending = false;
        if (flowPending && (snapshot.sessionState !== pendingFlowState || snapshot.phase !== pendingFlowPhase)) {
            flowPending = false;
            pendingFlowState = "";
            pendingFlowPhase = "";
        }
        syncingControls = true;
        dom.body.dataset.liveTheme = snapshot.settings?.theme_key || "aurora";

        checkboxControls.forEach(([element, key]) => {
            element.checked = Boolean(snapshot.settings?.[key]);
        });
        dom.choiceGroups.forEach((group) => {
            const key = group.dataset.settingChoice;
            const value = String(snapshot.settings?.[key] ?? "");
            group.querySelectorAll("[data-value]").forEach((button) => {
                const active = button.dataset.value === value;
                button.setAttribute("aria-checked", active ? "true" : "false");
                button.tabIndex = active || (!value && button === group.firstElementChild) ? 0 : -1;
            });
        });
        dom.themeButtons.forEach((button) => {
            const active = button.dataset.themeKey === (snapshot.settings?.theme_key || "aurora");
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (dom.autoMode) dom.autoMode.checked = Boolean(snapshot.settings?.autoplay);
        if (dom.maxParticipants && document.activeElement !== dom.maxParticipants) {
            dom.maxParticipants.value = String(snapshot.settings?.max_participants || 200);
        }

        const inLobby = snapshot.sessionState === "lobby";
        const inFlow = snapshot.sessionState === "question" || snapshot.sessionState === "reveal";
        showQuick(dom.quickStartBtn, inLobby && !startPending);
        if (dom.quickStartBtn) dom.quickStartBtn.disabled = startPending;
        showQuick(dom.quickLockBtn, inLobby);
        showQuick(dom.quickFlowBtn, inFlow);
        if (dom.quickFlowBtn) {
            const isQuestion = snapshot.sessionState === "question";
            const intro = isQuestion && ["intro", "countdown", "question"].includes(snapshot.phase);
            const label = intro ? copy.skip : isQuestion ? tr("revealLabel", "Cavabı göstər") : copy.next;
            dom.quickFlowBtn.disabled = !inFlow || flowPending;
            dom.quickFlowBtn.setAttribute("aria-label", label);
            dom.quickFlowBtn.setAttribute("title", label);
            dom.quickFlowBtn.innerHTML = `<span class="hx-i">${icon(intro ? "skip" : isQuestion ? "eye" : "next")}</span><span>${label}</span>`;
        }
        if (dom.quickActions) dom.quickActions.hidden = !inLobby && !inFlow;

        setLockButton(snapshot.isLocked);
        syncingControls = false;
    }

    async function updateSettings(updates) {
        const result = await controller.updateSettings(updates);
        if (!result?.ok) syncUi(controller.getState());
        return result;
    }

    checkboxControls.forEach(([element, key]) => {
        element.addEventListener("change", () => {
            if (syncingControls) return;
            updateSettings({ [key]: Boolean(element.checked) });
        });
    });

    dom.choiceGroups.forEach((group) => {
        const key = group.dataset.settingChoice;
        const buttons = () => Array.from(group.querySelectorAll("[data-value]"));
        group.addEventListener("click", (event) => {
            const button = event.target.closest("[data-value]");
            if (!button || syncingControls) return;
            buttons().forEach((item) => item.setAttribute("aria-checked", item === button ? "true" : "false"));
            updateSettings({ [key]: button.dataset.value });
        });
        group.addEventListener("keydown", (event) => {
            if (!["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(event.key)) return;
            event.preventDefault();
            const list = buttons();
            const index = list.indexOf(document.activeElement);
            const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
            const next = list[(index + step + list.length) % list.length];
            next?.focus();
            next?.click();
        });
    });

    if (dom.sfxVolumeSlider) {
        const initVol = Number(currentState.settings?.sfx_volume ?? 70);
        dom.sfxVolumeSlider.value = initVol;
        if (dom.sfxVolumeLabel) dom.sfxVolumeLabel.textContent = `${initVol}%`;
        dom.sfxVolumeSlider.addEventListener("input", () => {
            const vol = Number(dom.sfxVolumeSlider.value) || 0;
            if (dom.sfxVolumeLabel) dom.sfxVolumeLabel.textContent = `${vol}%`;
            if (typeof window.setSfxVolume === "function") window.setSfxVolume(vol);
        });
        dom.sfxVolumeSlider.addEventListener("change", () => {
            if (syncingControls) return;
            updateSettings({ sfx_volume: Number(dom.sfxVolumeSlider.value) || 0 });
        });
    }

    dom.themeButtons.forEach((button) => {
        button.addEventListener("click", () => updateSettings({ theme_key: button.dataset.themeKey || "aurora" }));
    });

    dom.sidebarEdgeToggle?.addEventListener("click", toggleSidebar);
    dom.sidebarBackdrop?.addEventListener("click", () => setPresentationSidebarOpen(false));
    dom.settingsBtn?.addEventListener("click", () => setDrawerOpen(true));
    dom.closeSettingsBtn?.addEventListener("click", () => {
        setDrawerOpen(false);
        dom.settingsBtn?.focus();
    });
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
            const skipIntro = actionState === "question" && ["intro", "countdown", "question"].includes(currentState.phase);
            const result = skipIntro
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
            /* brauzer tam ekranı rədd etdi */
        }
    });

    dom.maxParticipants?.addEventListener("focus", function onFocus() {
        this.select();
    });
    dom.maxParticipants?.addEventListener("blur", () => {
        const cap = Number((typeof CONFIG !== "undefined" ? CONFIG.maxParticipantsCap : 200) || 200);
        let value = parseInt(dom.maxParticipants.value, 10) || 1;
        value = Math.max(1, Math.min(value, cap));
        dom.maxParticipants.value = String(value);
        if (!syncingControls) updateSettings({ max_participants: value });
    });
    dom.maxParticipants?.addEventListener("keydown", (event) => {
        if (["Backspace", "Delete", "Tab", "Escape", "Enter", "ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        if ((event.ctrlKey || event.metaKey) && ["a", "c", "v", "x"].includes(String(event.key).toLowerCase())) return;
        if (/^\d$/.test(event.key)) return;
        event.preventDefault();
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
        syncSidebarButtons();
    }

    controller.subscribe(syncUi);
});
