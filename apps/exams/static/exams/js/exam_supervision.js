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

    const ExamSupervision = {
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

        /**
         * Initialize the supervision module.
         * @param {Object} opts - Configuration from server
         */
        init: function (opts) {
            this.config = opts.config || {};
            this.attemptId = opts.attemptId;
            this.csrfToken = opts.csrfToken;
            this.logEndpoint = opts.logEndpoint;
            this.statusEndpoint = opts.statusEndpoint;
            this.violationCount = opts.violationCount || 0;
            this.maxViolations = opts.maxViolations || 3;
            this.gracePeriodSeconds = this.config.grace_period_seconds || 15;
            this.isActive = true;

            this._createWarningModal();
            this._createSupervisionBadge();
            this._bindEvents();

            // Log exam start
            this._logEvent("exam_started_supervised", { timestamp: new Date().toISOString() });

            // If fullscreen is required, show acknowledgment
            if (this.config.force_fullscreen) {
                this._showAcknowledgment();
            }
        },

        _createWarningModal: function () {
            const modal = document.createElement("div");
            modal.id = "supervision-warning-modal";
            modal.style.cssText =
                "display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);" +
                "z-index:99999;justify-content:center;align-items:center;";
            modal.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2rem;max-width:500px;width:90%;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.3);">' +
                '<div style="font-size:3rem;color:#dc3545;margin-bottom:1rem;"><i class="fas fa-exclamation-triangle"></i></div>' +
                '<h2 style="color:#dc3545;margin-bottom:0.5rem;" id="supervision-warning-title">⚠️ Xəbərdarlıq</h2>' +
                '<p id="supervision-warning-message" style="color:#333;margin-bottom:1rem;">İmtahan sahəsindən çıxdınız. Zəhmət olmasa geri qayıdın.</p>' +
                '<div style="font-size:2.5rem;font-weight:bold;color:#dc3545;margin:1rem 0;" id="supervision-countdown">15</div>' +
                '<p style="color:#666;font-size:0.9rem;">Vaxt bitərsə, bu pozuntu kimi qeyd olunacaq.</p>' +
                '<div style="margin-top:1rem;">' +
                '<span style="background:#ffeeba;color:#856404;padding:0.3rem 0.8rem;border-radius:20px;font-size:0.85rem;" id="supervision-violation-badge">' +
                "Pozuntu: 0 / 3</span></div>" +
                '<button id="supervision-return-btn" style="margin-top:1.5rem;padding:0.75rem 2rem;background:#28a745;color:#fff;border:none;border-radius:8px;font-size:1rem;cursor:pointer;">' +
                '<i class="fas fa-expand"></i> Tam ekrana qayıt</button>' +
                "</div>";
            document.body.appendChild(modal);
            this.warningModal = modal;

            document.getElementById("supervision-return-btn").addEventListener("click", function () {
                ExamSupervision._requestFullscreen();
                ExamSupervision._hideWarning();
            });
        },

        _createSupervisionBadge: function () {
            const badge = document.createElement("div");
            badge.id = "supervision-active-badge";
            badge.style.cssText =
                "position:fixed;top:10px;right:10px;z-index:9999;background:#dc3545;color:#fff;" +
                "padding:0.4rem 0.8rem;border-radius:20px;font-size:0.8rem;display:flex;align-items:center;gap:0.4rem;" +
                "box-shadow:0 2px 10px rgba(220,53,69,0.3);";
            badge.innerHTML =
                '<i class="fas fa-shield-alt"></i> <span>Nəzarət aktiv</span>' +
                ' <span id="supervision-badge-count" style="background:rgba(255,255,255,0.2);padding:0.1rem 0.4rem;border-radius:10px;font-size:0.75rem;">0/' +
                this.maxViolations +
                "</span>";
            document.body.appendChild(badge);
        },

        _showAcknowledgment: function () {
            const overlay = document.createElement("div");
            overlay.id = "supervision-acknowledgment";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);" +
                "z-index:100000;display:flex;justify-content:center;align-items:center;";
            overlay.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2.5rem;max-width:550px;width:90%;text-align:center;">' +
                '<div style="font-size:3rem;color:#007bff;margin-bottom:1rem;"><i class="fas fa-shield-alt"></i></div>' +
                "<h2 style=\"color:#333;\">Nəzarət Rejimi Aktiv</h2>" +
                '<p style="color:#555;margin:1rem 0;">Bu imtahan <strong>nəzarət rejimində</strong> keçirilir. Aşağıdakı qaydalar tətbiq olunur:</p>' +
                '<ul style="text-align:left;color:#555;margin:1rem 2rem;">' +
                (this.config.force_fullscreen ? "<li>Tam ekran rejimi tələb olunur</li>" : "") +
                (this.config.detect_tab_switch ? "<li>Tab dəyişmə izlənilir</li>" : "") +
                (this.config.block_copy_paste ? "<li>Kopyala/yapışdır bloklanıb</li>" : "") +
                (this.config.disable_right_click ? "<li>Sağ klik deaktivdir</li>" : "") +
                (this.config.restrict_keyboard_shortcuts ? "<li>Klaviatura qısa yolları məhduddur</li>" : "") +
                "</ul>" +
                '<p style="color:#dc3545;font-weight:bold;">Maksimum ' +
                this.maxViolations +
                " pozuntuya icazə verilir.</p>" +
                '<button id="supervision-acknowledge-btn" style="margin-top:1.5rem;padding:0.75rem 2rem;background:#007bff;color:#fff;border:none;border-radius:8px;font-size:1rem;cursor:pointer;">' +
                '<i class="fas fa-check"></i> Başa düşdüm, davam et</button>' +
                "</div>";
            document.body.appendChild(overlay);

            document.getElementById("supervision-acknowledge-btn").addEventListener("click", function () {
                overlay.remove();
                ExamSupervision._requestFullscreen();
                ExamSupervision._logEvent("student_acknowledged");
            });
        },

        _bindEvents: function () {
            // Fullscreen change
            document.addEventListener("fullscreenchange", this._onFullscreenChange.bind(this));
            document.addEventListener("webkitfullscreenchange", this._onFullscreenChange.bind(this));

            // Visibility / focus
            if (this.config.detect_tab_switch) {
                document.addEventListener("visibilitychange", this._onVisibilityChange.bind(this));
                window.addEventListener("blur", this._onWindowBlur.bind(this));
                window.addEventListener("focus", this._onWindowFocus.bind(this));
            }

            // Copy/Paste
            if (this.config.block_copy_paste) {
                document.addEventListener("copy", this._onCopy.bind(this));
                document.addEventListener("paste", this._onPaste.bind(this));
                document.addEventListener("cut", this._onCut.bind(this));
            }

            // Right click
            if (this.config.disable_right_click) {
                document.addEventListener("contextmenu", this._onContextMenu.bind(this));
            }

            // Text selection
            if (this.config.disable_text_selection) {
                document.addEventListener("selectstart", this._onSelectStart.bind(this));
                document.addEventListener("dragstart", this._onDragStart.bind(this));
            }

            // Keyboard shortcuts
            if (this.config.restrict_keyboard_shortcuts) {
                document.addEventListener("keydown", this._onKeyDown.bind(this));
            }
        },

        _onFullscreenChange: function () {
            const isFS =
                !!document.fullscreenElement || !!document.webkitFullscreenElement;
            this.isFullscreen = isFS;

            if (!isFS && this.config.force_fullscreen && this.isActive) {
                this._showWarning("Tam ekrandan çıxdınız!", "Zəhmət olmasa tam ekrana qayıdın.");
                this._logEvent("fullscreen_exited");
                this._startGraceTimer();
            } else if (isFS) {
                this._hideWarning();
                this._clearGraceTimer();
                this._logEvent("fullscreen_restored");
            }
        },

        _onVisibilityChange: function () {
            if (document.hidden && this.isActive) {
                this._logEvent("tab_switched");
                this._incrementViolation();
            }
        },

        _onWindowBlur: function () {
            if (this.isActive) {
                this._logEvent("window_blurred");
            }
        },

        _onWindowFocus: function () {
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
            this._logEvent("text_select_attempt");
        },

        _onDragStart: function (e) {
            e.preventDefault();
        },

        _onKeyDown: function (e) {
            const blocked = [
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

            for (const combo of blocked) {
                const ctrlMatch = combo.ctrl ? e.ctrlKey || e.metaKey : true;
                const shiftMatch = combo.shift === undefined || combo.shift === e.shiftKey;
                const keyMatch = e.key && e.key.toLowerCase() === combo.key.toLowerCase();

                if (ctrlMatch && shiftMatch && keyMatch) {
                    // Allow Ctrl+C/V/X in input fields
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
            const el = document.documentElement;
            if (el.requestFullscreen) {
                el.requestFullscreen().catch(function () {});
            } else if (el.webkitRequestFullscreen) {
                el.webkitRequestFullscreen();
            }
        },

        _showWarning: function (title, message) {
            if (!this.warningModal) return;
            document.getElementById("supervision-warning-title").textContent = title;
            document.getElementById("supervision-warning-message").textContent = message;
            document.getElementById("supervision-violation-badge").textContent =
                "Pozuntu: " + this.violationCount + " / " + this.maxViolations;
            this.warningModal.style.display = "flex";
        },

        _hideWarning: function () {
            if (this.warningModal) {
                this.warningModal.style.display = "none";
            }
        },

        _startGraceTimer: function () {
            this._clearGraceTimer();
            let remaining = this.gracePeriodSeconds;
            const countdownEl = document.getElementById("supervision-countdown");
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
        },

        _incrementViolation: function () {
            this.violationCount++;
            this._updateBadge();

            if (this.violationCount >= this.maxViolations) {
                this._onLimitExceeded();
            }
        },

        _updateBadge: function () {
            const badge = document.getElementById("supervision-badge-count");
            if (badge) {
                badge.textContent = this.violationCount + "/" + this.maxViolations;
            }
            const modalBadge = document.getElementById("supervision-violation-badge");
            if (modalBadge) {
                modalBadge.textContent = "Pozuntu: " + this.violationCount + " / " + this.maxViolations;
            }
        },

        _onLimitExceeded: function () {
            this.isActive = false;
            this._hideWarning();

            const overlay = document.createElement("div");
            overlay.id = "supervision-locked-overlay";
            overlay.style.cssText =
                "position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);" +
                "z-index:100001;display:flex;justify-content:center;align-items:center;";
            overlay.innerHTML =
                '<div style="background:#fff;border-radius:12px;padding:2.5rem;max-width:500px;width:90%;text-align:center;">' +
                '<div style="font-size:4rem;color:#dc3545;margin-bottom:1rem;"><i class="fas fa-ban"></i></div>' +
                "<h2 style=\"color:#dc3545;\">İmtahan Dayandırıldı</h2>" +
                '<p style="color:#555;margin:1rem 0;">Maksimum pozuntu limitinə çatdınız (' +
                this.maxViolations +
                " pozuntu).</p>" +
                '<p style="color:#555;">İmtahanınız dayandırılıb. Müəllim qərar qəbul edənə qədər gözləyin.</p>' +
                '<div style="margin-top:1.5rem;"><div class="spinner-border text-secondary" role="status"></div></div>' +
                '<p style="color:#999;font-size:0.85rem;margin-top:1rem;">Müəllim cavabını gözləyirik...</p>' +
                "</div>";
            document.body.appendChild(overlay);

            // Poll for status changes
            this._startStatusPolling();
        },

        _startStatusPolling: function () {
            const poll = setInterval(function () {
                ExamSupervision._checkSupervisionStatus(function (data) {
                    if (data.supervision_status === "resumed" || data.supervision_status === "active") {
                        clearInterval(poll);
                        const overlay = document.getElementById("supervision-locked-overlay");
                        if (overlay) overlay.remove();
                        ExamSupervision.isActive = true;
                        ExamSupervision.violationCount = data.violation_count || 0;
                        ExamSupervision.maxViolations = data.max_violations || ExamSupervision.maxViolations;
                        ExamSupervision._updateBadge();
                        if (ExamSupervision.config.force_fullscreen) {
                            ExamSupervision._requestFullscreen();
                        }
                    } else if (data.is_finished) {
                        clearInterval(poll);
                        window.location.reload();
                    }
                });
            }, 5000);
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
