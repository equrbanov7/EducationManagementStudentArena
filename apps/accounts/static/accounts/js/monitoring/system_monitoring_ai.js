/* system_monitoring_ai.js — «AI ilə təhlil et» (sahib 2026-10-01).
 *
 * Düymə «Ümumi vəziyyət» bannerindədir; basanda `POST ai-analysis/` serverdə
 * TƏMİZLƏNMİŞ xülasəni (yalnız aqreqat saylar) Gemini-yə göndərir və Azərbaycan
 * dilində hesabat qaytarır. Cavab TƏHLÜKƏSİZ render olunur: əvvəl tam escape
 * (`& < > " '`), sonra məhdud markdown (qalın/kursiv/kod, başlıq, siyahılar);
 * keçid yalnız yerli «/…» (amma «//» və «/\» YOX — brauzer onları xarici host
 * kimi açır) və ya https:// olduqda — `static/js/ai_assistant.js` ilə eyni qayda.
 * Nəticə modul vəziyyətində saxlanılır: 30 s-lik avto-yeniləmə paneli silmir.
 */
(function () {
    "use strict";

    var namespace = window.EMSSystemMonitoring = window.EMSSystemMonitoring || {};
    var SEVERITY_TONE = { normal: "ok", low: "info", medium: "warning", high: "problem", critical: "problem" };
    var state = { loading: false, result: null, error: "", quota: null, body: null, ai: {}, ctx: null };

    function escapeHtml(text) {
        return String(text == null ? "" : text)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function inline(html) {
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/(^|[^*])\*(?!\*)([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        return html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (match, text, url) {
            // «/\host» brauzerdə «//host» kimi açılır (xarici sayt) — yerli sayılmır.
            var isLocal = url.charAt(0) === "/" && url.indexOf("//") !== 0 && url.indexOf("/\\") !== 0;
            var isHttps = url.indexOf("https://") === 0;
            if (!isLocal && !isHttps) return text;
            return '<a href="' + url + '"' + (isHttps ? ' target="_blank" rel="noopener noreferrer"' : "") + ">" + text + "</a>";
        });
    }

    /** Məhdud markdown → HTML. Mətn ƏVVƏL escape olunur, sonra yalnız sabit teqlər əlavə edilir. */
    function renderMarkdown(text) {
        var out = [];
        var list = "";
        function closeList() {
            if (list) { out.push("</" + list + ">"); list = ""; }
        }
        escapeHtml(text).split("\n").forEach(function (line) {
            var trimmed = line.trim();
            var heading = /^#{1,4}\s+(.*)$/.exec(trimmed);
            var bullet = /^[-*•]\s+(.*)$/.exec(trimmed);
            var ordered = /^\d+[.)]\s+(.*)$/.exec(trimmed);
            if (heading) {
                closeList();
                out.push('<h5 class="smx-md__h">' + inline(heading[1]) + "</h5>");
            } else if (bullet || ordered) {
                var kind = bullet ? "ul" : "ol";
                if (list !== kind) { closeList(); out.push("<" + kind + ">"); list = kind; }
                out.push("<li>" + inline((bullet || ordered)[1]) + "</li>");
            } else {
                closeList();
                if (trimmed) out.push("<p>" + inline(trimmed) + "</p>");
            }
        });
        closeList();
        return out.join("");
    }

    function t(key) {
        return state.ctx ? state.ctx.t(key) : key;
    }

    function quota() {
        return state.quota || { remaining: state.ai.remaining, limit: state.ai.limit };
    }

    function renderActions() {
        var actions = state.body && state.body.querySelector("[data-smx-ai-actions]");
        if (!actions) return;
        var ai = state.ai || {};
        var available = ai.enabled && ai.configured;
        var left = quota();
        var disabled = !available || state.loading || left.remaining === 0;
        var hint = !ai.enabled ? t("aiDisabled") : !ai.configured ? t("aiNotConfigured") :
            left.limit ? state.ctx.fmt(t("aiRemaining"), { remaining: left.remaining, limit: left.limit }) : "";
        actions.innerHTML = '<button type="button" class="ems-btn ems-btn--primary smx-ai-btn" data-smx-ai' +
            (disabled ? " disabled" : "") + '><i class="fas ' + (state.loading ? "fa-spinner fa-spin" : "fa-wand-magic-sparkles") +
            '" aria-hidden="true"></i> ' + escapeHtml(t("aiButton")) + "</button>" +
            (hint ? '<span class="smx-ai-quota">' + escapeHtml(hint) + "</span>" : "");
        var button = actions.querySelector("[data-smx-ai]");
        if (button && !disabled) button.addEventListener("click", run);
    }

    function renderPanel() {
        var panel = state.body && state.body.querySelector("[data-smx-ai-panel]");
        if (!panel) return;
        if (!state.loading && !state.result && !state.error) {
            panel.innerHTML = "";
            return;
        }
        var head = '<header class="smx-ai__head"><h4 class="smx-ai__title"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>' +
            escapeHtml(t("aiTitle")) + "</h4>";
        var content;
        if (state.loading) {
            content = '<div class="smx-ai__loading" role="status"><span class="skeleton skeleton-line skeleton-line--lg"></span>' +
                '<span class="skeleton skeleton-line skeleton-line--md"></span><span class="skeleton skeleton-line skeleton-line--sm"></span>' +
                "<p>" + escapeHtml(t("aiRunning")) + "</p></div>";
        } else if (state.error) {
            content = '<p class="smx-ai__error" role="alert"><i class="fas fa-circle-exclamation" aria-hidden="true"></i> ' +
                escapeHtml(state.error) + "</p>";
        } else {
            var result = state.result;
            var tone = SEVERITY_TONE[result.severity] || "";
            if (result.severity_label) {
                head += '<span class="smx-state smx-state--' + (tone || "unknown") + '"><span class="smx-state__dot" aria-hidden="true"></span>' +
                    escapeHtml(t("aiSeverity")) + ": " + escapeHtml(result.severity_label) + "</span>";
            }
            var when = result.generated_at ? new Date(result.generated_at).toLocaleTimeString("az") : "";
            content = '<div class="smx-md">' + renderMarkdown(result.answer || "") + "</div>" +
                '<p class="smx-ai__meta">' + (when ? escapeHtml(state.ctx.fmt(t("aiGenerated"), { time: when })) + " · " : "") +
                escapeHtml(t("aiNote")) + "</p>";
        }
        if (!state.loading) {
            head += '<button type="button" class="smx-btn smx-ai__close" data-smx-ai-close aria-label="' + escapeHtml(t("aiClose")) +
                '"><i class="fas fa-xmark" aria-hidden="true"></i></button>';
        }
        // Canlı region konteynerin özüdür (`[data-smx-ai-panel]`, summary.js) — istifadəçinin
        // başlatdığı «yüklənir → hesabat» keçidi elan olunur, avto-yeniləmə isə yox.
        panel.innerHTML = '<section class="smx-ai">' + head + "</header>" + content + "</section>";
        var close = panel.querySelector("[data-smx-ai-close]");
        if (close) {
            close.addEventListener("click", function () {
                state.result = null;
                state.error = "";
                renderPanel();
            });
        }
    }

    function run() {
        if (state.loading || !state.ctx) return;
        state.loading = true;
        state.error = "";
        renderActions();
        renderPanel();
        fetch(state.ctx.api + "ai-analysis/", {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": state.ctx.csrf, Accept: "application/json" },
        }).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (payload) {
                return { ok: response.ok, payload: payload || {} };
            });
        }).then(function (reply) {
            var payload = reply.payload;
            var data = payload.data || payload;
            if (data.limit != null) state.quota = { remaining: data.remaining, limit: data.limit };
            if (reply.ok && payload.status === "ok") {
                state.result = payload.data;
            } else {
                state.error = payload.message || t("aiError");
            }
        }).catch(function () {
            state.error = t("aiError");
        }).then(function () {
            state.loading = false;
            renderActions();
            renderPanel();
        });
    }

    namespace.ai = {
        renderMarkdown: renderMarkdown,
        escapeHtml: escapeHtml,
        mount: function (body, ai, ctx) {
            state.body = body;
            state.ai = ai || {};
            state.ctx = ctx;
            // Xülasə hər yenilənmədə serverdən təzə kvota gətirir — o, həqiqət mənbəyidir.
            if (state.ai.limit != null && !state.loading) state.quota = null;
            renderActions();
            renderPanel();
        },
        reset: function () {
            state = { loading: false, result: null, error: "", quota: null, body: null, ai: {}, ctx: null };
        },
    };

    if (typeof namespace.bootPending === "function") {
        namespace.bootPending();
    }
})();
