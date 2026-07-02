import { ExamSupervision } from "./state.js?v=20260611-fresh-csrf";

Object.assign(ExamSupervision, {
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
