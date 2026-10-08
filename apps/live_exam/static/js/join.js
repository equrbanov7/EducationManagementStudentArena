/* join.js — canlı oyuna qoşulma (LX-FE-PLAYER 2026-09-29).
 *  • Təsadüfi avatar + «🎲 başqa avatar»; ad sahəsində sayğac (32);
 *  • Xətalar: 409 (ad məşğuldur) / 400 → sahənin altında; 403 (lobbi kilidli, oyun başlayıb,
 *    müəllim çıxarıb, limit dolub) / 404 → blok kartı (server mesajı + «Yenidən yoxla» / «Başqa PIN»);
 *    429 → Retry-After saniyə sayğacı ilə düymə müvəqqəti bağlanır;
 *  • Əvvəlki qoşulma tapılıbsa — davam et / yenidən qoşul dialoqu.
 * Anonim WebSocket YOXDUR (server artıq rədd edir; tema server tərəfindən render olunur).
 * AJAX-safe: EMSReady + idempotent qoruyucu.
 */
(function () {
    "use strict";

    function init() {
        const card = document.getElementById("joinCard");
        if (!card || card.dataset.lxInit) return;
        card.dataset.lxInit = "1";

        const config = window.LiveJoinConfig || {};
        const i18n = window.LIVE_EXAM_JOIN_I18N || {};
        const catalog = window.LiveAvatarCatalog || {};
        const renderer = window.LiveAvatarRenderer;
        const nicknameTools = window.LiveWaitRoomNicknameEditor || {};
        const UNTRANSLATED = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;
        const MAX = 32;
        const tr = (key, fallback) => {
            const value = i18n[key];
            if (typeof value !== "string" || !value.trim() || UNTRANSLATED.test(value.trim())) return fallback;
            return value;
        };
        const fmt = (template, values) =>
            String(template).replace(/\{(\w+)\}/g, (match, key) =>
                Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
            );

        // Server mesajı hələ tərcümə olunmayıbsa (msgid açarı gəlir) — tanınan açarlar üçün az ehtiyat mətni.
        const SERVER_FALLBACK = {
            removed_by_host: "Müəllim səni bu oyundan çıxarıb — bu cihazla yenidən qoşulmaq olmur.",
            lobby_locked: "Lobbi kilidlənib — müəllimdən açmasını xahiş et.",
            game_already_started: "Oyun artıq başlayıb — növbəti oyunu gözlə.",
            session_finished: "Bu oyun artıq bitib.",
            participant_limit_reached: "İştirakçı limiti dolub.",
            nickname_required: "Adını yaz.",
        };
        const serverText = (message) => {
            const text = String(message || "").trim();
            if (!text) return tr("errorUnknown", "Xəta baş verdi");
            if (UNTRANSLATED.test(text)) return SERVER_FALLBACK[text] || tr("errorUnknown", "Xəta baş verdi");
            return text;
        };
        const $ = (id) => document.getElementById(id);
        const dom = {
            form: $("joinForm"),
            input: $("nickname"),
            count: $("joinNicknameCount"),
            error: $("joinNicknameError"),
            status: $("joinStatus"),
            button: $("joinBtn"),
            preview: $("joinPreview"),
            reroll: $("joinReroll"),
            blocked: $("joinBlocked"),
            resumeNotice: $("resumePlayerBtn"),
            resumePrompt: $("joinResumePrompt"),
        };
        if (!dom.form || !dom.input || !dom.button) return;

        const settings = config.sessionSettings || {};
        const charactersEnabled = settings.characters_enabled !== false;
        const remembered = config.rememberedPlayer || null;
        const defaultAvatar = catalog.defaultAvatarKey || "avatar_1";
        const defaultAccessory = catalog.defaultAccessoryKey || "accessory_none";
        const accessoryChoices = (catalog.accessoryKeys || []).filter((key) => key && key !== defaultAccessory);
        const pick = (items, fallback, avoid) => {
            const pool = (items || []).filter((item) => item && item !== avoid);
            return pool.length ? pool[Math.floor(Math.random() * pool.length)] : fallback;
        };

        let avatarKey = defaultAvatar;
        let accessoryKey = defaultAccessory;
        let allowFreshJoin = !remembered;
        let joining = false;
        let rateTimer = null;
        let rateLimitedUntil = 0;
        let navigating = false;

        function rollAppearance() {
            if (!charactersEnabled) return;
            avatarKey = pick(catalog.avatarKeys, defaultAvatar, avatarKey);
            accessoryKey = pick(accessoryChoices, defaultAccessory, accessoryKey);
        }

        function renderPreview(dance) {
            if (!dom.preview || !renderer) return;
            dom.preview.innerHTML = renderer.renderAvatarMarkup(
                { avatar_key: avatarKey, accessory_key: accessoryKey },
                { size: 120, crop: "full", interactive: false, className: "lxj-avatar__svg", dance: dance || "idle" }
            );
        }

        function updateCount() {
            if (dom.count) dom.count.textContent = `${dom.input.value.length}/${MAX}`;
        }

        function setError(message) {
            dom.error.textContent = message || "";
            dom.input.setAttribute("aria-invalid", message ? "true" : "false");
            dom.input.classList.toggle("is-invalid", Boolean(message));
        }

        function setStatus(message, kind) {
            dom.status.textContent = message || "";
            dom.status.dataset.kind = kind || "";
        }

        function setJoining(active) {
            joining = Boolean(active);
            dom.button.disabled = joining;
            dom.button.classList.toggle("is-loading", joining);
            const label = dom.button.querySelector("span");
            if (label) {
                label.textContent = joining ? tr("buttonJoining", "Qoşulur…") : tr("joinReady", "Oyuna qoşul!");
            }
        }

        function showBlocked(message) {
            $("joinBlockedTitle").textContent = tr("blockedTitle", "Qoşulmaq alınmadı");
            $("joinBlockedMessage").textContent = serverText(message);
            $("joinRetry").textContent = tr("tryAgain", "Yenidən yoxla");
            const newPin = $("joinNewPin");
            newPin.textContent = tr("enterNewPin", "Başqa PIN daxil et");
            if (config.pinEntryUrl) newPin.href = config.pinEntryUrl;
            dom.form.hidden = true;
            dom.blocked.hidden = false;
            $("joinRetry").focus();
        }

        function hideBlocked() {
            dom.blocked.hidden = true;
            dom.form.hidden = false;
            setStatus("");
            dom.input.focus();
        }

        function rateLimit(seconds) {
            let left = Math.max(1, Math.round(seconds || 10));
            rateLimitedUntil = Date.now() + left * 1000;
            dom.button.disabled = true;
            window.clearInterval(rateTimer);
            const tick = () => {
                setStatus(fmt(tr("rateLimited", "Çox tez-tez cəhd edildi — {seconds} san sonra yenidən yoxla."), { seconds: left }), "warn");
                left -= 1;
                if (left < 0) {
                    window.clearInterval(rateTimer);
                    setStatus("");
                    dom.button.disabled = false;
                }
            };
            tick();
            rateTimer = window.setInterval(tick, 1000);
        }

        function validate() {
            const messages = {
                required: tr("nicknameRequired", "Adını yaz."),
                tooLong: tr("nicknameTooLong", "Ad çox uzundur."),
            };
            if (typeof nicknameTools.validateNickname === "function") {
                return nicknameTools.validateNickname(dom.input.value, messages);
            }
            const value = String(dom.input.value || "").trim();
            return { valid: Boolean(value), value, message: value ? "" : messages.required };
        }

        function openResume() {
            if (!dom.resumePrompt) return;
            dom.resumePrompt.hidden = false;
            document.body.classList.add("lxj-modal-open");
            const first = $("joinResumeContinue");
            if (first) first.focus();
        }

        function closeResume() {
            if (!dom.resumePrompt || dom.resumePrompt.hidden) return;
            dom.resumePrompt.hidden = true;
            document.body.classList.remove("lxj-modal-open");
            dom.input.focus();
        }

        function continuePrevious() {
            if (config.resumeUrl) window.location.href = config.resumeUrl;
        }

        async function submitJoin(forceFresh) {
            if (joining) return;
            const validation = validate();
            dom.input.value = validation.value;
            updateCount();
            if (!validation.valid) {
                setError(validation.message);
                dom.input.focus();
                return;
            }
            setError("");
            if (!forceFresh && !allowFreshJoin && remembered && validation.value === String(remembered.nickname || "").trim()) {
                openResume();
                return;
            }
            setJoining(true);
            setStatus("");
            try {
                const body = new FormData();
                body.append("nickname", validation.value);
                body.append("avatar_key", avatarKey);
                body.append("accessory_key", accessoryKey);
                const response = await fetch(config.joinUrl, {
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
                if (response.ok && data.ok && data.redirect) {
                    navigating = true;
                    renderPreview("jump");
                    window.location.href = data.redirect;
                    return;
                }
                if (response.status === 429) {
                    rateLimit(Number(response.headers.get("Retry-After") || 10));
                    return;
                }
                if (response.status === 409 || response.status === 400) {
                    setError(serverText(data.message));
                    dom.input.focus();
                    return;
                }
                if (response.status === 403 || response.status === 404) {
                    showBlocked(data.message);
                    return;
                }
                setStatus(serverText(data.message), "error");
            } catch (error) {
                setStatus(tr("errorConnection", "Bağlantı xətası"), "error");
            } finally {
                if (navigating) return;
                setJoining(false);
                if (Date.now() < rateLimitedUntil) dom.button.disabled = true;
            }
        }

        // ── Başlanğıc ─────────────────────────────────────────────────────
        if (remembered && charactersEnabled) {
            avatarKey = remembered.avatar_key || defaultAvatar;
            accessoryKey = remembered.accessory_key || defaultAccessory;
        } else {
            rollAppearance();
        }
        if (!dom.input.value.trim() && config.generatedNickname) dom.input.value = config.generatedNickname;
        if (!dom.input.value.trim() && remembered && remembered.nickname) dom.input.value = remembered.nickname;
        if (dom.reroll) {
            dom.reroll.hidden = !charactersEnabled;
            dom.reroll.setAttribute("aria-label", tr("rerollAvatar", "Başqa avatar"));
            dom.reroll.title = tr("rerollAvatar", "Başqa avatar");
        }
        renderPreview("wave");
        updateCount();

        dom.form.addEventListener("submit", (event) => {
            event.preventDefault();
            submitJoin(false);
        });
        dom.input.addEventListener("input", () => {
            setError("");
            if (dom.status.dataset.kind !== "warn") setStatus("");
            updateCount();
        });
        if (dom.reroll) {
            dom.reroll.addEventListener("click", () => {
                rollAppearance();
                renderPreview("jump");
            });
        }
        $("joinRetry").addEventListener("click", () => {
            hideBlocked();
        });
        // 2026-10-08: server bu cihazın qoşula bilməyəcəyini əvvəlcədən bilirsə (çıxarılıb / gec qoşulma
        // bağlıdır / oyun bitib) — formanı doldurtmadan izahlı blok kartı göstər.
        if (config.blockedMessage) showBlocked(config.blockedMessage);
        if (dom.resumeNotice) dom.resumeNotice.addEventListener("click", continuePrevious);
        const resumeContinue = $("joinResumeContinue");
        if (resumeContinue) resumeContinue.addEventListener("click", continuePrevious);
        const resumeRestart = $("joinResumeRestart");
        if (resumeRestart) {
            resumeRestart.addEventListener("click", () => {
                allowFreshJoin = true;
                closeResume();
                rollAppearance();
                renderPreview("jump");
                submitJoin(true);
            });
        }
        const resumeClose = $("joinResumeClose");
        if (resumeClose) resumeClose.addEventListener("click", closeResume);
        if (dom.resumePrompt) {
            dom.resumePrompt.addEventListener("click", (event) => {
                if (event.target === dom.resumePrompt) closeResume();
            });
        }
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeResume();
        });
        window.setTimeout(() => {
            if (config.blockedMessage) return;
            if (!dom.resumePrompt || dom.resumePrompt.hidden) {
                try {
                    dom.input.focus({ preventScroll: true });
                } catch (error) {
                    dom.input.focus();
                }
            }
        }, 150);
    }

    if (window.EMSReady) window.EMSReady(init);
    else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
