import { ExamSupervision } from "./state.js?v=20260914-w4r3";

Object.assign(ExamSupervision, {
        // Status sorğusu — WS-in dublikatı yox, EHTİYAT yoludur (2026-09-14, w3sweep R3).
        // Əvvəl WS bağlı olanda da hər 1 s sorğu gedirdi (300 tələbə = 300 sorğu/s).
        // İndi:
        //   • WS açıqdır  → 15 s-lik heartbeat (müəllim əməli onsuz da WS ilə gəlir);
        //   • WS yoxdur   → 2 s-dən başlayan, 10 s-ə qədər ikiqat artan backoff;
        //   • `visibilitychange` (görünən oldu) / `online` / WS qırıldı → dərhal bir sorğu;
        //   • 429 (server limiti) → Retry-After qədər gözlə.
        // Backoff hər poller üçün ayrıdır (fon nəzarəti və kilid gözləməsi paylaşmır).
        _bgHeartbeatMs: 15000,
        _bgBackoffMinMs: 2000,
        _bgBackoffMaxMs: 10000,
        _bgWatchActive: false,
        _bgStatusWatch: null,
        _bgInFlight: false,
        _bgPoller: null,
        _statusRetryAfterUntil: 0,

        _isWsOpen: function () {
            var sock = this._wsSocket;
            return !!(sock && sock.readyState === 1);
        },

        _newStatusPoller: function () {
            return { backoffMs: this._bgBackoffMinMs };
        },

        // Növbəti sorğuya qədər gözləmə — WS açıqdırsa heartbeat, yoxdursa backoff.
        _nextStatusDelayMs: function (poller) {
            var retryWait = this._statusRetryAfterUntil - Date.now();
            if (retryWait > 0) return retryWait;
            if (this._isWsOpen()) {
                poller.backoffMs = this._bgBackoffMinMs;
                return this._bgHeartbeatMs;
            }
            var delay = poller.backoffMs;
            poller.backoffMs = Math.min(delay * 2, this._bgBackoffMaxMs);
            return delay;
        },

        // Serverin 429 cavabı → Retry-After (saniyə) qədər heç bir poller sorğu göndərmir.
        _noteStatusRetryAfter: function (seconds) {
            var wait = Math.max(1, parseInt(seconds, 10) || 1) * 1000;
            this._statusRetryAfterUntil = Date.now() + wait;
        },

        // WS bağlandı → backoff sıfırlanır; qırıldı / onlayn oldu / görünən oldu → dərhal yoxla.
        _onTransportStateChange: function (checkNow) {
            if (this._bgPoller) this._bgPoller.backoffMs = this._bgBackoffMinMs;
            if (this._lockPoller) this._lockPoller.backoffMs = this._bgBackoffMinMs;
            if (checkNow) this._kickBackgroundStatusCheck();
        },

        _kickBackgroundStatusCheck: function () {
            if (!this._bgWatchActive || this._bgInFlight) return;
            this._scheduleBackgroundStatusTick(0);
        },

        _scheduleBackgroundStatusTick: function (delayMs) {
            if (!this._bgWatchActive) return;
            if (this._bgStatusWatch) clearTimeout(this._bgStatusWatch);
            var self = this;
            this._bgStatusWatch = setTimeout(function () {
                self._bgStatusWatch = null;
                self._backgroundStatusTick();
            }, delayMs);
        },

        _backgroundStatusTick: function () {
            if (!this._bgWatchActive || this._bgInFlight) return;
            var self = this;
            var scheduleNext = function () {
                self._bgInFlight = false;
                self._scheduleBackgroundStatusTick(self._nextStatusDelayMs(self._bgPoller));
            };
            if (!this.isActive ||
                document.getElementById("supervision-teacher-lock-overlay") ||
                document.getElementById("supervision-locked-overlay")) {
                // Kilid overlay-i öz pollerini işlədir — fon nəzarəti yalnız növbəni saxlayır.
                scheduleNext();
                return;
            }
            this._bgInFlight = true;
            this._checkSupervisionStatus(function (data) {
                if (!data) return;
                if (data.is_finished) {
                    // Teacher removed / auto-finished the attempt → leave the
                    // exam immediately (result page) instead of waiting.
                    if (data.intervention_action || data.intervention_reason) {
                        self._showRemovalOverlay(data.intervention_reason, data.intervention_action);
                    } else {
                        self._leaveToResult();
                    }
                    return;
                }
                if (data.supervision_status === "locked") {
                    if (data.manual_lock) {
                        self._showTeacherLockOverlay(data.intervention_reason);
                    } else {
                        self._onLimitExceeded();
                    }
                }
            }, scheduleNext);
        },

        _startBackgroundStatusWatch: function () {
            if (this._bgWatchActive) return;
            this._bgWatchActive = true;
            this._bgPoller = this._newStatusPoller();
            this._scheduleBackgroundStatusTick(this._bgBackoffMinMs);
            this._bindTransportWakeups();
        },

        _stopBackgroundStatusWatch: function () {
            this._bgWatchActive = false;
            this._bgInFlight = false;
            if (this._bgStatusWatch) {
                clearTimeout(this._bgStatusWatch);
                this._bgStatusWatch = null;
            }
        },

        _transportWakeupsBound: false,
        _bindTransportWakeups: function () {
            if (this._transportWakeupsBound) return;
            this._transportWakeupsBound = true;
            var self = this;
            document.addEventListener("visibilitychange", function () {
                if (document.visibilityState === "visible") self._onTransportStateChange(true);
            });
            window.addEventListener("online", function () {
                self._onTransportStateChange(true);
            });
        },

        // W4 2026-09-14 (w3sweep R3): kilid overlay-i altındakı poll da WS-first —
        // WS açıqdırsa 15 s heartbeat (davam etmə WS ilə gəlir), yoxdursa 2→10 s backoff.
        // `handler(data)` true qaytaranda poll dayanır. İki kilid növü eyni polleri paylaşır.
        _lockPoller: null,
        _lockPollTimer: null,
        _lockPollInFlight: false,
        _startLockStatusPolling: function (handler) {
            if (this._lockPoller) return;
            var self = this;
            this._lockPoller = this._newStatusPoller ? this._newStatusPoller() : { backoffMs: 2000 };
            var tick = function () {
                self._lockPollTimer = null;
                if (!self._lockPoller || self._lockPollInFlight) return;
                self._lockPollInFlight = true;
                var done = false;
                self._checkSupervisionStatus(function (data) {
                    if (!data) return;
                    done = !!handler(data);
                }, function () {
                    self._lockPollInFlight = false;
                    if (!self._lockPoller) return;
                    if (done) {
                        self._stopLockStatusPolling();
                        return;
                    }
                    var delay = self._nextStatusDelayMs ? self._nextStatusDelayMs(self._lockPoller) : 2000;
                    self._lockPollTimer = setTimeout(tick, delay);
                });
            };
            this._lockPollTimer = setTimeout(tick, this._lockPoller.backoffMs);
        },

        _stopLockStatusPolling: function () {
            this._lockPoller = null;
            this._lockPollInFlight = false;
            if (this._lockPollTimer) {
                clearTimeout(this._lockPollTimer);
                this._lockPollTimer = null;
            }
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
});
