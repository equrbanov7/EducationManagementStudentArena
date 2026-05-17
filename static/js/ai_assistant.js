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
    const limitBadge = document.getElementById("ai-chat-limit");
    const limitExceeded = document.getElementById("ai-chat-limit-exceeded");
    const inputWrap = document.getElementById("ai-chat-input-wrap");

    if (!botBtn || !panel) return;

    // ── State ────────────────────────────────────────────────────────
    let isOpen = false;
    let isLoading = false;
    let remainingRequests = null;
    let requestLimit = null;
    let hasGreeted = false;

    // ── CSRF token ───────────────────────────────────────────────────
    function getCsrfToken() {
        const cookie = document.cookie.split("; ").find(c => c.startsWith("csrftoken="));
        return cookie ? cookie.split("=")[1] : "";
    }

    // ── Bot SVG (small inline for avatar) ────────────────────────────
    const botAvatarSVG = `<svg viewBox="0 0 400 400" xmlns="http://www.w3.org/2000/svg" width="20" height="20">
        <g><rect x="90" y="60" width="220" height="140" rx="55" fill="#e8f0fe"/>
        <rect x="110" y="80" width="180" height="100" rx="35" fill="#1e272e"/>
        <circle cx="155" cy="125" r="16" fill="#48dbfb"/>
        <circle cx="151" cy="118" r="4" fill="#fff"/>
        <circle cx="245" cy="125" r="16" fill="#48dbfb"/>
        <circle cx="241" cy="118" r="4" fill="#fff"/>
        <path d="M 188 150 Q 200 162 212 150" stroke="#48dbfb" stroke-width="5" stroke-linecap="round" fill="none"/>
        <rect x="125" y="210" width="150" height="110" rx="55" fill="#e8f0fe"/>
        </g></svg>`;

    // ── Panel toggle ─────────────────────────────────────────────────
    function openPanel() {
        isOpen = true;
        panel.classList.add("ai-chat-panel--open");
        botBtn.style.display = "none";
        tooltip.classList.remove("ai-bot-tooltip--visible");
        inputEl.focus();

        if (!hasGreeted) {
            hasGreeted = true;
            addBotMessage("Salam! Mən EMSArena AI. Suallarınızı cavablandırmağa hazıram. Necə kömək edə bilərəm?");
        }
    }

    function closePanel() {
        isOpen = false;
        panel.classList.remove("ai-chat-panel--open");
        botBtn.style.display = "flex";
    }

    botBtn.addEventListener("click", openPanel);
    closeBtn.addEventListener("click", closePanel);

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
    function addUserMessage(text) {
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--user";
        el.innerHTML = `<div class="ai-msg-bubble"></div>`;
        el.querySelector(".ai-msg-bubble").textContent = text;
        messagesEl.appendChild(el);
        scrollToBottom();
    }

    function addBotMessage(text) {
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--bot";
        el.innerHTML = `<div class="ai-msg-avatar">${botAvatarSVG}</div><div class="ai-msg-bubble"></div>`;
        el.querySelector(".ai-msg-bubble").textContent = text;
        messagesEl.appendChild(el);
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
        if (remaining !== null && limit !== null) {
            remainingRequests = remaining;
            requestLimit = limit;
            limitBadge.textContent = `Sorğular: ${remaining} / ${limit}`;
        }

        if (remainingRequests !== null && remainingRequests <= 0) {
            limitExceeded.style.display = "block";
            inputWrap.style.display = "none";
        } else {
            limitExceeded.style.display = "none";
            inputWrap.style.display = "flex";
        }
    }

    // ── Send message ─────────────────────────────────────────────────
    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text || isLoading) return;

        addUserMessage(text);
        inputEl.value = "";
        setLoading(true);
        showTyping();

        try {
            const resp = await fetch("/api/ai-assistant/chat/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: JSON.stringify({ message: text }),
            });

            const data = await resp.json();
            hideTyping();

            if (data.answer) {
                addBotMessage(data.answer);
            } else if (data.error) {
                addBotMessage(data.error);
            } else {
                addBotMessage("Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin.");
            }

            if (data.remaining_requests !== undefined) {
                updateLimitDisplay(data.remaining_requests, data.limit);
            }
        } catch (err) {
            hideTyping();
            addBotMessage("Şəbəkə xətası. Zəhmət olmasa yenidən cəhd edin.");
        }

        setLoading(false);
    }

    function setLoading(loading) {
        isLoading = loading;
        sendBtn.disabled = loading;
        inputEl.disabled = loading;
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // ── Escape to close ──────────────────────────────────────────────
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && isOpen) {
            closePanel();
        }
    });
})();
