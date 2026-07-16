import { ExamSupervision } from "./state.js?v=20260716-intervention";

Object.assign(ExamSupervision, {
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
});
