/**
 * AI Assistant Chatbot Widget
 *
 * Manages the floating bot button, chat panel open/close,
 * message sending, typing indicator, and rate limit display.
 */
(function () {
    "use strict";

    // ── DOM references ───────────────────────────────────────────────
    const botBtn = document.getElementById("ai-bot-btn");
    const tooltip = document.getElementById("ai-bot-tooltip");
    const panel = document.getElementById("ai-chat-panel");
    const closeBtn = document.getElementById("ai-chat-close");
    const messagesEl = document.getElementById("ai-chat-messages");
    const inputEl = document.getElementById("ai-chat-input");
    const sendBtn = document.getElementById("ai-chat-send");
    const emojiBtn = document.getElementById("ai-chat-emoji");
    const limitBadge = document.getElementById("ai-chat-limit");
    const limitExceeded = document.getElementById("ai-chat-limit-exceeded");
    const inputWrap = document.getElementById("ai-chat-input-wrap");

    if (!botBtn || !panel) return;

    const chatUrl = panel.dataset.chatUrl || "/api/ai-assistant/chat/";
    const quotaUrl = panel.dataset.quotaUrl || "/api/ai-assistant/quota/";
    const limitLabel = panel.dataset.limitLabel || gettext("Sorğular");
    const loadingLabel = panel.dataset.loadingLabel || gettext("yüklənir...");
    const uiText = {
        greeting: panel.dataset.greeting || gettext("Salam! Suallarınızı cavablandırmağa hazıram. Necə kömək edə bilərəm?"),
        limitDisabled: panel.dataset.limitDisabledMessage || gettext("AI sorğu limiti hazırda aktiv deyil."),
        sendFailed: panel.dataset.sendFailedMessage || gettext("Sorğu göndərilmədi. Səhifəni yeniləyib yenidən cəhd edin."),
        genericError: panel.dataset.genericErrorMessage || gettext("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin."),
        networkError: panel.dataset.networkErrorMessage || gettext("Şəbəkə xətası. Zəhmət olmasa yenidən cəhd edin."),
    };
    const storageKey = panel.dataset.storageKey || "emsa.aiAssistant.v2.global";
    const historyTtlMs = Number(panel.dataset.historyTtlMs) || (15 * 60 * 1000);
    const historyMaxMessages = 60;

    // ── State ────────────────────────────────────────────────────────
    let isOpen = false;
    let isLoading = false;
    let remainingRequests = null;
    let requestLimit = null;
    let hasGreeted = false;
    let hasLoadedQuota = false;
    let chatHistory = [];
    let lastUserMessageAt = 0;
    let lastHistoryUpdatedAt = 0;

    // ── CSRF token ───────────────────────────────────────────────────
    function getCsrfToken() {
        const embeddedToken = (panel.dataset.csrfToken || "").trim();
        if (embeddedToken && embeddedToken !== "NOTPROVIDED") {
            return embeddedToken;
        }

        const cookie = document.cookie.split("; ").find(c => c.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    // ── Bot SVG (small inline for avatar) ────────────────────────────
    const botAvatarSVG = `<svg viewBox="70 48 260 176" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <rect x="75" y="105" width="40" height="50" rx="15" fill="#f8fbff"/>
        <rect x="285" y="105" width="40" height="50" rx="15" fill="#f8fbff"/>
        <rect x="90" y="60" width="220" height="140" rx="55" fill="#f8fbff"/>
        <rect x="110" y="80" width="180" height="100" rx="35" fill="#111827"/>
        <circle cx="155" cy="125" r="18" fill="#48dbfb"/>
        <circle cx="150" cy="118" r="6" fill="#ffffff"/>
        <circle cx="162" cy="128" r="3" fill="#ffffff"/>
        <circle cx="245" cy="125" r="18" fill="#48dbfb"/>
        <circle cx="240" cy="118" r="6" fill="#ffffff"/>
        <circle cx="252" cy="128" r="3" fill="#ffffff"/>
        <path d="M 188 150 Q 200 162 212 150" stroke="#48dbfb" stroke-width="7" stroke-linecap="round" fill="none"/>
    </svg>`;

    // ── Persist chat between page navigations ────────────────────────
    function readStoredHistory() {
        try {
            const raw = window.localStorage.getItem(storageKey);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (err) {
            return null;
        }
    }

    function clearStoredHistory() {
        chatHistory = [];
        lastUserMessageAt = 0;
        lastHistoryUpdatedAt = 0;
        try {
            window.localStorage.removeItem(storageKey);
        } catch (err) {
            // localStorage can be unavailable in private/restricted contexts.
        }
    }

    function historyExpiryAnchor() {
        return lastUserMessageAt || lastHistoryUpdatedAt || 0;
    }

    function isHistoryExpired() {
        const anchor = historyExpiryAnchor();
        return Boolean(anchor && Date.now() - anchor > historyTtlMs);
    }

    function saveStoredHistory() {
        if (!chatHistory.length) {
            clearStoredHistory();
            return;
        }

        const payload = {
            version: 2,
            lastUserMessageAt,
            updatedAt: lastHistoryUpdatedAt || Date.now(),
            messages: chatHistory.slice(-historyMaxMessages),
        };

        try {
            window.localStorage.setItem(storageKey, JSON.stringify(payload));
        } catch (err) {
            // Best-effort persistence only; chat still works without storage.
        }
    }

    function loadStoredHistory() {
        const payload = readStoredHistory();
        if (!payload || !Array.isArray(payload.messages)) {
            clearStoredHistory();
            return;
        }

        chatHistory = payload.messages
            .filter(msg => msg && (msg.role === "user" || msg.role === "bot") && typeof msg.text === "string")
            .map(msg => ({
                role: msg.role,
                text: msg.text.slice(0, 5000),
                at: Number(msg.at) || Date.now(),
            }))
            .slice(-historyMaxMessages);
        lastUserMessageAt = Number(payload.lastUserMessageAt) || 0;
        const lastMessage = chatHistory.length ? chatHistory[chatHistory.length - 1] : null;
        lastHistoryUpdatedAt = Number(payload.updatedAt) || (lastMessage ? lastMessage.at : 0);

        if (!chatHistory.length || isHistoryExpired()) {
            clearStoredHistory();
        }
    }

    function rememberMessage(role, text, options) {
        const now = Date.now();
        chatHistory.push({ role, text, at: now });
        chatHistory = chatHistory.slice(-historyMaxMessages);
        lastHistoryUpdatedAt = now;
        if (options && options.touchUser) {
            lastUserMessageAt = now;
        }
        saveStoredHistory();
    }

    function renderStoredHistory() {
        messagesEl.innerHTML = "";
        chatHistory.forEach(msg => {
            if (msg.role === "user") {
                addUserMessage(msg.text, { persist: false });
            } else {
                addBotMessage(msg.text, { persist: false });
            }
        });
        hasGreeted = chatHistory.length > 0;
        scrollToBottom();
    }

    function resetHistoryIfExpired() {
        if (!chatHistory.length || !isHistoryExpired()) return;

        clearStoredHistory();
        messagesEl.innerHTML = "";
        hasGreeted = false;

        if (isOpen) {
            hasGreeted = true;
            addBotMessage(uiText.greeting);
        }
    }

    // ── Panel toggle ─────────────────────────────────────────────────
    function openPanel() {
        resetHistoryIfExpired();
        isOpen = true;
        panel.classList.add("ai-chat-panel--open");
        botBtn.style.display = "none";
        tooltip.classList.remove("ai-bot-tooltip--visible");
        inputEl.focus();
        fetchQuota();

        if (!hasGreeted) {
            hasGreeted = true;
            addBotMessage(uiText.greeting);
        }
    }

    function closePanel() {
        isOpen = false;
        panel.classList.remove("ai-chat-panel--open");
        botBtn.style.display = "flex";
    }

    botBtn.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);

    document.addEventListener("pointerdown", function (e) {
        if (!isOpen) return;
        if (panel.contains(e.target) || botBtn.contains(e.target)) return;
        closePanel();
    });

    // ── Wave animation (occasional) ──────────────────────────────────
    let waveInterval = null;

    function triggerWave() {
        if (isOpen) return;
        botBtn.classList.add("ai-bot-btn--wave");
        tooltip.classList.add("ai-bot-tooltip--visible");

        setTimeout(() => {
            botBtn.classList.remove("ai-bot-btn--wave");
        }, 1800);

        setTimeout(() => {
            if (!isOpen) tooltip.classList.remove("ai-bot-tooltip--visible");
        }, 4000);
    }

    // First wave after 5s, then every 30s
    setTimeout(triggerWave, 5000);
    waveInterval = setInterval(triggerWave, 30000);

    // ── Messages ─────────────────────────────────────────────────────
    function addUserMessage(text, options) {
        const shouldPersist = !options || options.persist !== false;
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--user";
        el.innerHTML = `<div class="ai-msg-bubble"></div>`;
        el.querySelector(".ai-msg-bubble").textContent = text;
        messagesEl.appendChild(el);
        if (shouldPersist) {
            rememberMessage("user", text, { touchUser: true });
        }
        scrollToBottom();
    }

    function renderMarkdown(text) {
        var html = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function (match, linkText, url) {
            if (url.startsWith("/") || url.startsWith("http://") || url.startsWith("https://")) {
                var escaped = url.replace(/"/g, "&quot;");
                return '<a href="' + escaped + '" class="ai-msg-link">' + linkText + "</a>";
            }
            return linkText;
        });

        var lines = html.split("\n");
        var result = [];
        var inList = false;

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var trimmed = line.trim();

            if (/^[\-\*]\s+/.test(trimmed)) {
                if (!inList) {
                    result.push("<ul>");
                    inList = true;
                }
                result.push("<li>" + trimmed.replace(/^[\-\*]\s+/, "") + "</li>");
            } else {
                if (inList) {
                    result.push("</ul>");
                    inList = false;
                }
                if (trimmed === "") {
                    if (result.length > 0) result.push("<br>");
                } else {
                    result.push("<p>" + trimmed + "</p>");
                }
            }
        }

        if (inList) result.push("</ul>");
        return result.join("");
    }

    function addBotMessage(text, options) {
        const shouldPersist = !options || options.persist !== false;
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--bot";
        el.innerHTML = `<div class="ai-msg-avatar">${botAvatarSVG}</div><div class="ai-msg-bubble ai-msg-bubble--rich"></div>`;
        el.querySelector(".ai-msg-bubble").innerHTML = renderMarkdown(text);
        messagesEl.appendChild(el);
        if (shouldPersist) {
            rememberMessage("bot", text);
        }
        scrollToBottom();
    }

    function showTyping() {
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--bot ai-msg-typing";
        el.id = "ai-typing-indicator";
        el.innerHTML = `<div class="ai-msg-avatar">${botAvatarSVG}</div>
            <div class="ai-msg-bubble">
                <div class="ai-typing-dot"></div>
                <div class="ai-typing-dot"></div>
                <div class="ai-typing-dot"></div>
            </div>`;
        messagesEl.appendChild(el);
        scrollToBottom();
    }

    function hideTyping() {
        const el = document.getElementById("ai-typing-indicator");
        if (el) el.remove();
    }

    function scrollToBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // ── Rate limit display ───────────────────────────────────────────
    function updateLimitDisplay(remaining, limit) {
        const parsedRemaining = Number(remaining);
        const parsedLimit = Number(limit);

        if (Number.isFinite(parsedRemaining) && Number.isFinite(parsedLimit)) {
            remainingRequests = parsedRemaining;
            requestLimit = parsedLimit;
            hasLoadedQuota = true;
            limitBadge.textContent = `${limitLabel}: ${parsedRemaining} / ${parsedLimit}`;
        }

        if (requestLimit !== null && requestLimit <= 0) {
            limitExceeded.style.display = "block";
            limitExceeded.textContent = uiText.limitDisabled;
            inputWrap.style.display = "none";
        } else if (remainingRequests !== null && remainingRequests <= 0) {
            limitExceeded.style.display = "block";
            inputWrap.style.display = "none";
        } else {
            limitExceeded.style.display = "none";
            inputWrap.style.display = "flex";
        }
    }

    async function readJsonResponse(resp) {
        const contentType = resp.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            return resp.json();
        }

        const text = await resp.text();
        return {
            error: text || `HTTP ${resp.status}`,
        };
    }

    async function fetchQuota() {
        if (hasLoadedQuota || !quotaUrl) return;

        try {
            const resp = await fetch(quotaUrl, {
                method: "GET",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                },
            });
            const data = await readJsonResponse(resp);

            if (data.remaining_requests !== undefined) {
                updateLimitDisplay(data.remaining_requests, data.limit);
            }
        } catch (err) {
            limitBadge.textContent = `${limitLabel}: ${loadingLabel}`;
        }
    }

    // ── Send message ─────────────────────────────────────────────────
    async function sendMessage() {
        resetHistoryIfExpired();
        const text = inputEl.value.trim();
        if (!text || isLoading) return;

        addUserMessage(text);
        inputEl.value = "";
        setLoading(true);
        showTyping();

        try {
            const resp = await fetch(chatUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ message: text, current_page: window.location.href }),
            });

            const data = await readJsonResponse(resp);
            hideTyping();

            if (resp.ok && data.answer) {
                addBotMessage(data.answer);
            } else if (data.error === "rate_limit_exceeded" && data.answer) {
                addBotMessage(data.answer);
            } else if (data.error) {
                const fallback = resp.ok
                    ? data.error
                    : uiText.sendFailed;
                addBotMessage(fallback);
            } else {
                addBotMessage(uiText.genericError);
            }

            if (data.remaining_requests !== undefined) {
                updateLimitDisplay(data.remaining_requests, data.limit);
            }
        } catch (err) {
            hideTyping();
            addBotMessage(uiText.networkError);
        }

        setLoading(false);
    }

    function setLoading(loading) {
        isLoading = loading;
        sendBtn.disabled = loading;
        inputEl.disabled = loading;
    }

    sendBtn.addEventListener("click", sendMessage);
    if (emojiBtn) {
        emojiBtn.addEventListener("click", function () {
            inputEl.focus();
        });
    }
    inputEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    document.querySelectorAll(".ai-chat-org-logo img").forEach(img => {
        img.addEventListener("error", function () {
            const logo = img.closest(".ai-chat-org-logo");
            if (logo) {
                logo.classList.add("ai-chat-org-logo--fallback");
            }
        }, { once: true });
    });

    loadStoredHistory();
    renderStoredHistory();
    setInterval(resetHistoryIfExpired, 60 * 1000);

    // ── Escape to close ──────────────────────────────────────────────
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && isOpen) {
            closePanel();
        }
    });
})();
