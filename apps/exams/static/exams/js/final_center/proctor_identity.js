/**
 * İM monitoru — tələbə KİMLİYİ (şəkil / ad / qrup / nömrə) və proktorinq
 * göstəriciləri (risk xalı, «şübhəli», nəzarət siqnalı) üçün PAYLAŞILAN render
 * köməkçiləri. Zal monitoru, oturum monitoru və canlı snapshot modalı eyni
 * funksiyalardan istifadə edir ki, üç ekran eyni görünsün.
 *
 * Etiketlər server tərəfində tərcümə olunub `#fxc-proctor-i18n` JSON-undan
 * oxunur (JS-də sabit mətn yoxdur). Şəkil URL-i serverin icazəli marşrutudur
 * (exams:proctor_student_photo) — burada heç bir media yolu qurulmur.
 * Şəkil yüklənməsə (silinib / icazə yoxdur) baş hərflərə qayıdılır — inline
 * `onerror` YOX (CSP): sənəd səviyyəsində bir dəfə tutulan `error` hadisəsi.
 */
(function () {
    "use strict";

    if (window.FXCProctor) return;

    var labels = {};
    function readLabels() {
        var el = document.getElementById("fxc-proctor-i18n");
        if (!el) return;
        try { labels = JSON.parse(el.textContent) || {}; } catch (err) { labels = {}; }
    }
    readLabels();

    function t(key, fallback) {
        var value = labels[key];
        return value == null || value === "" ? fallback : value;
    }

    function esc(text) {
        var d = document.createElement("div");
        d.textContent = text == null ? "" : String(text);
        return d.innerHTML;
    }

    var SEVERITIES = ["critical", "high", "medium", "low", "info"];

    function severityLabel(sev) {
        var map = labels.severity || {};
        return map[sev] || sev || "";
    }

    function safePhotoUrl(url) {
        // Yalnız öz origin-imizdəki nisbi yol (serverin marşrutu) qəbul olunur.
        url = String(url || "");
        return url.charAt(0) === "/" && url.charAt(1) !== "/" ? url : "";
    }

    function initialsOf(data) {
        var ini = (data && data.initials) || "";
        if (ini) return ini;
        var name = String((data && (data.name || data.student_name)) || "?").trim();
        return name.charAt(0).toUpperCase() || "?";
    }

    /** Dairəvi şəkil (və ya baş hərflər). size: "sm" | "md" | "lg". */
    function avatarHtml(data, size, extraClass) {
        data = data || {};
        var cls = "fxc-ava fxc-ava--" + (size || "sm") + (extraClass ? " " + extraClass : "");
        if (data.flagged) cls += " fxc-ava--flagged";
        var url = safePhotoUrl(data.photo_url);
        var name = data.name || data.student_name || "";
        var ini = '<span class="fxc-ava__ini" aria-hidden="true">' + esc(initialsOf(data)) + "</span>";
        if (!url) {
            return '<span class="' + cls + '" title="' + esc(t("noPhoto", "")) + '">' + ini + "</span>";
        }
        return '<span class="' + cls + ' fxc-ava--photo">' + ini +
            '<img class="fxc-ava__img" src="' + esc(url) + '" alt="' + esc(name) + '" ' +
            'loading="lazy" decoding="async" referrerpolicy="no-referrer" draggable="false"></span>';
    }

    /** Heartbeat vəziyyəti → {cls, text} (yoxdursa null). */
    function heartbeatInfo(hb) {
        if (!hb || !hb.status || hb.status === "ok" || hb.status === "pending") return null;
        if (hb.status === "stale") return { cls: "stale", text: t("hbStale", "") };
        return { cls: "missing", text: t("hbMissing", "") };
    }

    /** Risk / şübhəli / heartbeat nişanları (kiçik «pill»lər). */
    function badgesHtml(row) {
        row = row || {};
        var out = [];
        if (row.flagged) {
            out.push('<span class="fxc-pbadge fxc-pbadge--flag"><i class="fas fa-flag" aria-hidden="true"></i> ' +
                esc(t("flagged", "")) + "</span>");
        }
        if (row.risk_score) {
            out.push('<span class="fxc-pbadge fxc-pbadge--risk fxc-pbadge--sev-' + esc(row.max_severity || "low") +
                '" title="' + esc(t("riskHint", "")) + '">' + esc(t("risk", "")) + " " + esc(row.risk_score) +
                (row.risk_threshold ? "/" + esc(row.risk_threshold) : "") + "</span>");
        }
        if (row.signal_count) {
            out.push('<span class="fxc-pbadge fxc-pbadge--sig">' + esc(row.signal_count) + " " +
                esc(t("signals", "")) + "</span>");
        }
        var hb = heartbeatInfo(row.heartbeat);
        if (hb) {
            out.push('<span class="fxc-pbadge fxc-pbadge--hb-' + hb.cls + '"><i class="fas fa-heart-crack" ' +
                'aria-hidden="true"></i> ' + esc(hb.text) + "</span>");
        }
        return out.join(" ");
    }

    /** Qrup · nömrə sətri (`noFallback` — qrup/nömrə yoxdursa istifadəçi adını yazma). */
    function metaLine(data, noFallback) {
        data = data || {};
        var parts = [];
        if (data.group) parts.push(esc(t("group", "")) + ": <b>" + esc(data.group) + "</b>");
        if (data.student_number) parts.push(esc(t("studentNumber", "")) + ": <b>" + esc(data.student_number) + "</b>");
        if (!parts.length && data.username && !noFallback) parts.push(esc(data.username));
        return parts.join(" · ");
    }

    /** Böyük kimlik kartı (modallar üçün). */
    function identityCardHtml(identity, extra) {
        identity = identity || {};
        extra = extra || {};
        var data = {
            name: identity.name, photo_url: identity.photo_url, initials: identity.initials,
            flagged: extra.risk && extra.risk.flagged
        };
        var riskRow = extra.risk ? {
            flagged: extra.risk.flagged, risk_score: extra.risk.score, risk_threshold: extra.risk.threshold,
            max_severity: extra.risk.max_severity, signal_count: extra.risk.signals, heartbeat: extra.heartbeat
        } : { heartbeat: extra.heartbeat };
        return '<div class="fxc-idcard">' + avatarHtml(data, "lg") +
            '<div class="fxc-idcard__body">' +
                '<div class="fxc-idcard__kicker">' + esc(t("identityTitle", "")) + "</div>" +
                '<div class="fxc-idcard__name">' + esc(identity.name || "—") + "</div>" +
                '<div class="fxc-idcard__meta">' + metaLine(identity, true) + "</div>" +
                (identity.username ? '<div class="fxc-idcard__user"><i class="fas fa-user" aria-hidden="true"></i> ' +
                    esc(identity.username) + "</div>" : "") +
                '<div class="fxc-idcard__badges">' + badgesHtml(riskRow) + "</div>" +
            "</div></div>";
    }

    /** Qayda + siqnal xronologiyası (ən yeni əvvəldə). */
    function timelineHtml(rows) {
        rows = rows || [];
        if (!rows.length) {
            return '<p class="fxc-tl__empty">' + esc(t("noEvents", "")) + "</p>";
        }
        return '<ol class="fxc-tl">' + rows.map(function (row) {
            var when = row.at || "";
            try { when = new Date(row.at).toLocaleTimeString(); } catch (err) { when = row.at || ""; }
            var sev = SEVERITIES.indexOf(row.severity) === -1 ? "low" : row.severity;
            var source = row.source === "signal" ? t("sourceSignal", "") : t("sourceRule", "");
            return '<li class="fxc-tl__item fxc-tl__item--' + esc(sev) + '">' +
                '<span class="fxc-tl__time">' + esc(when) + "</span>" +
                '<span class="fxc-tl__label">' + esc(row.label || row.code || "") + "</span>" +
                '<span class="fxc-tl__tags"><span class="fxc-tl__src fxc-tl__src--' + esc(row.source || "rule") + '">' +
                    esc(source) + "</span>" +
                    '<span class="fxc-tl__sev">' + esc(severityLabel(sev)) + "</span>" +
                    (row.counts ? '<span class="fxc-tl__counts">' + esc(t("counts", "")) + "</span>" : "") +
                "</span></li>";
        }).join("") + "</ol>";
    }

    function timelineSection(rows) {
        return '<section class="fxc-tl-wrap"><h4 class="fxc-tl-title"><i class="fas fa-timeline" aria-hidden="true"></i> ' +
            esc(t("timeline", "")) + "</h4>" + timelineHtml(rows) + "</section>";
    }

    // Şəkil yüklənməsə baş hərflər görünsün (img gizlənir, span qalır).
    document.addEventListener("error", function (evt) {
        var img = evt.target;
        if (!img || img.tagName !== "IMG" || !img.classList.contains("fxc-ava__img")) return;
        var holder = img.parentNode;
        if (holder && holder.classList) holder.classList.remove("fxc-ava--photo");
        img.remove();
    }, true);

    window.FXCProctor = {
        t: t,
        esc: esc,
        avatarHtml: avatarHtml,
        badgesHtml: badgesHtml,
        heartbeatInfo: heartbeatInfo,
        metaLine: metaLine,
        identityCardHtml: identityCardHtml,
        timelineHtml: timelineHtml,
        timelineSection: timelineSection,
        severityLabel: severityLabel,
        reloadLabels: readLabels
    };
})();
