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
        capabilities: null,
        requestedConfig: null,
        isSupervised: true,
        _fullscreenDisabledByCapability: false,
        _acknowledged: false,
        _initialized: false,
        _initialStatus: "active",
        _thresholdWarned: false,
        _navigatingToResult: false,

        /**
         * Initialize the supervision module.
         * @param {Object} opts - Configuration from server
         */
        init: function (opts) {
            // Prevent double initialization
            if (this._initialized) return;
            this._initialized = true;

            this.requestedConfig = this._cloneConfig(opts.config || {});
            this.config = this._cloneConfig(opts.config || {});
            this.attemptId = opts.attemptId;
            this.csrfToken = opts.csrfToken;
            this.logEndpoint = opts.logEndpoint;
            this.statusEndpoint = opts.statusEndpoint;
            this.violationCount = opts.violationCount || 0;
            this.maxViolations = opts.maxViolations || 3;
            this.gracePeriodSeconds = this.config.grace_period_seconds || 15;
            this.isSupervised = opts.supervised !== false;
            this._initialStatus = opts.supervisionStatus || "active";
            this.isActive = true;
            this._acknowledged = false;
            this._fullscreenDisabledByCapability = false;
            this.capabilities = this._detectCapabilities();
            this._applyCapabilityFallbacks();

            if (this.isSupervised) {
                this._createWarningModal();
                this._createSupervisionBadge();
            }

            // Connect WebSocket for real-time teacher action notifications
            this._connectWebSocket();
            // Start the resilient status poll immediately as well. If the
            // teacher pauses the student while the acknowledgment modal is
            // still open, the manual-lock modal should still appear.
            this._startBackgroundStatusWatch();

            // If attempt is already locked/removed, show the right overlay
            // immediately. We ask the status API whether this was a manual
            // teacher pause (distinct overlay, no auto-finish countdown) or an
            // auto-lock from the violation limit.
            if (this._initialStatus === "locked" || this._initialStatus === "removed") {
                this._acknowledged = true;
                this._bindEvents();
                var self = this;
                this._checkSupervisionStatus(function (data) {
                    if (data && data.manual_lock) {
                        self._showTeacherLockOverlay();
                    } else {
                        self._onLimitExceeded();
                    }
                });
                // Fallback: if the status call fails the callback never fires,
                // so show the limit overlay after a short delay to be safe.
                window.setTimeout(function () {
                    if (!document.getElementById("supervision-teacher-lock-overlay") &&
                        !document.getElementById("supervision-locked-overlay")) {
                        self._onLimitExceeded();
                    }
                }, 1500);
                return;
            }

            if (!this.isSupervised) {
                return;
            }

            // Show acknowledgment overlay - events bind AFTER student acknowledges
            this._showAcknowledgment();
        },

        _cloneConfig: function (config) {
            var clone = {};
            Object.keys(config || {}).forEach(function (key) {
                clone[key] = config[key];
            });
            return clone;
        },

        _detectCapabilities: function () {
            var el = document.documentElement || document.body;
            var ua = navigator.userAgent || "";
            var platform = navigator.platform || "";
            var isIOS = /iPad|iPhone|iPod/.test(ua) ||
                (platform === "MacIntel" && navigator.maxTouchPoints > 1);
            var isMobileLike = isIOS || /Android|Mobi|Tablet|IEMobile|Opera Mini/i.test(ua) ||
                (navigator.maxTouchPoints && navigator.maxTouchPoints > 1 && Math.min(window.innerWidth, window.innerHeight) < 900);
            var hasRequestFullscreen = !!(
                el &&
                (typeof el.requestFullscreen === "function" || typeof el.webkitRequestFullscreen === "function")
            );
            var fullscreenEnabled = true;
            if (typeof document.fullscreenEnabled === "boolean") {
                fullscreenEnabled = document.fullscreenEnabled;
            } else if (typeof document.webkitFullscreenEnabled === "boolean") {
                fullscreenEnabled = document.webkitFullscreenEnabled;
            }

            return {
                fullscreen_supported: !!(hasRequestFullscreen && fullscreenEnabled),
                has_request_fullscreen: hasRequestFullscreen,
                fullscreen_enabled: fullscreenEnabled,
                is_ios: !!isIOS,
                is_mobile: !!isMobileLike,
                user_agent: ua
            };
        },

        _applyCapabilityFallbacks: function () {
            if (this.config.force_fullscreen && !(this.capabilities && this.capabilities.fullscreen_supported)) {
                this.config.force_fullscreen = false;
                this._fullscreenDisabledByCapability = true;
                if (this.capabilities) {
                    this.capabilities.fullscreen_disabled_reason = "unsupported";
                }
            }
        },

        _disableFullscreenForSession: function (reason) {
            this.config.force_fullscreen = false;
            this._fullscreenDisabledByCapability = true;
            if (this.capabilities) {
                this.capabilities.fullscreen_supported = false;
                this.capabilities.fullscreen_disabled_reason = reason || "request_failed";
            }
        },

        _isFullscreenActive: function () {
            return !!(
                document.fullscreenElement ||
                document.webkitFullscreenElement
            );
        },

        _publicConfig: function (config) {
            return {
                force_fullscreen: !!config.force_fullscreen,
                detect_tab_switch: !!config.detect_tab_switch,
                block_copy_paste: !!config.block_copy_paste,
                disable_right_click: !!config.disable_right_click,
                disable_text_selection: !!config.disable_text_selection,
                restrict_keyboard_shortcuts: !!config.restrict_keyboard_shortcuts
            };
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
            var ruleFullscreenUnavailable = i18n.ruleFullscreenUnavailable ||
                "Tam ekran bu cihaz\u0131n brauzerind\u0259 d\u0259st\u0259kl\u0259nmir; m\u00fcmk\u00fcn n\u0259zar\u0259tl\u0259r aktiv qalacaq.";
            var fullscreenRuleHtml = "";
            if (this.config.force_fullscreen) {
                fullscreenRuleHtml = "<li>" + ruleFullscreen + "</li>";
            } else if (this.requestedConfig && this.requestedConfig.force_fullscreen && this._fullscreenDisabledByCapability) {
                fullscreenRuleHtml = '<li style="color:#856404;">' + ruleFullscreenUnavailable + "</li>";
            }

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
                fullscreenRuleHtml +
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
                    self._requestFullscreen().then(function (success) {
                        if (!success && self.capabilities && self.capabilities.is_mobile) {
                            self._disableFullscreenForSession("request_failed");
                        }
                        self._completeAcknowledgment(overlay);
                    });
                    return;
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
            this._logEvent("exam_started_supervised", {
                timestamp: new Date().toISOString(),
                capabilities: this.capabilities || {},
                requested_config: this._publicConfig(this.requestedConfig || {}),
                effective_config: this._publicConfig(this.config || {})
            });
            this._logEvent("student_acknowledged", {
                fullscreen_adjusted: !!this._fullscreenDisabledByCapability
            });

            // Update badge immediately with current violation count
            this._updateBadge();

            // If fullscreen is required but not active, show warning immediately
            if (this.config.force_fullscreen) {
                if (!this._isFullscreenActive()) {
                    this._showWarning();
                    this._startGraceTimer();
                }
            }

            // Always-on safety net: poll the status API so a teacher lock/stop
            // is honoured even if the WebSocket is unavailable (no Redis / proxy
            // dropped the socket). The WS still delivers it instantly when up.
            this._startBackgroundStatusWatch();
        },

        // Primary, infra-independent delivery path: a fast status poll that
        // reacts to a teacher action (lock / stop) while the student is taking
        // the exam. The WebSocket delivers the same events instantly when it is
        // available, but in dev (InMemoryChannelLayer) or behind a proxy that
        // drops WS the socket may never connect — so this poll guarantees the
        // student's screen still locks / submits without a manual refresh.
        // WebSocket delivers teacher actions instantly. Keep the fallback poll
        // at 1s so the lock still feels immediate when WS is unavailable.
        _bgStatusInterval: 1000,
        _startBackgroundStatusWatch: function () {
            if (this._bgStatusWatch) return;
            var self = this;
            this._bgStatusWatch = setInterval(function () {
                if (!self.isActive) return;
                if (document.getElementById("supervision-teacher-lock-overlay") ||
                    document.getElementById("supervision-locked-overlay")) {
                    return;
                }
                self._checkSupervisionStatus(function (data) {
                    if (!data) return;
                    if (data.is_finished) {
                        // Teacher removed / auto-finished the attempt → leave the
                        // exam immediately (result page) instead of waiting.
                        self._leaveToResult();
                        return;
                    }
                    if (data.supervision_status === "locked") {
                        if (data.manual_lock) {
                            self._showTeacherLockOverlay();
                        } else {
                            self._onLimitExceeded();
                        }
                    }
                });
            }, this._bgStatusInterval);
        },

        // Navigate the student away once the attempt is finished by a teacher
        // (or auto-finish). Uses the result URL exposed by the exam page when
        // present; falls back to a plain reload, which the server then redirects
        // to the result page for a finished attempt.
        _leaveToResult: function () {
            if (this._navigatingToResult || window.EXAM_SUPERVISION_NAVIGATING === true) {
                return;
            }
            this._navigatingToResult = true;
            window.EXAM_SUPERVISION_NAVIGATING = true;
            this.destroy();

            var url = (window.SUPERVISION_RESULT_URL || "").trim();
            if (url) {
                window.location.href = url;
            } else {
                window.location.reload();
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

            // After an iframe-triggered alert/confirm/prompt closes, any
            // user gesture (click or key) on the parent window is the
            // safest moment to re-enter fullscreen. We piggy-back on the
            // grace flag so this only fires right after a Run.
            var restoreOnGesture = function () { self._maybeRestoreFullscreen(); };
            document.addEventListener("click", restoreOnGesture, true);
            document.addEventListener("keyup", restoreOnGesture, true);

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

            var isFS = this._isFullscreenActive();
            this.isFullscreen = isFS;

            if (!isFS && this.config.force_fullscreen && this.isActive) {
                // Native browser modals from the preview iframe (alert/confirm/prompt)
                // can momentarily exit fullscreen on Chromium. Ignore the exit
                // event if we are inside the post-Run grace window.
                if (this._isInPreviewGrace()) {
                    return;
                }
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
                // Suppress when the iframe just triggered alert()/confirm()/prompt():
                // these temporarily mark the tab as hidden in some browsers
                // but the student never actually left the exam.
                if (this._isInPreviewGrace() || this._focusInsidePreview()) {
                    return;
                }
                this._logEvent("tab_switched");
                this._incrementViolation();
            }
        },

        _onWindowBlur: function () {
            if (!this._acknowledged) return;
            if (this.isActive) {
                // Ignore blur events caused by the student's own alert()/
                // confirm()/prompt() — they are still inside the exam page.
                if (this._isInPreviewGrace() || this._focusInsidePreview()) {
                    return;
                }
                this._logEvent("window_blurred");
            }
        },

        _onWindowFocus: function () {
            if (!this._acknowledged) return;
            if (this.isActive) {
                this._logEvent("window_focused");
                this._checkSupervisionStatus();
                // After a native alert/confirm/prompt closes, focus returns
                // to the exam window. If we are still inside the post-Run
                // grace window AND fullscreen was required but is now gone,
                // re-enter fullscreen so the student doesn't have to. The
                // focus event counts as a user gesture in most browsers.
                this._maybeRestoreFullscreen();
            }
        },

        // Re-request fullscreen if it was lost during the preview grace
        // window. Schedules a couple of retries because some browsers (e.g.
        // Chromium) refuse the first call right after the modal closes.
        _maybeRestoreFullscreen: function () {
            if (!this.config.force_fullscreen) return;
            if (!this._isInPreviewGrace()) return;
            if (this._isFullscreenActive()) return;
            var self = this;
            var attempt = function () {
                if (!self.isActive || self._isFullscreenActive()) return;
                self._requestFullscreen().catch(function () { /* user-gesture required, swallow */ });
            };
            attempt();
            // Retry once after the browser settles — alert() can briefly
            // suppress the fullscreen request even though focus has returned.
            window.setTimeout(attempt, 150);
        },

        _isEditableField: function (target) {
            if (!target) return false;
            var tag = target.tagName;
            if (tag === "INPUT" || tag === "TEXTAREA") return true;
            if (target.isContentEditable) return true;
            // CodeMirror 5 renders an editable surface as a <pre> inside
            // .CodeMirror; bubbling events report .CodeMirror-line / .CodeMirror-code
            // as the target. Walk up to detect either marker.
            var node = target;
            while (node && node.nodeType === 1) {
                if (node.classList && (node.classList.contains("CodeMirror") || node.classList.contains("CodeMirror-code") || node.classList.contains("CodeMirror-line"))) {
                    return true;
                }
                // Inline interactive terminal input.
                if (node.classList && node.classList.contains("coding-terminal-input")) {
                    return true;
                }
                node = node.parentNode;
            }
            return false;
        },

        // True when the user's focus is inside the run-preview iframe (the
        // student's own program is running there). Native browser modals
        // launched from that iframe — alert/confirm/prompt — momentarily
        // blur the parent window. That is NOT a tab switch and must not be
        // logged as a supervision violation.
        _focusInsidePreview: function () {
            try {
                var active = document.activeElement;
                if (active && active.tagName === "IFRAME") return true;
                // After alert() closes, activeElement reverts to body but the
                // iframe still owns the modal — check by id as fallback.
                var preview = document.getElementById("codingPreviewFrame");
                if (preview && preview.contentDocument && preview.contentDocument.hasFocus && preview.contentDocument.hasFocus()) {
                    return true;
                }
            } catch (e) {
                // Cross-origin or sandboxed access — fall through.
            }
            return false;
        },

        // Native alert()/confirm()/prompt() temporarily steal focus and (on
        // Chromium) exit fullscreen. We open a short "grace window" right
        // after a Run so subsequent fullscreen/blur events do not count as
        // violations. The window auto-clears on the next user interaction.
        _previewGraceUntil: 0,
        _isInPreviewGrace: function () {
            return Date.now() < this._previewGraceUntil;
        },

        /**
         * Open a grace window (default 5 seconds) during which fullscreen
         * exits and window blurs caused by the run-preview iframe will NOT
         * be logged as violations. Called by coding_exam.js right before it
         * runs student code that may pop alert()/confirm()/prompt().
         * @param {number} durationMs - How long the grace window lasts.
         */
        startPreviewGrace: function (durationMs) {
            var ms = Math.max(1000, Math.min(parseInt(durationMs, 10) || 5000, 30000));
            this._previewGraceUntil = Date.now() + ms;
        },

        // Clipboard / right-click are blocked outright (preventDefault) but do
        // NOT cost the student a violation point. We still log the attempt so
        // the teacher sees it in the audit trail.
        _onCopy: function (e) {
            if (this._isEditableField(e.target)) return;
            e.preventDefault();
            this._logEvent("copy_attempt");
        },

        _onPaste: function (e) {
            e.preventDefault();
            this._logEvent("paste_attempt");
        },

        _onCut: function (e) {
            if (this._isEditableField(e.target)) return;
            e.preventDefault();
            this._logEvent("cut_attempt");
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
            // Inside an editable field (text input, textarea, CodeMirror, or
            // our inline terminal input) the student must be able to type
            // freely — including punctuation like # @ % * ? /, and use the
            // ordinary clipboard shortcuts to move their own code around.
            // We only block "system" shortcuts that open dev tools, print,
            // or view source. Pure copy/paste/cut/save are always allowed
            // inside editable fields.
            var inEditor = this._isEditableField(e.target);
            var ctrl = e.ctrlKey || e.metaKey;
            var shift = e.shiftKey;
            var key = (e.key || "").toLowerCase();

            // Always-blocked system shortcuts (regardless of focus).
            var systemBlocked = (
                (ctrl && shift && (key === "i" || key === "j" || key === "c")) || // DevTools
                (ctrl && key === "u") || // View Source
                (ctrl && key === "p") || // Print
                key === "f12" ||
                key === "printscreen"
            );
            if (systemBlocked) {
                e.preventDefault();
                e.stopPropagation();
                this._logEvent("keyboard_shortcut", {
                    key: e.key, ctrl: e.ctrlKey, shift: e.shiftKey, meta: e.metaKey,
                });
                return false;
            }

            // Copy/cut/paste shortcuts: only restricted OUTSIDE editable
            // fields, and only when the exam config asks for it. This stops
            // a student from copying the question text into another window
            // while still letting them edit their own code naturally.
            if (this.config.block_copy_paste && !inEditor) {
                if (ctrl && (key === "c" || key === "v" || key === "x")) {
                    e.preventDefault();
                    e.stopPropagation();
                    // Blocked, but logged as a non-counting clipboard event so it
                    // does not burn a violation point (matches mouse copy/paste).
                    var clipEvent = key === "c" ? "copy_attempt" : (key === "v" ? "paste_attempt" : "cut_attempt");
                    this._logEvent(clipEvent, { via: "keyboard", key: e.key });
                    return false;
                }
            }

            // Ctrl+S inside the editor is reserved for our autosave shortcut
            // (see coding_exam.js). Swallow the browser "Save Page" dialog.
            if (ctrl && key === "s") {
                e.preventDefault();
                return false;
            }
        },

        _requestFullscreen: function () {
            var self = this;
            if (!(this.capabilities && this.capabilities.fullscreen_supported)) {
                return Promise.resolve(false);
            }
            try {
                var el = document.documentElement;
                var fsPromise;
                if (el.requestFullscreen) {
                    fsPromise = el.requestFullscreen();
                } else if (el.webkitRequestFullscreen) {
                    fsPromise = el.webkitRequestFullscreen();
                } else {
                    return Promise.resolve(false);
                }

                if (fsPromise && typeof fsPromise.then === "function") {
                    return fsPromise.then(function () {
                        return self._isFullscreenActive();
                    }).catch(function () {
                        return false;
                    });
                }

                return Promise.resolve(true);
            } catch (e) {}
            return Promise.resolve(false);
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
            this._logEvent("grace_period_expired", {
                reason: "fullscreen_not_restored",
                fullscreen_active: this._isFullscreenActive()
            });
            this._incrementViolation();
            this._hideWarning();
            if (this.config.force_fullscreen && this.isActive && !this._isFullscreenActive()) {
                this._showWarning();
                this._startGraceTimer();
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

        // Dedicated overlay for a *manual* teacher pause ("Müvəqqəti blokla").
        // Visually matches the violation-lock overlay so the student gets the
        // same clear "screen is frozen" treatment, but the wording makes it
        // explicit that the teacher paused them and there is NO auto-finish
        // countdown — the student simply waits for the teacher to resume.
        _showTeacherLockOverlay: function () {
            this.isActive = false;
            this._hideWarning();
            this._clearGraceTimer();

            // If the violation-lock overlay is already up, drop it — the teacher
            // pause supersedes it with the correct messaging.
            var existingLimit = document.getElementById("supervision-locked-overlay");
            if (existingLimit) existingLimit.remove();
            if (document.getElementById("supervision-teacher-lock-overlay")) {
                this._startTeacherLockPolling();
                return;
            }

            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var title = i18n.teacherLockTitle || "Müəllim tərəfindən müvəqqəti bloklandınız";
            var msg = i18n.teacherLockMsg ||
                "Müəllim imtahanınızı müvəqqəti blokladı. Ekranınız kilidlənib.";
            var waiting = i18n.teacherLockWaiting ||
                "Müəllim imtahanı bərpa edənə qədər zəhmət olmasa gözləyin. Səhifəni bağlamayın.";

            var overlay = document.createElement("div");
            overlay.id = "supervision-teacher-lock-overlay";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);" +
                "z-index:100001;display:flex;justify-content:center;align-items:center;";
            overlay.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2.5rem;max-width:520px;width:90%;text-align:center;">' +
                '<div style="font-size:4rem;color:#ea580c;margin-bottom:1rem;"><i class="fas fa-hand-paper"></i></div>' +
                '<h2 style="color:#ea580c;">' + title + '</h2>' +
                '<p style="color:#555;margin:1rem 0;">' + msg + '</p>' +
                '<div style="margin:1.25rem 0;display:flex;justify-content:center;">' +
                '<div style="display:inline-flex;align-items:center;gap:0.6rem;background:#fff7ed;color:#9a3412;' +
                'padding:0.6rem 1.1rem;border-radius:999px;font-weight:600;">' +
                '<i class="fas fa-spinner fa-spin"></i> ' + waiting + '</div>' +
                '</div>' +
                '</div>';
            document.body.appendChild(overlay);

            // Poll for the teacher's resume / a force-stop. The WebSocket usually
            // delivers this instantly, but polling is the resilient fallback.
            this._startTeacherLockPolling();
        },

        _startTeacherLockPolling: function () {
            if (this._teacherLockPoll) return;
            this._teacherLockPoll = setInterval(function () {
                ExamSupervision._checkSupervisionStatus(function (data) {
                    if (!data) return;
                    if (data.supervision_status === "resumed" || data.supervision_status === "active") {
                        clearInterval(ExamSupervision._teacherLockPoll);
                        ExamSupervision._teacherLockPoll = null;
                        var ov = document.getElementById("supervision-teacher-lock-overlay");
                        if (ov) ov.remove();
                        ExamSupervision.isActive = true;
                        if (data.violation_count !== undefined) {
                            ExamSupervision.violationCount = data.violation_count;
                        }
                        if (data.max_violations !== undefined) {
                            ExamSupervision.maxViolations = data.max_violations;
                        }
                        ExamSupervision._updateBadge();
                        ExamSupervision._showResumeFullscreenOverlay(null);
                    } else if (data.is_finished) {
                        clearInterval(ExamSupervision._teacherLockPoll);
                        ExamSupervision._teacherLockPoll = null;
                        ExamSupervision._leaveToResult();
                    }
                });
            }, 1000);
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

            var countdownLabel = i18n.lockedCountdownLabel || "Müəllim bərpa etməsə, imtahan avtomatik bitəcək";

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
                '<div id="supervision-locked-countdown-wrap" style="margin:1.5rem 0;display:none;">' +
                '<div style="font-size:0.8rem;color:#888;text-transform:uppercase;letter-spacing:0.02em;">' + countdownLabel + '</div>' +
                '<div id="supervision-locked-countdown" style="font-size:2.5rem;font-weight:700;color:#dc3545;font-variant-numeric:tabular-nums;">--:--</div>' +
                '</div>' +
                '<p style="color:#999;font-size:0.85rem;margin-top:1rem;">' + lockedWaiting + "</p>" +
                "</div>";
            document.body.appendChild(overlay);

            // Fetch the authoritative remaining time, then tick locally.
            this._startLockCountdown();
            // Poll for status changes (teacher resume / auto-finish).
            this._startStatusPolling();
        },

        // Drives the "teacher must resume within N" countdown shown on the
        // locked overlay. Seeds from the status API, then ticks every second.
        _startLockCountdown: function () {
            var self = this;
            this._checkSupervisionStatus(function (data) {
                var remaining = data && data.resume_seconds_remaining;
                if (remaining === null || remaining === undefined) return;
                var wrap = document.getElementById("supervision-locked-countdown-wrap");
                var cdEl = document.getElementById("supervision-locked-countdown");
                if (!wrap || !cdEl) return;
                wrap.style.display = "block";
                remaining = Math.max(0, parseInt(remaining, 10) || 0);
                cdEl.textContent = self._formatRemaining(remaining);
                if (self._lockCountdownTimer) clearInterval(self._lockCountdownTimer);
                self._lockCountdownTimer = setInterval(function () {
                    remaining--;
                    cdEl.textContent = self._formatRemaining(remaining);
                    if (remaining <= 0) {
                        clearInterval(self._lockCountdownTimer);
                        self._lockCountdownTimer = null;
                        // Window elapsed — backend has (or is about to) submit
                        // the attempt; reload to land on the result page.
                        window.location.reload();
                    }
                }, 1000);
            });
        },

        _startStatusPolling: function () {
            var poll = setInterval(function () {
                ExamSupervision._checkSupervisionStatus(function (data) {
                    if (data.supervision_status === "resumed" || data.supervision_status === "active") {
                        clearInterval(poll);
                        if (ExamSupervision._lockCountdownTimer) {
                            clearInterval(ExamSupervision._lockCountdownTimer);
                            ExamSupervision._lockCountdownTimer = null;
                        }
                        var overlay = document.getElementById("supervision-locked-overlay");
                        if (overlay) overlay.remove();
                        ExamSupervision.isActive = true;
                        ExamSupervision.violationCount = data.violation_count || 0;
                        ExamSupervision.maxViolations = data.max_violations || ExamSupervision.maxViolations;
                        ExamSupervision._updateBadge();
                        // Teacher resumed in time → just bring the student back
                        // (fullscreen prompt if required). No further countdown.
                        ExamSupervision._showResumeFullscreenOverlay(null);
                    } else if (data.is_finished) {
                        clearInterval(poll);
                        if (ExamSupervision._lockCountdownTimer) {
                            clearInterval(ExamSupervision._lockCountdownTimer);
                            ExamSupervision._lockCountdownTimer = null;
                        }
                        ExamSupervision._leaveToResult();
                    }
                });
            }, 1000);
        },

        // Format seconds as M:SS for the resume countdown.
        _formatRemaining: function (totalSeconds) {
            totalSeconds = Math.max(0, parseInt(totalSeconds, 10) || 0);
            var m = Math.floor(totalSeconds / 60);
            var s = totalSeconds % 60;
            return m + ":" + (s < 10 ? "0" + s : s);
        },

        _showResumeFullscreenOverlay: function (resumeSecondsRemaining) {
            if (document.getElementById("supervision-resume-overlay")) return;

            var self = this;
            var i18n = (window.SUPERVISION_ACK_I18N) || {};
            var resumeTitle = i18n.resumeTitle || "\u0130mtahan b\u0259rpa edildi!";
            var needsFullscreen = !!this.config.force_fullscreen;
            var resumeMsg = needsFullscreen
                ? (i18n.resumeMsg || "Davam etm\u0259k \u00fc\u00e7\u00fcn tam ekrana qay\u0131d\u0131n.")
                : (i18n.resumeMsgNoFs || "Davam etm\u0259k \u00fc\u00e7\u00fcn d\u00fcym\u0259ni bas\u0131n.");
            var resumeBtn = needsFullscreen
                ? (i18n.resumeBtn || "Tam ekrana ke\u00e7 v\u0259 davam et")
                : (i18n.resumeBtnNoFs || "Davam et");
            var countdownLabel = i18n.resumeCountdownLabel || "B\u0259rpa etm\u0259y\u0259 qalan vaxt";

            // Whether a resume window applies (null = disabled / no deadline).
            var hasCountdown = resumeSecondsRemaining !== null && resumeSecondsRemaining !== undefined;

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
                (hasCountdown
                    ? '<div style="margin:1.25rem 0;">' +
                      '<div style="font-size:0.85rem;color:#888;letter-spacing:0.02em;text-transform:uppercase;">' + countdownLabel + '</div>' +
                      '<div id="supervision-resume-countdown" style="font-size:2.5rem;font-weight:700;color:#dc3545;font-variant-numeric:tabular-nums;">' +
                      self._formatRemaining(resumeSecondsRemaining) + '</div>' +
                      '</div>'
                    : '') +
                '<button id="supervision-resume-fs-btn" style="margin-top:0.5rem;padding:0.75rem 2rem;background:#007bff;color:#fff;' +
                'border:none;border-radius:8px;font-size:1.1rem;cursor:pointer;">' +
                (needsFullscreen ? '<i class="fas fa-expand"></i> ' : '') + resumeBtn + '</button>' +
                '</div>';
            document.body.appendChild(overlay);

            // Live countdown to the resume deadline. When it hits zero the
            // backend has (or is about to) auto-finish the attempt, so reload
            // to land on the result page.
            if (hasCountdown) {
                var remaining = Math.max(0, parseInt(resumeSecondsRemaining, 10) || 0);
                var cdEl = document.getElementById("supervision-resume-countdown");
                this._resumeCountdownTimer = setInterval(function () {
                    remaining--;
                    if (cdEl) {
                        cdEl.textContent = self._formatRemaining(remaining);
                        if (remaining <= 30) cdEl.style.color = "#dc3545";
                    }
                    if (remaining <= 0) {
                        clearInterval(self._resumeCountdownTimer);
                        self._resumeCountdownTimer = null;
                        window.location.reload();
                    }
                }, 1000);
            }

            var finishResume = function () {
                if (self._resumeCountdownTimer) {
                    clearInterval(self._resumeCountdownTimer);
                    self._resumeCountdownTimer = null;
                }
                overlay.remove();
            };

            document.getElementById("supervision-resume-fs-btn").addEventListener("click", function () {
                if (!needsFullscreen) {
                    finishResume();
                    return;
                }
                try {
                    var el = document.documentElement;
                    var fsPromise;
                    if (el.requestFullscreen) {
                        fsPromise = el.requestFullscreen();
                    } else if (el.webkitRequestFullscreen) {
                        fsPromise = el.webkitRequestFullscreen();
                    }
                    if (fsPromise && typeof fsPromise.then === "function") {
                        fsPromise.then(finishResume).catch(finishResume);
                        return;
                    }
                } catch (e) {}
                finishResume();
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

        // Tokeni hər sorğuda cookie-dən təzə oxu: uzun imtahanda token
        // rotasiya olunarsa init-də verilmiş statik token 403 verir.
        _freshCsrfToken: function () {
            var row = document.cookie.split("; ").find(function (c) {
                return c.indexOf("csrftoken=") === 0;
            });
            if (row) {
                return decodeURIComponent(row.split("=").slice(1).join("="));
            }
            return this.csrfToken;
        },

        _logEvent: function (eventType, metadata) {
            if (!this.logEndpoint) return;
            fetch(this.logEndpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": this._freshCsrfToken(),
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
                            if (data.manual_lock) {
                                ExamSupervision._showTeacherLockOverlay();
                            } else {
                                ExamSupervision._onLimitExceeded();
                            }
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
            if (this._resumeCountdownTimer) {
                clearInterval(this._resumeCountdownTimer);
                this._resumeCountdownTimer = null;
            }
            if (this._lockCountdownTimer) {
                clearInterval(this._lockCountdownTimer);
                this._lockCountdownTimer = null;
            }
            if (this._teacherLockPoll) {
                clearInterval(this._teacherLockPoll);
                this._teacherLockPoll = null;
            }
            if (this._bgStatusWatch) {
                clearInterval(this._bgStatusWatch);
                this._bgStatusWatch = null;
            }
            this._closeWebSocket();
        },

        /* ---------- WebSocket for real-time teacher actions ---------- */

        _wsSocket: null,
        _wsReconnectTimer: null,
        _wsReconnectDelay: 2000,

        _connectWebSocket: function () {
            if (!this.attemptId) return;
            var self = this;
            var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            var url = protocol + "//" + window.location.host + "/ws/exams/supervision/" + this.attemptId + "/";

            try {
                this._wsSocket = new WebSocket(url);
            } catch (e) {
                return;
            }

            this._wsSocket.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    self._handleWsEvent(data);
                } catch (e) {}
            };

            this._wsSocket.onclose = function () {
                self._wsSocket = null;
                // Reconnect after delay unless destroyed
                if (self._initialized) {
                    self._wsReconnectTimer = setTimeout(function () {
                        self._connectWebSocket();
                    }, self._wsReconnectDelay);
                }
            };

            this._wsSocket.onerror = function () {
                // Will trigger onclose
            };
        },

        _closeWebSocket: function () {
            if (this._wsReconnectTimer) {
                clearTimeout(this._wsReconnectTimer);
                this._wsReconnectTimer = null;
            }
            if (this._wsSocket) {
                this._wsSocket.onclose = null;
                this._wsSocket.close();
                this._wsSocket = null;
            }
        },

        _handleWsEvent: function (data) {
            if (!data || !data.action) return;

            if (data.action === "locked") {
                // Teacher temporarily blocked the student's screen. A manual
                // teacher pause shows a distinct "your teacher paused you"
                // overlay (no auto-finish countdown); an auto-lock keeps the
                // violation-limit flow.
                if (data.manual) {
                    this._showTeacherLockOverlay();
                } else {
                    this._onLimitExceeded();
                }
            } else if (data.action === "stopped") {
                // Teacher force-stopped the exam — leave to the result page.
                this._leaveToResult();
            } else if (data.action === "resumed") {
                // Teacher resumed the student
                if (this._lockCountdownTimer) {
                    clearInterval(this._lockCountdownTimer);
                    this._lockCountdownTimer = null;
                }
                var overlay = document.getElementById("supervision-locked-overlay");
                if (overlay) overlay.remove();
                var teacherLockOverlay = document.getElementById("supervision-teacher-lock-overlay");
                if (teacherLockOverlay) teacherLockOverlay.remove();
                this.isActive = true;
                if (data.violation_count !== undefined) {
                    this.violationCount = data.violation_count;
                }
                if (data.max_violations !== undefined) {
                    this.maxViolations = data.max_violations;
                }
                this._updateBadge();
                this._showResumeFullscreenOverlay(null);
            }
        },
    };

    window.ExamSupervision = ExamSupervision;
})(window);
