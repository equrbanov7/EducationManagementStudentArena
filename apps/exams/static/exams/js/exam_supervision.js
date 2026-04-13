/**
 * Exam Supervision Module
 *
 * Browser-based anti-cheating enforcement for supervised exams.
 * Handles fullscreen, focus detection, copy/paste blocking,
 * right-click prevention, keyboard shortcut restriction, and
 * violation tracking with server-side logging.
 *
 * Usage: Call ExamSupervision.init(config) after DOM is ready.
 */
(function (window) {
    "use strict";

    var ExamSupervision = {
        config: null,
        attemptId: null,
        csrfToken: "",
        logEndpoint: "",
        statusEndpoint: "",
        violationCount: 0,
        maxViolations: 3,
        gracePeriodSeconds: 15,
        graceTimer: null,
        warningModal: null,
        isActive: false,
        isFullscreen: false,
        _acknowledged: false,
        _initialized: false,
        _initialStatus: "active",
        _thresholdWarned: false,

        /**
         * Initialize the supervision module.
         * @param {Object} opts - Configuration from server
         */
        init: function (opts) {
            // Prevent double initialization
            if (this._initialized) return;
            this._initialized = true;

            this.config = opts.config || {};
            this.attemptId = opts.attemptId;
            this.csrfToken = opts.csrfToken;
            this.logEndpoint = opts.logEndpoint;
            this.statusEndpoint = opts.statusEndpoint;
            this.violationCount = opts.violationCount || 0;
            this.maxViolations = opts.maxViolations || 3;
            this.gracePeriodSeconds = this.config.grace_period_seconds || 15;
            this._initialStatus = opts.supervisionStatus || "active";
            this.isActive = true;
            this._acknowledged = false;

            this._createWarningModal();
            this._createSupervisionBadge();

            // If attempt is already locked/removed, show locked overlay immediately
            if (this._initialStatus === "locked" || this._initialStatus === "removed") {
                this._acknowledged = true;
                this._bindEvents();
                this._onLimitExceeded();
                return;
            }

            // Show acknowledgment overlay - events bind AFTER student acknowledges
            this._showAcknowledgment();
        },

        _createWarningModal: function () {
            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var warningTitle = i18n.warningTitle || "\u26a0\ufe0f X\u0259b\u0259rdarliq";
            var warningMsg = i18n.warningMsg || "\u0130mtahan sah\u0259sind\u0259n \u00e7\u0131xd\u0131n\u0131z. Z\u0259hm\u0259t olmasa geri qay\u0131d\u0131n.";
            var warningTimeout = i18n.warningTimeout || "Vaxt bit\u0259rs\u0259, bu pozuntu kimi qeyd olunacaq.";
            var warningViolation = i18n.warningViolation || "Pozuntu";
            var warningReturn = i18n.warningReturn || "Tam ekrana qay\u0131t";

            var modal = document.createElement("div");
            modal.id = "supervision-warning-modal";
            modal.style.cssText =
                "display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);" +
                "z-index:99999;justify-content:center;align-items:center;";
            modal.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2rem;max-width:500px;width:90%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.3);">' +
                '<div style="font-size:3rem;color:#dc3545;margin-bottom:1rem;"><i class="fas fa-exclamation-triangle"></i></div>' +
                '<h2 style="color:#dc3545;margin-bottom:0.5rem;" id="supervision-warning-title">' + warningTitle + '</h2>' +
                '<p id="supervision-warning-message" style="color:#333;margin-bottom:1rem;">' + warningMsg + '</p>' +
                '<div style="font-size:2.5rem;font-weight:bold;color:#dc3545;margin:1rem 0;" id="supervision-countdown">' + this.gracePeriodSeconds + '</div>' +
                '<p style="color:#666;font-size:0.9rem;">' + warningTimeout + '</p>' +
                '<div style="margin-top:1rem;">' +
                '<span style="background:#ffeeba;color:#856404;padding:0.3rem 0.8rem;border-radius:20px;font-size:0.85rem;" id="supervision-violation-badge">' +
                warningViolation + ": 0 / " + this.maxViolations + "</span></div>" +
                '<button id="supervision-return-btn" style="margin-top:1.5rem;padding:0.75rem 2rem;background:#28a745;color:#fff;border:none;border-radius:8px;font-size:1rem;cursor:pointer;">' +
                '<i class="fas fa-expand"></i> ' + warningReturn + '</button>' +
                "</div>";
            document.body.appendChild(modal);
            this.warningModal = modal;
            this._violationLabel = warningViolation;

            document.getElementById("supervision-return-btn").addEventListener("click", function () {
                ExamSupervision._requestFullscreen();
            });
        },

        _createSupervisionBadge: function () {
            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var badgeText = i18n.badgeActive || "N\u0259zar\u0259t aktiv";

            var badge = document.createElement("div");
            badge.id = "supervision-active-badge";
            badge.style.cssText =
                "position:fixed;top:60px;right:10px;z-index:9999;background:#dc3545;color:#fff;" +
                "padding:0.4rem 0.8rem;border-radius:20px;font-size:0.8rem;display:flex;align-items:center;gap:0.4rem;" +
                "box-shadow:0 2px 10px rgba(220,53,69,0.3);";
            badge.innerHTML =
                '<i class="fas fa-shield-alt"></i> <span>' + badgeText + '</span>' +
                ' <span id="supervision-badge-count" style="background:rgba(255,255,255,0.2);padding:0.1rem 0.4rem;border-radius:10px;font-size:0.75rem;">' +
                this.violationCount + '/' + this.maxViolations + "</span>";
            document.body.appendChild(badge);
        },

        _showAcknowledgment: function () {
            // Prevent duplicate acknowledgment overlays
            if (document.getElementById("supervision-acknowledgment")) return;

            var self = this;
            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var titleText = i18n.title || "N\u0259zar\u0259t Rejimi Aktiv";
            var descText = i18n.desc || "Bu imtahan <strong>n\u0259zar\u0259t rejimind\u0259</strong> ke\u00e7irilir. A\u015fa\u011f\u0131dak\u0131 qaydalar t\u0259tbiq olunur:";
            var ruleFullscreen = i18n.ruleFullscreen || "Tam ekran rejimi t\u0259l\u0259b olunur";
            var ruleTab = i18n.ruleTab || "Tab d\u0259yi\u015fm\u0259 izl\u0259nilir";
            var ruleCopy = i18n.ruleCopy || "Kopyala/yap\u0131\u015fd\u0131r bloklan\u0131b";
            var ruleRightClick = i18n.ruleRightClick || "Sa\u011f klik deaktivdir";
            var ruleKeyboard = i18n.ruleKeyboard || "Klaviatura q\u0131sa yollar\u0131 m\u0259hduddur";

            // Build max violation text with actual count
            var maxViolationText = i18n.maxViolation || "";
            if (maxViolationText && maxViolationText.indexOf("{count}") !== -1) {
                maxViolationText = maxViolationText.replace("{count}", this.maxViolations);
            } else {
                maxViolationText = "Maksimum " + this.maxViolations + " pozuntuya icaz\u0259 verilir.";
            }

            var btnText = i18n.btnText || "Ba\u015fa d\u00fc\u015fd\u00fcm, davam et";

            var overlay = document.createElement("div");
            overlay.id = "supervision-acknowledgment";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);" +
                "z-index:100000;display:flex;justify-content:center;align-items:center;";

            var contentDiv = document.createElement("div");
            contentDiv.style.cssText =
                "background:#fff;border-radius:12px;padding:2.5rem;max-width:550px;width:90%;text-align:center;";
            contentDiv.innerHTML =
                '<div style="font-size:3rem;color:#007bff;margin-bottom:1rem;"><i class="fas fa-shield-alt"></i></div>' +
                '<h2 style="color:#333;">' + titleText + "</h2>" +
                '<p style="color:#555;margin:1rem 0;">' + descText + "</p>" +
                '<ul style="text-align:left;color:#555;margin:1rem 2rem;">' +
                (this.config.force_fullscreen ? "<li>" + ruleFullscreen + "</li>" : "") +
                (this.config.detect_tab_switch ? "<li>" + ruleTab + "</li>" : "") +
                (this.config.block_copy_paste ? "<li>" + ruleCopy + "</li>" : "") +
                (this.config.disable_right_click ? "<li>" + ruleRightClick + "</li>" : "") +
                (this.config.restrict_keyboard_shortcuts ? "<li>" + ruleKeyboard + "</li>" : "") +
                "</ul>" +
                '<p style="color:#dc3545;font-weight:bold;font-size:1.05rem;">' + maxViolationText + "</p>";

            // Create button via DOM API for reliable event binding
            var acknowledgeBtn = document.createElement("button");
            acknowledgeBtn.type = "button";
            acknowledgeBtn.id = "supervision-acknowledge-btn";
            acknowledgeBtn.style.cssText =
                "margin-top:1.5rem;padding:0.75rem 2rem;background:#007bff;color:#fff;" +
                "border:none;border-radius:8px;font-size:1.1rem;cursor:pointer;min-width:250px;";
            acknowledgeBtn.innerHTML = '<i class="fas fa-check"></i> ' + btnText;

            acknowledgeBtn.onclick = function () {
                // Disable button to prevent double-clicks
                if (acknowledgeBtn.disabled) return;
                acknowledgeBtn.disabled = true;
                acknowledgeBtn.style.opacity = "0.7";
                acknowledgeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ...';

                // Request fullscreen FIRST (required before allowing exam)
                if (self.config.force_fullscreen) {
                    try {
                        var el = document.documentElement;
                        var fsPromise;
                        if (el.requestFullscreen) {
                            fsPromise = el.requestFullscreen();
                        } else if (el.webkitRequestFullscreen) {
                            fsPromise = el.webkitRequestFullscreen();
                        }
                        if (fsPromise && typeof fsPromise.then === "function") {
                            fsPromise.then(function () {
                                self._completeAcknowledgment(overlay);
                            }).catch(function () {
                                // Fullscreen failed - still allow but enforce later
                                self._completeAcknowledgment(overlay);
                            });
                            return;
                        }
                    } catch (e) {
                        // Fullscreen API not available
                    }
                }
                self._completeAcknowledgment(overlay);
            };

            contentDiv.appendChild(acknowledgeBtn);
            overlay.appendChild(contentDiv);
            document.body.appendChild(overlay);
        },

        _completeAcknowledgment: function (overlay) {
            // Mark as acknowledged
            this._acknowledged = true;

            // Remove overlay so exam content is accessible
            if (overlay && overlay.parentNode) overlay.remove();

            // Bind violation detection events
            this._bindEvents();

            // Log exam start and acknowledgment
            this._logEvent("exam_started_supervised", { timestamp: new Date().toISOString() });
            this._logEvent("student_acknowledged");

            // Update badge immediately with current violation count
            this._updateBadge();

            // If fullscreen is required but not active, show warning immediately
            if (this.config.force_fullscreen) {
                var isFS = !!document.fullscreenElement || !!document.webkitFullscreenElement;
                if (!isFS) {
                    this._showWarning();
                    this._startGraceTimer();
                }
            }
        },

        _bindEvents: function () {
            var self = this;

            // Fullscreen change
            document.addEventListener("fullscreenchange", function () { self._onFullscreenChange(); });
            document.addEventListener("webkitfullscreenchange", function () { self._onFullscreenChange(); });

            // Visibility / focus
            if (this.config.detect_tab_switch) {
                document.addEventListener("visibilitychange", function () { self._onVisibilityChange(); });
                window.addEventListener("blur", function () { self._onWindowBlur(); });
                window.addEventListener("focus", function () { self._onWindowFocus(); });
            }

            // Copy/Paste
            if (this.config.block_copy_paste) {
                document.addEventListener("copy", function (e) { self._onCopy(e); });
                document.addEventListener("paste", function (e) { self._onPaste(e); });
                document.addEventListener("cut", function (e) { self._onCut(e); });
            }

            // Right click
            if (this.config.disable_right_click) {
                document.addEventListener("contextmenu", function (e) { self._onContextMenu(e); });
            }

            // Text selection
            if (this.config.disable_text_selection) {
                document.addEventListener("selectstart", function (e) { self._onSelectStart(e); });
                document.addEventListener("dragstart", function (e) { self._onDragStart(e); });
            }

            // Keyboard shortcuts
            if (this.config.restrict_keyboard_shortcuts) {
                document.addEventListener("keydown", function (e) { self._onKeyDown(e); });
            }
        },

        _onFullscreenChange: function () {
            if (!this._acknowledged) return;

            var isFS =
                !!document.fullscreenElement || !!document.webkitFullscreenElement;
            this.isFullscreen = isFS;

            if (!isFS && this.config.force_fullscreen && this.isActive) {
                // Only start grace timer if not already running
                if (!this.graceTimer) {
                    this._showWarning();
                    this._logEvent("fullscreen_exited");
                    this._startGraceTimer();
                }
            } else if (isFS) {
                this._hideWarning();
                this._clearGraceTimer();
                this._logEvent("fullscreen_restored");
            }
        },

        _onVisibilityChange: function () {
            if (!this._acknowledged) return;
            if (document.hidden && this.isActive) {
                this._logEvent("tab_switched");
                this._incrementViolation();
            }
        },

        _onWindowBlur: function () {
            if (!this._acknowledged) return;
            if (this.isActive) {
                this._logEvent("window_blurred");
            }
        },

        _onWindowFocus: function () {
            if (!this._acknowledged) return;
            if (this.isActive) {
                this._logEvent("window_focused");
                this._checkSupervisionStatus();
            }
        },

        _isEditableField: function (target) {
            return target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
        },

        _onCopy: function (e) {
            if (this._isEditableField(e.target)) return;
            e.preventDefault();
            this._logEvent("copy_attempt");
            this._incrementViolation();
        },

        _onPaste: function (e) {
            e.preventDefault();
            this._logEvent("paste_attempt");
            this._incrementViolation();
        },

        _onCut: function (e) {
            if (this._isEditableField(e.target)) return;
            e.preventDefault();
            this._logEvent("cut_attempt");
            this._incrementViolation();
        },

        _onContextMenu: function (e) {
            e.preventDefault();
            this._logEvent("right_click_attempt");
        },

        _onSelectStart: function (e) {
            if (this._isEditableField(e.target)) return;
            e.preventDefault();
        },

        _onDragStart: function (e) {
            e.preventDefault();
        },

        _onKeyDown: function (e) {
            var blocked = [
                { ctrl: true, key: "c" },
                { ctrl: true, key: "v" },
                { ctrl: true, key: "x" },
                { ctrl: true, key: "p" },
                { ctrl: true, key: "s" },
                { ctrl: true, key: "u" },
                { ctrl: true, shift: true, key: "i" },
                { ctrl: true, shift: true, key: "j" },
                { key: "F12" },
                { key: "PrintScreen" },
            ];

            for (var idx = 0; idx < blocked.length; idx++) {
                var combo = blocked[idx];
                var ctrlMatch = combo.ctrl ? e.ctrlKey || e.metaKey : true;
                var shiftMatch = combo.shift === undefined || combo.shift === e.shiftKey;
                var keyMatch = e.key && e.key.toLowerCase() === combo.key.toLowerCase();

                if (ctrlMatch && shiftMatch && keyMatch) {
                    if (
                        (combo.key === "c" || combo.key === "v" || combo.key === "x") &&
                        this._isEditableField(e.target)
                    ) {
                        if (!this.config.block_copy_paste) return;
                    }
                    e.preventDefault();
                    e.stopPropagation();
                    this._logEvent("keyboard_shortcut", {
                        key: e.key,
                        ctrl: e.ctrlKey,
                        shift: e.shiftKey,
                        meta: e.metaKey,
                    });
                    return false;
                }
            }
        },

        _requestFullscreen: function () {
            try {
                var el = document.documentElement;
                if (el.requestFullscreen) {
                    el.requestFullscreen().catch(function () {});
                } else if (el.webkitRequestFullscreen) {
                    el.webkitRequestFullscreen();
                }
            } catch (e) {}
        },

        _showWarning: function (title, message) {
            if (!this.warningModal) return;
            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var defaultTitle = i18n.warningTitle || "\u26a0\ufe0f X\u0259b\u0259rdarliq";
            var defaultMsg = i18n.warningMsg || "\u0130mtahan sah\u0259sind\u0259n \u00e7\u0131xd\u0131n\u0131z. Z\u0259hm\u0259t olmasa geri qay\u0131d\u0131n.";
            document.getElementById("supervision-warning-title").textContent = title || defaultTitle;
            document.getElementById("supervision-warning-message").textContent = message || defaultMsg;
            document.getElementById("supervision-violation-badge").textContent =
                (this._violationLabel || "Pozuntu") + ": " + this.violationCount + " / " + this.maxViolations;
            this.warningModal.style.display = "flex";
        },

        _hideWarning: function () {
            if (this.warningModal) {
                this.warningModal.style.display = "none";
            }
        },

        _startGraceTimer: function () {
            this._clearGraceTimer();
            var remaining = this.gracePeriodSeconds;
            var countdownEl = document.getElementById("supervision-countdown");
            if (countdownEl) countdownEl.textContent = remaining;

            this.graceTimer = setInterval(
                function () {
                    remaining--;
                    if (countdownEl) countdownEl.textContent = remaining;
                    if (remaining <= 0) {
                        ExamSupervision._clearGraceTimer();
                        ExamSupervision._onGracePeriodExpired();
                    }
                },
                1000
            );
        },

        _clearGraceTimer: function () {
            if (this.graceTimer) {
                clearInterval(this.graceTimer);
                this.graceTimer = null;
            }
        },

        _onGracePeriodExpired: function () {
            this._logEvent("grace_period_expired");
            this._incrementViolation();
            this._hideWarning();
            // If fullscreen required and still not in fullscreen, lock the exam
            if (this.config.force_fullscreen && this.isActive) {
                var isFS = !!document.fullscreenElement || !!document.webkitFullscreenElement;
                if (!isFS) {
                    this._onLimitExceeded();
                }
            }
        },

        _incrementViolation: function () {
            this.violationCount++;
            this._updateBadge();

            // Show attention-grabbing warning at 75% threshold
            if (!this._thresholdWarned && this.maxViolations > 0) {
                var threshold = Math.ceil(this.maxViolations * 0.75);
                if (this.violationCount >= threshold && this.violationCount < this.maxViolations) {
                    this._thresholdWarned = true;
                    this._showThresholdWarning();
                }
            }

            if (this.violationCount >= this.maxViolations) {
                this._onLimitExceeded();
            }
        },

        _updateBadge: function () {
            var badge = document.getElementById("supervision-badge-count");
            if (badge) {
                badge.textContent = this.violationCount + "/" + this.maxViolations;
            }
            var modalBadge = document.getElementById("supervision-violation-badge");
            if (modalBadge) {
                var lbl = this._violationLabel || "Pozuntu";
                modalBadge.textContent = lbl + ": " + this.violationCount + " / " + this.maxViolations;
            }

            // Change badge color to orange/warning at 75% threshold
            var activeBadge = document.getElementById("supervision-active-badge");
            if (activeBadge && this.maxViolations > 0) {
                var threshold = Math.ceil(this.maxViolations * 0.75);
                if (this.violationCount >= threshold) {
                    activeBadge.style.background = "#ff6b00";
                    activeBadge.style.boxShadow = "0 2px 10px rgba(255,107,0,0.4)";
                    activeBadge.style.animation = "pulse-badge 1.5s ease-in-out infinite";
                }
            }
        },

        _showThresholdWarning: function () {
            // Don't show if already locked
            if (!this.isActive) return;
            if (document.getElementById("supervision-threshold-banner")) return;

            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var remaining = this.maxViolations - this.violationCount;
            var thresholdTitle = i18n.thresholdTitle || "\u26a0\ufe0f Diqq\u0259t!";
            var thresholdMsg = i18n.thresholdMsg || "";
            if (!thresholdMsg) {
                thresholdMsg = "Siz art\u0131q pozuntu limitinin 75%-in\u0259 \u00e7atm\u0131s\u0131n\u0131z! Yaln\u0131z " +
                    remaining + " pozuntuya icaz\u0259 qal\u0131b. Daha diqq\u0259tli olun!";
            } else if (thresholdMsg.indexOf("{remaining}") !== -1) {
                thresholdMsg = thresholdMsg.replace("{remaining}", remaining);
            }

            // Inject pulse animation if not already present
            if (!document.getElementById("supervision-threshold-style")) {
                var styleEl = document.createElement("style");
                styleEl.id = "supervision-threshold-style";
                styleEl.textContent =
                    "@keyframes pulse-badge{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}" +
                    "@keyframes threshold-slide-in{0%{transform:translateY(-100%);opacity:0}100%{transform:translateY(0);opacity:1}}" +
                    "@keyframes threshold-pulse{0%,100%{box-shadow:0 4px 20px rgba(255,107,0,0.3)}50%{box-shadow:0 4px 30px rgba(255,107,0,0.6)}}";
                document.head.appendChild(styleEl);
            }

            var banner = document.createElement("div");
            banner.id = "supervision-threshold-banner";
            banner.style.cssText =
                "position:fixed;top:0;left:0;width:100%;z-index:100000;background:linear-gradient(135deg,#ff6b00,#ff8c00);" +
                "color:#fff;text-align:center;padding:1rem 1.5rem;font-size:1rem;font-weight:600;" +
                "box-shadow:0 4px 20px rgba(255,107,0,0.3);" +
                "animation:threshold-slide-in 0.5s ease-out,threshold-pulse 2s ease-in-out infinite;";
            banner.innerHTML =
                '<div style="display:flex;align-items:center;justify-content:center;gap:0.75rem;flex-wrap:wrap;">' +
                '<i class="fas fa-exclamation-triangle" style="font-size:1.5rem;"></i>' +
                '<div>' +
                '<div style="font-size:1.1rem;font-weight:700;">' + thresholdTitle + '</div>' +
                '<div style="font-size:0.9rem;font-weight:400;opacity:0.95;margin-top:0.2rem;">' + thresholdMsg + '</div>' +
                '</div>' +
                '<span style="background:rgba(255,255,255,0.25);padding:0.3rem 0.8rem;border-radius:20px;font-size:0.85rem;">' +
                (this._violationLabel || "Pozuntu") + ": " + this.violationCount + " / " + this.maxViolations +
                '</span>' +
                '<button id="supervision-threshold-dismiss" style="background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);' +
                'color:#fff;padding:0.3rem 0.8rem;border-radius:6px;cursor:pointer;font-size:0.85rem;font-weight:500;">OK</button>' +
                '</div>';
            document.body.appendChild(banner);

            document.getElementById("supervision-threshold-dismiss").addEventListener("click", function () {
                banner.style.animation = "none";
                banner.style.transition = "transform 0.3s ease-in, opacity 0.3s ease-in";
                banner.style.transform = "translateY(-100%)";
                banner.style.opacity = "0";
                setTimeout(function () {
                    if (banner.parentNode) banner.remove();
                }, 350);
            });

            // Auto-dismiss after 10 seconds
            setTimeout(function () {
                if (banner.parentNode) {
                    banner.style.animation = "none";
                    banner.style.transition = "transform 0.3s ease-in, opacity 0.3s ease-in";
                    banner.style.transform = "translateY(-100%)";
                    banner.style.opacity = "0";
                    setTimeout(function () {
                        if (banner.parentNode) banner.remove();
                    }, 350);
                }
            }, 10000);
        },

        _onLimitExceeded: function () {
            this.isActive = false;
            this._hideWarning();

            // Don't create duplicate locked overlays
            if (document.getElementById("supervision-locked-overlay")) return;

            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var lockedTitle = i18n.lockedTitle || "\u0130mtahan Dayand\u0131r\u0131ld\u0131";
            var lockedMsg = i18n.lockedMsg || ("Maksimum pozuntu limitin\u0259 \u00e7atd\u0131n\u0131z (" + this.maxViolations + " pozuntu).");
            var lockedWait = i18n.lockedWait || "\u0130mtahan\u0131n\u0131z dayand\u0131r\u0131l\u0131b. M\u00fc\u0259llim q\u0259rar q\u0259bul ed\u0259n\u0259 q\u0259d\u0259r g\u00f6zl\u0259yin.";
            var lockedWaiting = i18n.lockedWaiting || "M\u00fc\u0259llim cavab\u0131n\u0131 g\u00f6zl\u0259yirik...";

            var overlay = document.createElement("div");
            overlay.id = "supervision-locked-overlay";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);" +
                "z-index:100001;display:flex;justify-content:center;align-items:center;";
            overlay.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2.5rem;max-width:500px;width:90%;text-align:center;">' +
                '<div style="font-size:4rem;color:#dc3545;margin-bottom:1rem;"><i class="fas fa-ban"></i></div>' +
                '<h2 style="color:#dc3545;">' + lockedTitle + "</h2>" +
                '<p style="color:#555;margin:1rem 0;">' + lockedMsg + "</p>" +
                '<p style="color:#555;">' + lockedWait + "</p>" +
                '<div style="margin-top:1.5rem;"><div class="spinner-border text-secondary" role="status"></div></div>' +
                '<p style="color:#999;font-size:0.85rem;margin-top:1rem;">' + lockedWaiting + "</p>" +
                "</div>";
            document.body.appendChild(overlay);

            // Poll for status changes
            this._startStatusPolling();
        },

        _startStatusPolling: function () {
            var poll = setInterval(function () {
                ExamSupervision._checkSupervisionStatus(function (data) {
                    if (data.supervision_status === "resumed" || data.supervision_status === "active") {
                        clearInterval(poll);
                        var overlay = document.getElementById("supervision-locked-overlay");
                        if (overlay) overlay.remove();
                        ExamSupervision.isActive = true;
                        ExamSupervision.violationCount = data.violation_count || 0;
                        ExamSupervision.maxViolations = data.max_violations || ExamSupervision.maxViolations;
                        ExamSupervision._updateBadge();
                        if (ExamSupervision.config.force_fullscreen) {
                            ExamSupervision._showResumeFullscreenOverlay();
                        }
                    } else if (data.is_finished) {
                        clearInterval(poll);
                        window.location.reload();
                    }
                });
            }, 5000);
        },

        _showResumeFullscreenOverlay: function () {
            if (document.getElementById("supervision-resume-overlay")) return;

            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var resumeTitle = i18n.resumeTitle || "\u0130mtahan b\u0259rpa edildi!";
            var resumeMsg = i18n.resumeMsg || "Davam etm\u0259k \u00fc\u00e7\u00fcn tam ekrana qay\u0131d\u0131n.";
            var resumeBtn = i18n.resumeBtn || "Tam ekrana ke\u00e7 v\u0259 davam et";

            var overlay = document.createElement("div");
            overlay.id = "supervision-resume-overlay";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);" +
                "z-index:100001;display:flex;justify-content:center;align-items:center;";
            overlay.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2.5rem;max-width:500px;width:90%;text-align:center;">' +
                '<div style="font-size:3rem;color:#28a745;margin-bottom:1rem;"><i class="fas fa-check-circle"></i></div>' +
                '<h2 style="color:#333;">' + resumeTitle + '</h2>' +
                '<p style="color:#555;margin:1rem 0;">' + resumeMsg + '</p>' +
                '<button id="supervision-resume-fs-btn" style="margin-top:1rem;padding:0.75rem 2rem;background:#007bff;color:#fff;' +
                'border:none;border-radius:8px;font-size:1.1rem;cursor:pointer;">' +
                '<i class="fas fa-expand"></i> ' + resumeBtn + '</button>' +
                '</div>';
            document.body.appendChild(overlay);

            document.getElementById("supervision-resume-fs-btn").addEventListener("click", function () {
                try {
                    var el = document.documentElement;
                    var fsPromise;
                    if (el.requestFullscreen) {
                        fsPromise = el.requestFullscreen();
                    } else if (el.webkitRequestFullscreen) {
                        fsPromise = el.webkitRequestFullscreen();
                    }
                    if (fsPromise && typeof fsPromise.then === "function") {
                        fsPromise.then(function () {
                            overlay.remove();
                        }).catch(function () {
                            overlay.remove();
                        });
                        return;
                    }
                } catch (e) {}
                overlay.remove();
            });
        },

        _checkSupervisionStatus: function (callback) {
            if (!this.statusEndpoint) return;
            fetch(this.statusEndpoint, {
                method: "GET",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (r) {
                    return r.json();
                })
                .then(function (data) {
                    if (callback) callback(data);
                })
                .catch(function () {});
        },

        _logEvent: function (eventType, metadata) {
            if (!this.logEndpoint) return;
            fetch(this.logEndpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": this.csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: JSON.stringify({
                    event_type: eventType,
                    metadata: metadata || {},
                }),
            })
                .then(function (r) {
                    return r.json();
                })
                .then(
                    function (data) {
                        if (data.supervision_status === "locked" || data.supervision_status === "removed") {
                            ExamSupervision._onLimitExceeded();
                        }
                        if (data.violation_count !== undefined) {
                            ExamSupervision.violationCount = data.violation_count;
                            ExamSupervision.maxViolations = data.max_violations || ExamSupervision.maxViolations;
                            ExamSupervision._updateBadge();
                        }
                    }
                )
                .catch(function () {});
        },

        destroy: function () {
            this.isActive = false;
            this._clearGraceTimer();
        },
    };

    window.ExamSupervision = ExamSupervision;
})(window);
