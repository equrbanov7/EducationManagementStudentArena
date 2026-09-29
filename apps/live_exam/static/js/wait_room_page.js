/* wait_room_page.js — canlı oyunun gözləmə otağı (LX-FE-PLAYER 2026-09-29).
 *
 * Nə edir:
 *  • lobby WebSocket-i avtomatik yenidən qoşulma ilə (0.8 → 10 s, jitter); WS bağlıdırsa hər 3 s,
 *    açıqdırsa hər 12 s «təhlükəsizlik» snapshot-u (qaçırılmış `game_started` də tutulur);
 *  • `kicked` mesajı / snapshot 403 → «müəllim səni çıxardı» kartı, bütün taymerlər dayanır;
 *  • lobbi kilidlənəndə ad sahəsi bağlanır (server qaydası: ad yalnız açıq lobbidə dəyişir);
 *  • oyun başlayanda «Oyun başlayır!» örtüyü və oyun ekranına keçid;
 *  • reaksiyalar yalnız lobbidə; 429 → sakit soyuma (Retry-After).
 * AJAX-safe: EMSReady + idempotent qoruyucu (data-lx-init).
 */
(function () {
    "use strict";

    function init() {
        const shell = document.querySelector(".lxw-shell");
        if (!shell || shell.dataset.lxInit) return;
        shell.dataset.lxInit = "1";

        const config = window.LiveWaitRoomConfig || {};
        const i18n = window.LIVE_EXAM_WAIT_ROOM_I18N || {};
        const catalog = window.LiveAvatarCatalog || {};
        const renderer = window.LiveAvatarRenderer;
        const nicknameTools = window.LiveWaitRoomNicknameEditor || {};
        const UNTRANSLATED = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;

        const tr = (key, fallback) => {
            const value = i18n[key];
            if (typeof value !== "string" || !value.trim() || UNTRANSLATED.test(value.trim())) return fallback;
            return value;
        };
        const fmt = (template, values) =>
            String(template).replace(/\{(\w+)\}/g, (match, key) =>
                Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
            );

        const AZ_ACCESSORY = {
            accessory_none: "Yoxdur", glasses: "Eynək", cap: "Papaq", crown: "Tac", mask: "Maska",
            sparkles: "Parıltı", bowtie: "Kəpənək qalstuk", headphones: "Qulaqlıq", flower: "Gül",
            pirate_patch: "Pirat sarğısı", halo: "Halə",
        };
        const AZ_AVATAR = {
            avatar_1: "Tülkü", avatar_2: "Panda", avatar_3: "Şir", avatar_4: "Pələng", avatar_5: "Koala",
            avatar_6: "Donuz balası", avatar_7: "Qurbağa", avatar_8: "Səkkizayaq", avatar_9: "Meymun",
            avatar_10: "Təkbuynuz", avatar_11: "Dovşan", avatar_12: "Hamster", avatar_13: "Canavar",
            avatar_14: "Ağ ayı", avatar_15: "Qırmızı panda", avatar_16: "Nanə dovşanı",
        };
        const accessoryLabels = {};
        (catalog.accessoryKeys || []).forEach((key) => {
            accessoryLabels[key] = tr(`acc:${key}`, AZ_ACCESSORY[key] || key);
        });
        const avatarLabels = {};
        (catalog.avatarKeys || []).forEach((key) => {
            avatarLabels[key] = tr(`ava:${key}`, AZ_AVATAR[key] || key);
        });

        const $ = (id) => document.getElementById(id);
        const dom = {
            heroAvatar: $("waitRoomHeroAvatar"),
            heroName: $("waitRoomHeroNickname"),
            status: $("waitRoomStatusText"),
            count: $("waitRoomPlayersCount"),
            lockedChip: $("waitRoomLockedChip"),
            lockedText: $("waitRoomLockedText"),
            net: $("waitRoomNet"),
            feedback: $("waitRoomFeedback"),
            sheet: $("waitRoomEditModal"),
            backdrop: $("waitRoomModalBackdrop"),
            nickInput: $("waitRoomNicknameInput"),
            nickCount: $("waitRoomNicknameCount"),
            nickHint: $("waitRoomNicknameHint"),
            nickError: $("waitRoomNicknameError"),
            saveButton: $("waitRoomSaveButton"),
            preview: $("waitRoomPreview"),
            appearance: $("waitRoomAppearanceSection"),
            avatarPanel: $("waitRoomAvatarPanel"),
            accessoryPanel: $("waitRoomAccessoryPanel"),
            reactionDock: $("waitRoomReactionDock"),
            kicked: $("waitRoomKicked"),
            starting: $("waitRoomStarting"),
        };

        const state = {
            me: Object.assign({}, config.myPlayer || {}),
            settings: Object.assign({}, config.sessionSettings || {}),
            locked: Boolean(config.isLocked),
            socket: null,
            attempts: 0,
            retryTimer: null,
            pollTimer: null,
            lastSync: 0,
            done: false,
            lastFocus: null,
            feedbackTimer: null,
            netTimer: null,
            netShown: "",
            danceTimer: null,
            reactionWarnAt: 0,
        };

        // ── Göstərmə ────────────────────────────────────────────────────────
        function avatar(profile, size, opts) {
            if (!renderer) return "";
            return renderer.renderAvatarMarkup(profile || {}, Object.assign({ size, interactive: false }, opts || {}));
        }

        function renderHero(dance) {
            if (dom.heroAvatar) {
                dom.heroAvatar.innerHTML = avatar(state.me, 150, {
                    crop: "full",
                    className: "lxw-hero__art",
                    dance: dance || "idle",
                });
            }
            if (dom.heroName) dom.heroName.textContent = state.me.nickname || tr("defaultPlayer", "Oyunçu");
        }

        function celebrate(dance, ms) {
            renderHero(dance);
            window.clearTimeout(state.danceTimer);
            state.danceTimer = window.setTimeout(() => renderHero("idle"), ms || 1800);
        }

        function showFeedback(message, kind) {
            if (!dom.feedback || !message) return;
            dom.feedback.textContent = message;
            dom.feedback.dataset.kind = kind || "info";
            dom.feedback.hidden = false;
            dom.feedback.classList.remove("is-visible");
            void dom.feedback.offsetWidth;
            dom.feedback.classList.add("is-visible");
            window.clearTimeout(state.feedbackTimer);
            state.feedbackTimer = window.setTimeout(() => {
                dom.feedback.classList.remove("is-visible");
                state.feedbackTimer = window.setTimeout(() => {
                    dom.feedback.hidden = true;
                }, 260);
            }, 2600);
        }

        function setNet(kind) {
            if (!dom.net) return;
            window.clearTimeout(state.netTimer);
            if (kind === "online") {
                if (!state.netShown) return;
                state.netShown = "";
                dom.net.dataset.kind = "back";
                dom.net.textContent = tr("netBack", "Yenidən onlayn!");
                state.netTimer = window.setTimeout(() => {
                    dom.net.hidden = true;
                }, 1500);
                return;
            }
            const show = () => {
                state.netShown = kind;
                dom.net.dataset.kind = kind;
                dom.net.textContent =
                    kind === "offline"
                        ? tr("netOffline", "İnternet yoxdur — bağlantı gözlənilir")
                        : tr("netReconnecting", "Bağlantı bərpa olunur…");
                dom.net.hidden = false;
            };
            if (state.netShown || kind === "offline") show();
            else state.netTimer = window.setTimeout(show, 1500);
        }

        function renderCount(total) {
            if (!dom.count) return;
            const count = Math.max(1, Number(total) || 1);
            dom.count.textContent =
                count <= 1
                    ? tr("playersAlone", "Hələlik yalnız sənsən")
                    : fmt(tr("playersCount", "{count} oyunçu qoşulub"), { count });
        }

        function setLocked(locked) {
            state.locked = Boolean(locked);
            if (dom.lockedChip) dom.lockedChip.hidden = !state.locked;
            if (dom.lockedText) dom.lockedText.textContent = tr("lockedBadge", "Lobbi bağlanıb — oyun tezliklə başlayır");
            if (dom.nickInput) {
                dom.nickInput.disabled = state.locked;
                if (dom.nickHint) {
                    dom.nickHint.hidden = !state.locked;
                    dom.nickHint.textContent = tr(
                        "nicknameLockedHint",
                        "Lobbi bağlıdır — ad artıq dəyişmir, avatarı dəyişə bilərsən."
                    );
                }
            }
        }

        function applySettings(next) {
            state.settings = Object.assign({}, state.settings, next || {});
            document.body.dataset.liveTheme = state.settings.theme_key || "aurora";
            reactions.setEnabled(state.settings.reactions_enabled !== false && !state.done);
            const characters = state.settings.characters_enabled !== false;
            if (dom.appearance) dom.appearance.hidden = !characters;
            if (dom.avatarPanel && !characters) dom.avatarPanel.hidden = true;
            if (dom.accessoryPanel && !characters) dom.accessoryPanel.hidden = true;
        }

        function renderPlayers(players, total) {
            const list = Array.isArray(players) ? players : [];
            const count = Number.isFinite(Number(total)) ? Number(total) : list.length;
            const me = list.find((player) => Number(player && player.id) === Number(state.me.id));
            if (me) {
                const changed =
                    me.nickname !== state.me.nickname ||
                    me.avatar_key !== state.me.avatar_key ||
                    me.accessory_key !== state.me.accessory_key;
                state.me = Object.assign({}, state.me, me);
                if (changed) renderHero();
            } else if (list.length && list.length >= count) {
                // Tam siyahıda yoxuq — çox güman çıxarılmışıq; serverdən təsdiq alırıq (403).
                syncState();
            }
            renderCount(count);
        }

        // ── Son vəziyyətlər ─────────────────────────────────────────────────
        function stopAll() {
            state.done = true;
            window.clearTimeout(state.retryTimer);
            window.clearInterval(state.pollTimer);
            state.pollTimer = null;
            if (state.socket) {
                state.socket.onclose = null;
                try {
                    state.socket.close();
                } catch (error) {
                    // bağlıdır
                }
                state.socket = null;
            }
            reactions.setEnabled(false);
        }

        function showKicked() {
            if (state.done && dom.kicked && !dom.kicked.hidden) return;
            stopAll();
            closeSheet();
            if (!dom.kicked) return;
            $("waitRoomKickedTitle").textContent = tr("kickedTitle", "Müəllim səni oyundan çıxardı");
            $("waitRoomKickedBody").textContent = tr(
                "kickedBody",
                "Bu cihazla bu oyuna yenidən qoşulmaq mümkün deyil. Səhv olubsa, müəllimə yaz."
            );
            const action = $("waitRoomKickedAction");
            action.textContent = tr("kickedAction", "Başqa PIN daxil et");
            if (config.pinEntryUrl) action.href = config.pinEntryUrl;
            dom.kicked.hidden = false;
            window.setTimeout(() => action.focus(), 60);
        }

        function goToGame(url) {
            if (state.done) return;
            stopAll();
            closeSheet();
            if (dom.starting) {
                $("waitRoomStartingText").textContent = tr("gameStarting", "Oyun başlayır!");
                dom.starting.hidden = false;
            }
            celebrate("cheer", 4000);
            window.location.href = url || config.playerScreenUrl;
        }

        // ── Server ilə sinxron ──────────────────────────────────────────────
        async function syncState() {
            if (state.done || !config.stateUrl) return;
            state.lastSync = Date.now();
            try {
                const response = await fetch(config.stateUrl, {
                    headers: { Accept: "application/json" },
                    credentials: "same-origin",
                    cache: "no-store",
                });
                if (response.status === 403) {
                    showKicked();
                    return;
                }
                if (!response.ok) return;
                const snapshot = await response.json();
                if (!snapshot || !snapshot.ok) return;
                applySettings(snapshot.settings);
                if (snapshot.state && snapshot.state !== "lobby") {
                    goToGame(config.playerScreenUrl);
                    return;
                }
                setLocked(snapshot.is_locked);
                renderPlayers(snapshot.players, snapshot.total_players);
            } catch (error) {
                // şəbəkə yoxdur — WS/yenidən cəhd idarə edir
            }
        }

        function socketUrl() {
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            return `${protocol}//${window.location.host}${config.wsPath}`;
        }

        function scheduleReconnect() {
            if (state.done) return;
            state.attempts += 1;
            const delay = Math.min(10000, 800 * Math.pow(2, state.attempts - 1)) + Math.floor(Math.random() * 400);
            window.clearTimeout(state.retryTimer);
            state.retryTimer = window.setTimeout(connect, delay);
        }

        function handleMessage(payload) {
            switch (payload && payload.type) {
                case "game_started": {
                    // 90–150 telefon eyni anda yönləndirilməsin: server verdiyi pəncərədə səpələnir.
                    const jitterMs = Math.min(Math.max(Number(payload.redirect_jitter_ms) || 0, 0), 3000);
                    window.setTimeout(() => goToGame(payload.redirect), Math.random() * jitterMs);
                    break;
                }
                case "lobby_state":
                    applySettings(payload.settings);
                    setLocked(payload.is_locked);
                    renderPlayers(payload.players, payload.count);
                    break;
                case "session_settings":
                    applySettings(payload.settings);
                    if (payload.is_locked !== undefined) setLocked(payload.is_locked);
                    break;
                case "reaction_event":
                    reactions.spawn(payload);
                    break;
                case "kicked":
                    showKicked();
                    break;
                default:
                    break;
            }
        }

        function connect() {
            window.clearTimeout(state.retryTimer);
            if (state.done) return;
            if (state.socket && state.socket.readyState <= 1) return;
            let socket;
            try {
                socket = new WebSocket(socketUrl());
            } catch (error) {
                scheduleReconnect();
                return;
            }
            state.socket = socket;
            socket.onopen = () => {
                if (socket !== state.socket) return;
                state.attempts = 0;
                setNet("online");
            };
            socket.onmessage = (event) => {
                if (socket !== state.socket) return;
                try {
                    const message = JSON.parse(event.data);
                    handleMessage(message.data || message);
                } catch (error) {
                    // yanlış mesaj — yox sayılır
                }
            };
            socket.onclose = () => {
                if (socket !== state.socket) return;
                state.socket = null;
                if (state.done) return;
                setNet(navigator.onLine === false ? "offline" : "reconnecting");
                scheduleReconnect();
            };
        }

        function wsOpen() {
            return Boolean(state.socket && state.socket.readyState === WebSocket.OPEN);
        }

        // ── Profil vərəqi (wait_room_profile_sheet.js) ──────────────────────
        const sheet = window.LiveWaitRoomProfileSheet.create({
            dom,
            tr,
            config,
            catalog,
            avatar,
            nicknameTools,
            avatarLabels,
            accessoryLabels,
            getState: () => state,
            applyLocked: () => setLocked(state.locked),
            onSaved: (player) => {
                state.me = Object.assign({}, state.me, player || {});
                celebrate("jump", 1600);
                showFeedback(tr("saved", "Saxlanıldı"), "success");
            },
            onFailed: () => syncState(),
        });
        const openSheet = () => sheet.open();
        const closeSheet = () => sheet.close();
        const saveProfile = () => sheet.save();

        // ── Reaksiyalar ─────────────────────────────────────────────────────
        const reactions = new window.LiveWaitRoomReactionPanel({
            root: dom.reactionDock,
            list: $("waitRoomReactionList"),
            overlay: $("waitRoomReactionOverlay"),
            cooldownMs: 1100,
            onSend: sendReaction,
        });

        async function sendReaction(reactionKey) {
            try {
                const body = new FormData();
                body.append("reaction_key", reactionKey);
                const response = await fetch(config.reactionUrl, {
                    method: "POST",
                    headers: { "X-CSRFToken": config.csrf },
                    credentials: "same-origin",
                    body,
                });
                if (response.status === 429) {
                    const retry = Number(response.headers.get("Retry-After") || 0);
                    reactions.setCooldown(Math.max(2, retry || 5) * 1000);
                    if (Date.now() - state.reactionWarnAt > 6000) {
                        state.reactionWarnAt = Date.now();
                        showFeedback(tr("reactionWait", "Bir az gözlə — reaksiyalar çox tez-tezdir"), "warn");
                    }
                    return;
                }
                if (response.status === 403) {
                    // Oyun başlayıb və ya reaksiyalar söndürülüb — panel gizlənir, snapshot yoxlanır.
                    reactions.setEnabled(false);
                    syncState();
                }
            } catch (error) {
                // şəbəkə xətası — səssiz
            }
        }

        // ── Hadisələr ───────────────────────────────────────────────────────
        const delegate =
            window.EMSDelegate && typeof window.EMSDelegate.on === "function"
                ? window.EMSDelegate.on
                : (type, selector, handler) =>
                      document.addEventListener(type, (event) => {
                          const match = event.target && event.target.closest ? event.target.closest(selector) : null;
                          if (match) handler.call(match, event, match);
                      });
        delegate("click", "[data-wait-room-open]", openSheet);
        delegate("click", "[data-wait-room-close]", closeSheet);
        delegate("click", "#waitRoomModalBackdrop", closeSheet);
        delegate("click", "#waitRoomSaveButton", saveProfile);
        delegate("click", "[data-wait-room-panel-target]", (event, tab) => sheet.setPanel(tab.dataset.waitRoomPanelTarget));
        delegate("input", "#waitRoomNicknameInput", () => {
            dom.nickError.textContent = "";
            sheet.renderPreview();
        });
        delegate("keydown", "#waitRoomNicknameInput", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                saveProfile();
            }
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeSheet();
        });
        window.addEventListener("online", () => {
            if (wsOpen()) {
                setNet("online");
            } else {
                setNet("reconnecting");
                state.attempts = 0;
                connect();
            }
            syncState();
        });
        window.addEventListener("offline", () => setNet("offline"));
        document.addEventListener("visibilitychange", () => {
            if (document.hidden || state.done) return;
            state.attempts = 0;
            connect();
            syncState();
        });
        window.addEventListener("pagehide", () => {
            if (state.socket) {
                state.socket.onclose = null;
                state.socket.close();
                state.socket = null;
            }
        });
        window.addEventListener("pageshow", (event) => {
            if (event.persisted && !state.done) {
                connect();
                syncState();
            }
        });

        // ── Başlanğıc ───────────────────────────────────────────────────────
        const STATIC_TEXT = {
            lookOnScreen: "Adını böyük ekranda axtar!",
            reactionsHint: "Reaksiya göndər",
            editLook: "Görünüşü dəyiş",
        };
        document.querySelectorAll("[data-lxw-i18n]").forEach((el) => {
            const key = el.dataset.lxwI18n;
            el.textContent = tr(key, STATIC_TEXT[key] || "");
        });
        reactions.init();
        if (dom.status) dom.status.textContent = tr("waitingHost", "Müəllimin oyunu başlatmasını gözləyirik");
        applySettings(state.settings);
        setLocked(state.locked);
        renderHero("wave");
        window.setTimeout(() => renderHero("idle"), 2200);
        try {
            renderPlayers(JSON.parse(($("initialPlayers") || {}).textContent || "[]"));
        } catch (error) {
            renderCount(1);
        }
        connect();
        syncState();
        state.pollTimer = window.setInterval(() => {
            if (state.done || document.hidden) return;
            const gap = Date.now() - state.lastSync;
            if ((!wsOpen() && gap >= 3000) || gap >= 12000) syncState();
        }, 1000);
    }

    if (window.EMSReady) window.EMSReady(init);
    else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
