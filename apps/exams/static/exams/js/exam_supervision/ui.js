import { ExamSupervision } from "./state.js?v=20260611-fresh-csrf";

Object.assign(ExamSupervision, {
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
            var title = i18n.teacherLockTitle || gettext("Müəllim tərəfindən müvəqqəti bloklandınız");
            var msg = i18n.teacherLockMsg ||
                gettext("Müəllim imtahanınızı müvəqqəti blokladı. Ekranınız kilidlənib.");
            var waiting = i18n.teacherLockWaiting ||
                gettext("Müəllim imtahanı bərpa edənə qədər zəhmət olmasa gözləyin. Səhifəni bağlamayın.");

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

            var countdownLabel = i18n.lockedCountdownLabel || gettext("Müəllim bərpa etməsə, imtahan avtomatik bitəcək");

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
});
