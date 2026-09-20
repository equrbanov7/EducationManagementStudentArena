/**
 * AI assistent vidceti — üzən düymə, panel, mesaj göndərmə, limit göstəricisi.
 *
 * 2026-09-20 redizayn + sərtləşdirmə (sahib):
 *  • «tezliklə» vəziyyəti: server `quota` cavabında `enabled`/`configured`
 *    false-dursa yazma sahəsi bağlanır və izah göstərilir (çat çağırılmır);
 *  • serverə yalnız səhifənin YOLU gedir (sorğu sətri/host yox);
 *  • cavab markdown-u əvvəl HTML-escape olunur; keçidlər yalnız eyni sayt
 *    (`/…`) və ya https:// — kənar keçid yeni tabda, `rel="noopener noreferrer"`;
 *  • tarixçə localStorage-də istifadəçi+təşkilat açarı ilə, 15 dəq TTL;
 *  • inline style yox (CSP) — görünmə `hidden` atributu ilə.
 * ID-lər şablonla müqavilədir: templates/partials/_ai_assistant.html.
 */
(function () {
    "use strict";

    const botBtn = document.getElementById("ai-bot-btn");
    const tooltip = document.getElementById("ai-bot-tooltip");
    const panel = document.getElementById("ai-chat-panel");
    const closeBtn = document.getElementById("ai-chat-close");
    const messagesEl = document.getElementById("ai-chat-messages");
    const inputEl = document.getElementById("ai-chat-input");
    const sendBtn = document.getElementById("ai-chat-send");
    const limitBadge = document.getElementById("ai-chat-limit");
    const notice = document.getElementById("ai-chat-limit-exceeded");
    const noticeText = notice ? notice.querySelector("[data-ai-notice-text]") : null;
    const inputWrap = document.getElementById("ai-chat-input-wrap");
    const statusEl = document.getElementById("ai-chat-status");

    if (!botBtn || !panel || !messagesEl || !inputEl || !sendBtn) return;

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
        soonMessage: panel.dataset.soonMessage || "",
        online: panel.dataset.onlineLabel || "",
        offline: panel.dataset.offlineLabel || "",
        limitNotice: noticeText ? noticeText.textContent : "",
    };
    const storageKey = panel.dataset.storageKey || "emsa.aiAssistant.v3.global";
    const historyTtlMs = Number(panel.dataset.historyTtlMs) || 15 * 60 * 1000;
    const historyMaxMessages = 60;

    let isOpen = false;
    let isLoading = false;
    let isAvailable = true; // server: enabled && configured
    let remainingRequests = null;
    let requestLimit = null;
    let hasGreeted = false;
    let hasLoadedQuota = false;
    let chatHistory = [];
    let lastUserMessageAt = 0;
    let lastHistoryUpdatedAt = 0;

    function getCsrfToken() {
        const embedded = (panel.dataset.csrfToken || "").trim();
        if (embedded && embedded !== "NOTPROVIDED") return embedded;
        const cookie = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    const botAvatarSVG =
        '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
        '<rect x="8" y="14" width="32" height="24" rx="10" fill="currentColor"/>' +
        '<rect x="14" y="20" width="20" height="12" rx="6" class="ai-avatar-screen"/>' +
        '<circle cx="20" cy="26" r="2.4" fill="currentColor"/><circle cx="28" cy="26" r="2.4" fill="currentColor"/>' +
        '<rect x="22" y="7" width="4" height="7" rx="2" fill="currentColor"/><circle cx="24" cy="6" r="3" fill="currentColor"/></svg>';

    // ── Tarixçə (brauzerdə, TTL ilə) ────────────────────────────────────
    function readStoredHistory() {
        try {
            const raw = window.localStorage.getItem(storageKey);
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;
        }
    }
    function clearStoredHistory() {
        chatHistory = [];
        lastUserMessageAt = 0;
        lastHistoryUpdatedAt = 0;
        try { window.localStorage.removeItem(storageKey); } catch (err) { /* private rejim */ }
    }
    function isHistoryExpired() {
        const anchor = lastUserMessageAt || lastHistoryUpdatedAt || 0;
        return Boolean(anchor && Date.now() - anchor > historyTtlMs);
    }
    function saveStoredHistory() {
        if (!chatHistory.length) { clearStoredHistory(); return; }
        const payload = {
            version: 3,
            lastUserMessageAt,
            updatedAt: lastHistoryUpdatedAt || Date.now(),
            messages: chatHistory.slice(-historyMaxMessages),
        };
        try { window.localStorage.setItem(storageKey, JSON.stringify(payload)); } catch (err) { /* best-effort */ }
    }
    function loadStoredHistory() {
        const payload = readStoredHistory();
        if (!payload || !Array.isArray(payload.messages)) { clearStoredHistory(); return; }
        chatHistory = payload.messages
            .filter((m) => m && (m.role === "user" || m.role === "bot") && typeof m.text === "string")
            .map((m) => ({ role: m.role, text: m.text.slice(0, 5000), at: Number(m.at) || Date.now() }))
            .slice(-historyMaxMessages);
        lastUserMessageAt = Number(payload.lastUserMessageAt) || 0;
        const last = chatHistory.length ? chatHistory[chatHistory.length - 1] : null;
        lastHistoryUpdatedAt = Number(payload.updatedAt) || (last ? last.at : 0);
        if (!chatHistory.length || isHistoryExpired()) clearStoredHistory();
    }
    function rememberMessage(role, text, touchUser) {
        const now = Date.now();
        chatHistory.push({ role, text, at: now });
        chatHistory = chatHistory.slice(-historyMaxMessages);
        lastHistoryUpdatedAt = now;
        if (touchUser) lastUserMessageAt = now;
        saveStoredHistory();
    }
    function renderStoredHistory() {
        messagesEl.textContent = "";
        chatHistory.forEach((m) => (m.role === "user" ? addUserMessage(m.text, false) : addBotMessage(m.text, false)));
        hasGreeted = chatHistory.length > 0;
        scrollToBottom();
    }
    function resetHistoryIfExpired() {
        if (!chatHistory.length || !isHistoryExpired()) return;
        clearStoredHistory();
        messagesEl.textContent = "";
        hasGreeted = false;
        if (isOpen) { hasGreeted = true; addBotMessage(uiText.greeting); }
    }

    // ── Panel ───────────────────────────────────────────────────────────
    function openPanel() {
        resetHistoryIfExpired();
        isOpen = true;
        panel.hidden = false;
        requestAnimationFrame(() => panel.classList.add("ai-chat-panel--open"));
        botBtn.classList.add("ai-bot-btn--hidden");
        botBtn.setAttribute("aria-expanded", "true");
        tooltip.classList.remove("ai-bot-tooltip--visible");
        fetchQuota();
        if (!hasGreeted) { hasGreeted = true; addBotMessage(uiText.greeting); }
        if (isAvailable) inputEl.focus();
    }
    function closePanel() {
        isOpen = false;
        panel.classList.remove("ai-chat-panel--open");
        botBtn.classList.remove("ai-bot-btn--hidden");
        botBtn.setAttribute("aria-expanded", "false");
        window.setTimeout(() => { if (!isOpen) panel.hidden = true; }, 180);
        botBtn.focus();
    }
    botBtn.addEventListener("click", openPanel);
    if (closeBtn) closeBtn.addEventListener("click", closePanel);
    document.addEventListener("pointerdown", (e) => {
        if (!isOpen) return;
        if (panel.contains(e.target) || botBtn.contains(e.target)) return;
        closePanel();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen) closePanel(); });

    // İlk dəfə (səhifə açılandan 6 s sonra) bir dəfə diqqət çəkir — daimi dalğa yox.
    window.setTimeout(() => {
        if (isOpen) return;
        botBtn.classList.add("ai-bot-btn--wave");
        tooltip.classList.add("ai-bot-tooltip--visible");
        window.setTimeout(() => botBtn.classList.remove("ai-bot-btn--wave"), 1600);
        window.setTimeout(() => tooltip.classList.remove("ai-bot-tooltip--visible"), 5000);
    }, 6000);

    // ── Mesajlar ────────────────────────────────────────────────────────
    function addUserMessage(text, persist) {
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--user";
        const bubble = document.createElement("div");
        bubble.className = "ai-msg-bubble";
        bubble.textContent = text;
        el.appendChild(bubble);
        messagesEl.appendChild(el);
        if (persist !== false) rememberMessage("user", text, true);
        scrollToBottom();
    }

    function escapeHtml(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    /** Məhdud markdown → HTML. Mətn ƏVVƏL escape olunur; keçid yalnız «/…» və ya https://. */
    function renderMarkdown(text) {
        let html = escapeHtml(text);
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/(^|[^*])\*(?!\*)([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, linkText, url) => {
            const isLocal = url.startsWith("/") && !url.startsWith("//");
            const isHttps = url.startsWith("https://");
            if (!isLocal && !isHttps) return linkText;
            const extra = isHttps ? ' target="_blank" rel="noopener noreferrer"' : "";
            return '<a href="' + url + '" class="ai-msg-link"' + extra + ">" + linkText + "</a>";
        });
        const out = [];
        let inList = false;
        html.split("\n").forEach((line) => {
            const t = line.trim();
            if (/^[-*]\s+/.test(t)) {
                if (!inList) { out.push("<ul>"); inList = true; }
                out.push("<li>" + t.replace(/^[-*]\s+/, "") + "</li>");
                return;
            }
            if (inList) { out.push("</ul>"); inList = false; }
            if (t) out.push("<p>" + t + "</p>");
        });
        if (inList) out.push("</ul>");
        return out.join("");
    }

    function botRow(extraClass) {
        const el = document.createElement("div");
        el.className = "ai-msg ai-msg--bot" + (extraClass ? " " + extraClass : "");
        const avatar = document.createElement("div");
        avatar.className = "ai-msg-avatar";
        avatar.innerHTML = botAvatarSVG; // sabit, kod içi SVG — istifadəçi datası deyil
        const bubble = document.createElement("div");
        bubble.className = "ai-msg-bubble";
        el.appendChild(avatar);
        el.appendChild(bubble);
        return { el, bubble };
    }
    function addBotMessage(text, persist) {
        const row = botRow("");
        row.bubble.classList.add("ai-msg-bubble--rich");
        row.bubble.innerHTML = renderMarkdown(text); // escape edilmiş mətn + məhdud teqlər
        messagesEl.appendChild(row.el);
        if (persist !== false) rememberMessage("bot", text, false);
        scrollToBottom();
    }
    function showTyping() {
        const row = botRow("ai-msg-typing");
        row.el.id = "ai-typing-indicator";
        for (let i = 0; i < 3; i += 1) {
            const dot = document.createElement("span");
            dot.className = "ai-typing-dot";
            row.bubble.appendChild(dot);
        }
        messagesEl.appendChild(row.el);
        scrollToBottom();
    }
    function hideTyping() {
        const el = document.getElementById("ai-typing-indicator");
        if (el) el.remove();
    }
    function scrollToBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }

    // ── Vəziyyət / limit ────────────────────────────────────────────────
    function setStatus(state, label) {
        if (!statusEl) return;
        statusEl.dataset.state = state;
        const text = statusEl.querySelector(".ai-chat-status__text");
        if (text) text.textContent = label;
    }
    function showNotice(text) {
        if (!notice) return;
        if (noticeText) noticeText.textContent = text;
        notice.hidden = false;
    }
    function hideNotice() { if (notice) notice.hidden = true; }
    function setComposer(enabled) {
        inputWrap.hidden = !enabled;
    }

    function applyAvailability(enabled, configured) {
        isAvailable = Boolean(enabled) && Boolean(configured);
        if (isAvailable) {
            setStatus("online", uiText.online);
            return;
        }
        setStatus("offline", uiText.offline);
        showNotice(uiText.soonMessage);
        setComposer(false);
        if (limitBadge) limitBadge.hidden = true;
    }

    function updateLimitDisplay(remaining, limit) {
        const r = Number(remaining);
        const l = Number(limit);
        if (Number.isFinite(r) && Number.isFinite(l)) {
            remainingRequests = r;
            requestLimit = l;
            hasLoadedQuota = true;
            if (limitBadge) limitBadge.textContent = limitLabel + ": " + r + " / " + l;
        }
        if (!isAvailable) return;
        if (requestLimit !== null && requestLimit <= 0) {
            showNotice(uiText.limitDisabled);
            setComposer(false);
        } else if (remainingRequests !== null && remainingRequests <= 0) {
            showNotice(uiText.limitNotice);
            setComposer(false);
        } else {
            hideNotice();
            setComposer(true);
        }
    }

    async function readJsonResponse(resp) {
        const type = resp.headers.get("content-type") || "";
        if (type.includes("application/json")) return resp.json();
        return { error: "HTTP " + resp.status };
    }

    async function fetchQuota() {
        if (hasLoadedQuota || !quotaUrl) return;
        try {
            const resp = await fetch(quotaUrl, { method: "GET", credentials: "same-origin", headers: { Accept: "application/json" } });
            const data = await readJsonResponse(resp);
            if (data && typeof data === "object") {
                applyAvailability(data.enabled !== false, data.configured !== false);
                if (data.remaining_requests !== undefined) updateLimitDisplay(data.remaining_requests, data.limit);
            }
        } catch (err) {
            if (limitBadge) limitBadge.textContent = limitLabel + ": " + loadingLabel;
        }
    }

    // ── Göndərmə ────────────────────────────────────────────────────────
    async function sendMessage() {
        resetHistoryIfExpired();
        const text = inputEl.value.trim();
        if (!text || isLoading || !isAvailable) return;
        addUserMessage(text);
        inputEl.value = "";
        autoGrow();
        setLoading(true);
        showTyping();
        try {
            const resp = await fetch(chatUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
                // Yalnız YOL — sorğu sətri/fraqment serverə (və audit jurnalına) getmir.
                body: JSON.stringify({ message: text, current_page: window.location.pathname }),
            });
            const data = await readJsonResponse(resp);
            hideTyping();
            if (resp.status === 503 && data.error === "assistant_disabled") {
                applyAvailability(false, true);
                if (data.answer) addBotMessage(data.answer);
            } else if (resp.ok && data.answer) {
                addBotMessage(data.answer);
            } else if (data.error === "rate_limit_exceeded" && data.answer) {
                addBotMessage(data.answer);
            } else if (data.answer) {
                addBotMessage(data.answer);
            } else {
                addBotMessage(resp.ok ? uiText.genericError : uiText.sendFailed);
            }
            if (data.remaining_requests !== undefined) updateLimitDisplay(data.remaining_requests, data.limit);
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
        if (!loading && isAvailable) inputEl.focus();
    }
    function autoGrow() {
        inputEl.style.height = "auto";
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("input", autoGrow);
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    document.querySelectorAll(".ai-chat-org-logo img").forEach((img) => {
        img.addEventListener("error", () => {
            const logo = img.closest(".ai-chat-org-logo");
            if (logo) logo.classList.add("ai-chat-org-logo--fallback");
        }, { once: true });
    });

    loadStoredHistory();
    renderStoredHistory();
    window.setInterval(resetHistoryIfExpired, 60 * 1000);
})();
