/* İnternet kəsilməsi nəzarət pozuntusu DEYİL (sahib 2026-11-20, QuizPython577E).
 *
 * Sahib: «İnternet gedəndə full screen çıxmaq ya da bal bərpa etmək olmur, problem olur».
 * Əvvəl: bağlantı kəsiləndə tələbə Wi-Fi-ı düzəltmək üçün tam ekrandan çıxırdı → güzəşt sayğacı hər
 * 15 s-dən bir pozuntu artırırdı, brauzer sayğacı limitə çatanda səhifəni ÖZÜ kilidləyirdi (server heç
 * nə bilmədən) və bağlantı qayıdan kimi gecikmiş hadisələr sayılırdı.
 *
 * İndi:
 *   • bağlantı yoxdur (`offline` hadisəsi və ya nəzarət sorğusunun şəbəkə xətası) → tam ekrandan çıxış,
 *     tab/pəncərə dəyişmə SAYILMIR, güzəşt sayğacı dayanır, xəbərdarlıq «bağlantı yoxdur» rejiminə keçir;
 *   • bağlantı qayıdanda RECONNECT_GRACE_MS ərzində tələbəyə «tam ekrana qayıt» pəncərəsi göstərilir
 *     (tam ekran yalnız istifadəçi toxunuşu ilə açılır), vaxtında qayıtmasa adi qayda işləyir;
 *   • kəsilmənin izi nəzarətçiyə siqnal kimi gedir (`network_offline`: müddət, tam ekrandan/səhifədən
 *     çıxıbmı) — kilidləmir, sayğaca düşmür;
 *   • cavab növbəsi: `ems:network-restored` hadisəsi autosave-i dərhal göndərtdirir (take_exam/draft.js).
 * Server sayğacı avtoritativdir (api.js) — burada yalnız klientin «nə göndərim» qərarı dəyişir. */
import { ExamSupervision } from "./state.js?v=20260914-w4r3";

var RECONNECT_GRACE_MS = 30000;

function texts() {
    return window.SUPERVISION_ACK_I18N || {};
}

function node(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
}

Object.assign(ExamSupervision, {
    _netDown: false,
    _netEpisode: null,
    _netGraceUntil: 0,
    _netGraceTimer: null,
    _netWatchBound: false,
    _reconnectGraceMs: RECONNECT_GRACE_MS,

    _bindNetworkWatch: function () {
        if (this._netWatchBound) return;
        this._netWatchBound = true;
        var self = this;
        window.addEventListener("offline", function () { self._markNetworkDown("offline_event"); });
        window.addEventListener("online", function () { self._markNetworkUp(); });
        if (navigator.onLine === false) this._markNetworkDown("offline_event");
    },

    /** Bağlantı yoxdur və ya yenicə qayıdıb — çıxış hadisələri pozuntu kimi göndərilmir. */
    _isNetworkExempt: function () {
        return this._netDown || Date.now() < this._netGraceUntil;
    },

    _noteNetworkEpisode: function (key) {
        if (this._netEpisode) this._netEpisode[key] = true;
    },

    _markNetworkDown: function (source) {
        if (this._netDown) return;
        this._netDown = true;
        this._netEpisode = { since: Date.now(), source: source || "fetch", fsExit: false, hidden: false };
        this._cancelReconnectGrace();
        // Güzəşt sayğacı işləyirdisə (tam ekrandan çıxıb) — dayandır, xəbərdarlıq «bağlantı yoxdur» olur.
        if (this.graceTimer || (this.config && this.config.force_fullscreen && this._acknowledged &&
                this.isActive && !this._isFullscreenActive())) {
            this._clearGraceTimer();
            this._noteNetworkEpisode("fsExit");
            this._showOfflineWarning();
        }
    },

    _markNetworkUp: function () {
        if (!this._netDown) return;
        this._netDown = false;
        var episode = this._netEpisode || { since: Date.now() };
        this._netEpisode = null;
        this._netGraceUntil = Date.now() + this._reconnectGraceMs;
        this._reportNetworkEpisode(episode);
        try {
            document.dispatchEvent(new CustomEvent("ems:network-restored"));
        } catch (e) {}
        if (this._onTransportStateChange) this._onTransportStateChange(true);
        this._afterReconnect();
    },

    _reportNetworkEpisode: function (episode) {
        var signals = window.EMSProctorSignals;
        if (!signals || typeof signals.signal !== "function" || !signals.cfg) return;
        signals.signal("network_offline", {
            seconds: Math.max(0, Math.round((Date.now() - episode.since) / 1000)),
            fs_exit: !!episode.fsExit,
            left_page: !!episode.hidden,
            source: episode.source || ""
        }, "net:" + episode.since);
    },

    _showOfflineWarning: function () {
        if (!this.warningModal || !this._acknowledged || !this.isActive) return;
        var t = texts();
        this.warningModal.classList.add("is-offline");
        this._showWarning(
            t.offlineTitle || "İnternet bağlantısı kəsildi",
            t.offlineMsg || "Cavablarınız bu kompüterdə saxlanılır. Bağlantı qayıdanda tam ekrana qayıdın — bu pozuntu sayılmır."
        );
    },

    _clearOfflineWarning: function () {
        if (this.warningModal) this.warningModal.classList.remove("is-offline");
    },

    _hasBlockingOverlay: function () {
        return !!(
            document.getElementById("supervision-locked-overlay") ||
            document.getElementById("supervision-teacher-lock-overlay") ||
            document.getElementById("supervision-resume-overlay")
        );
    },

    _afterReconnect: function () {
        var self = this;
        this._clearOfflineWarning();
        var needsFullscreen = !!(this.config && this.config.force_fullscreen);
        if (!this._acknowledged || !this.isActive || !needsFullscreen || this._isFullscreenActive()) {
            if (this._isFullscreenActive()) this._hideWarning();
            return;
        }
        this._hideWarning();
        if (!this._hasBlockingOverlay()) this._showReconnectOverlay();
        this._netGraceTimer = window.setTimeout(function () {
            self._netGraceTimer = null;
            self._netGraceUntil = 0;
            self._removeReconnectOverlay();
            // Vaxtında qayıtmadı → adi qayda: xəbərdarlıq + pozuntu + güzəşt sayğacı.
            if (self.isActive && !self._netDown && self.config.force_fullscreen &&
                    !self._isFullscreenActive() && !self.graceTimer) {
                self._showWarning();
                self._logEvent("fullscreen_exited", { after_reconnect: true });
                self._startGraceTimer();
            }
        }, this._reconnectGraceMs);
    },

    _cancelReconnectGrace: function () {
        if (this._netGraceTimer) {
            window.clearTimeout(this._netGraceTimer);
            this._netGraceTimer = null;
        }
        this._removeReconnectOverlay();
    },

    /** Tələbə tam ekrana qayıtdı (event_capture `_onFullscreenChange`). */
    _onFullscreenRegained: function () {
        this._clearOfflineWarning();
        if (this._netGraceTimer || document.getElementById("supervision-reconnect-overlay")) {
            this._cancelReconnectGrace();
            this._netGraceUntil = 0;
        }
    },

    _removeReconnectOverlay: function () {
        var overlay = document.getElementById("supervision-reconnect-overlay");
        if (overlay) overlay.remove();
    },

    _showReconnectOverlay: function () {
        if (document.getElementById("supervision-reconnect-overlay")) return;
        var self = this;
        var t = texts();
        var overlay = node("div", "supervision-net-overlay");
        overlay.id = "supervision-reconnect-overlay";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        var card = node("div", "supervision-net-card");
        var icon = node("i", "fas fa-wifi supervision-net-card__icon");
        icon.setAttribute("aria-hidden", "true");
        card.appendChild(icon);
        card.appendChild(node("h2", "supervision-net-card__title", t.reconnectTitle || "Bağlantı bərpa olundu"));
        card.appendChild(node("p", "supervision-net-card__text",
            t.reconnectMsg || "Davam etmək üçün tam ekrana qayıdın. Bağlantının kəsilməsi pozuntu sayılmadı."));
        var button = node("button", "supervision-net-card__btn", t.resumeBtn || "Tam ekrana keç və davam et");
        button.type = "button";
        button.addEventListener("click", function () {
            self._requestFullscreen().then(function (ok) {
                if (ok || self._isFullscreenActive()) self._onFullscreenRegained();
            });
        });
        card.appendChild(button);
        overlay.appendChild(card);
        document.body.appendChild(overlay);
    }
});

// Modul yüklənəndə bir dəfə (state.js-ə toxunmadan — idempotentdir).
ExamSupervision._bindNetworkWatch();
