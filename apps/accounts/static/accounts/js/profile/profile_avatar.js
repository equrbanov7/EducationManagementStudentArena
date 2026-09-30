/* Profil şəkli — yerində yüklə / dəyiş / sil (2026-10-01, sahib).
 *
 * «Profil şəkli tərəfini yenidən düzəlt … şəkli qoymaq olduğu kimi silmək də
 * mümkün olsun». İki səth, bir davranış:
 *   * kimlik başlığı (`_profile_info_identity.html`): kamera düyməsi menyusu →
 *     fayl seçimi → `data-avatar-modal` modalında önizləmə → «Şəkli yenilə»;
 *   * redaktə bölməsi (`_avatar_editor.html`): seçim → dairədə önizləmə →
 *     yerində «Yadda saxla / Ləğv et».
 * «Sil» hər ikisində EMSConfirm ilə təsdiqlənir. Server: accounts:profile_avatar_api
 * (`[data-avatar-scope][data-api-url]`). Uğurdan sonra səhifədəki BÜTÜN
 * `[data-avatar-display]` yerləri və navbar avatarı yenilənir (reload yoxdur).
 *
 * AJAX-safe: hər şey `EMSDelegate` (document) + `EMSReady.once` — bölmə swap
 * olsa da işləyir; seçicilər `[data-avatar-scope]` ilə unikallaşdırılıb
 * (EMSDelegate açarı hadisə+seçicidir, başqa modulun handler-ini əvəzləməsin).
 */
(function (window, document) {
    "use strict";

    var ALLOWED_TYPES = /^image\/(jpeg|png|webp|gif)$/i;
    var ALLOWED_EXT = /\.(jpe?g|png|webp|gif)$/i;
    var pending = null; // { scope, file, url }

    function scopeOf(node) {
        return node && node.closest ? node.closest("[data-avatar-scope]") : null;
    }

    function scopeForModal(modalEl) {
        if (!modalEl || !modalEl.id) {
            return null;
        }
        return document.querySelector('[data-avatar-scope][data-avatar-modal="#' + modalEl.id + '"]');
    }

    function modalFor(scope) {
        var selector = scope && scope.dataset.avatarModal;
        var element = selector ? document.querySelector(selector) : null;
        if (!element || !window.bootstrap || !window.bootstrap.Modal) {
            return null;
        }
        return { element: element, api: window.bootstrap.Modal.getOrCreateInstance(element) };
    }

    function releasePending() {
        if (pending && pending.url && window.URL && window.URL.revokeObjectURL) {
            window.URL.revokeObjectURL(pending.url);
        }
        pending = null;
    }

    function setBusy(button, busy) {
        if (!button) {
            return;
        }
        button.disabled = busy;
        var spinner = button.querySelector(".spinner-border");
        if (spinner) {
            spinner.classList.toggle("d-none", !busy);
        }
    }

    function errorRegion(scope) {
        var modal = modalFor(scope);
        return modal
            ? modal.element.querySelector("[data-avatar-modal-error]")
            : scope.querySelector("[data-avatar-error]");
    }

    function showError(scope, message) {
        var region = scope ? errorRegion(scope) : null;
        if (!region) {
            return;
        }
        region.textContent = message || "";
        region.hidden = !message;
    }

    function renderDisplay(display, url, initials) {
        var img = display.querySelector("[data-avatar-img]");
        var initialsNode = display.querySelector("[data-avatar-initials]");
        if (url && img) {
            img.src = url;
            img.hidden = false;
            if (initialsNode) {
                initialsNode.hidden = true;
            }
            return;
        }
        if (img) {
            img.removeAttribute("src");
            img.hidden = true;
        }
        if (initialsNode) {
            if (initials) {
                initialsNode.textContent = initials;
            }
            initialsNode.hidden = false;
        }
    }

    function setIdle(scope) {
        scope.querySelectorAll("[data-avatar-idle]").forEach(function (node) {
            node.hidden = false;
        });
        scope.querySelectorAll("[data-avatar-confirm]").forEach(function (node) {
            node.hidden = true;
        });
        var hint = scope.querySelector("[data-avatar-hint]");
        if (hint && hint.dataset.labelDefault) {
            hint.textContent = hint.dataset.labelDefault;
        }
    }

    function restoreScope(scope) {
        var display = scope.querySelector("[data-avatar-display]");
        if (display) {
            renderDisplay(display, scope.dataset.hasAvatar === "1" ? scope.dataset.avatarUrl : "", "");
        }
        setIdle(scope);
    }

    /* Navbar (desktop menyu + mobil panel) — `_navbar.html` markup-u dəyişmədən. */
    function updateNavbar(state) {
        document.querySelectorAll(".blog-header__user-avatar, .blog-header__user-head-avatar").forEach(function (slot) {
            var isHead = slot.classList.contains("blog-header__user-head-avatar");
            var initialsClass = isHead ? "blog-header__user-head-initials" : "blog-header__user-avatar-initials";
            var img = slot.querySelector("img.blog-header__user-avatar-image");
            var initialsNode = slot.querySelector("." + initialsClass);
            if (state.has_avatar) {
                if (!img) {
                    img = document.createElement("img");
                    img.className = "blog-header__user-avatar-image";
                    img.alt = "";
                    slot.insertBefore(img, slot.firstChild);
                }
                img.src = state.avatar_url;
                if (initialsNode) {
                    initialsNode.classList.add("d-none");
                }
                slot.classList.add("blog-header__user-avatar--image");
                return;
            }
            if (img) {
                img.parentNode.removeChild(img);
            }
            if (!initialsNode) {
                initialsNode = document.createElement("span");
                initialsNode.className = initialsClass;
                slot.appendChild(initialsNode);
            }
            initialsNode.textContent = state.initial || "";
            initialsNode.classList.remove("d-none");
            slot.classList.remove("blog-header__user-avatar--image");
        });
    }

    function applyState(state) {
        var url = state.has_avatar ? state.avatar_url : "";
        document.querySelectorAll("[data-avatar-scope]").forEach(function (scope) {
            scope.dataset.hasAvatar = state.has_avatar ? "1" : "";
            scope.dataset.avatarUrl = url;
            scope.querySelectorAll("[data-avatar-remove], [data-avatar-remove-wrap]").forEach(function (node) {
                node.hidden = !state.has_avatar;
            });
            scope.querySelectorAll("[data-avatar-pick-label]").forEach(function (node) {
                node.textContent = state.has_avatar ? scope.dataset.labelPickChange : scope.dataset.labelPickNew;
            });
            setIdle(scope);
            showError(scope, "");
        });
        document.querySelectorAll("[data-avatar-display]").forEach(function (display) {
            renderDisplay(display, url, state.initials);
        });
        updateNavbar(state);
    }

    function toast(message, level) {
        if (message && window.EMSToast && typeof window.EMSToast.show === "function") {
            window.EMSToast.show(message, level || "success");
        }
    }

    function post(scope, fields) {
        var body = new window.FormData();
        Object.keys(fields).forEach(function (key) {
            if (fields[key] instanceof window.File) {
                body.append(key, fields[key], fields[key].name);
            } else {
                body.append(key, fields[key]);
            }
        });
        return window.EMSCore.fetchJSON(scope.dataset.apiUrl, { method: "POST", body: body });
    }

    function errorFrom(error, scope) {
        if (error && error.payload && typeof error.payload === "object" && error.payload.error) {
            return String(error.payload.error);
        }
        return scope.dataset.labelError || "Error";
    }

    function validate(scope, file) {
        var maxBytes = parseInt(scope.dataset.maxBytes || "0", 10);
        var typeOk = file.type ? ALLOWED_TYPES.test(file.type) : ALLOWED_EXT.test(file.name || "");
        if (!typeOk) {
            return scope.dataset.labelBadType || "";
        }
        if (maxBytes && file.size > maxBytes) {
            return scope.dataset.labelTooBig || "";
        }
        return "";
    }

    function openPreview(scope, file) {
        var modal = modalFor(scope);
        var problem = validate(scope, file);
        releasePending();
        if (!problem) {
            pending = { scope: scope, file: file, url: window.URL.createObjectURL(file) };
        }
        if (modal) {
            var preview = modal.element.querySelector("[data-avatar-preview]");
            var empty = modal.element.querySelector("[data-avatar-preview-empty]");
            var name = modal.element.querySelector("[data-avatar-file-name]");
            var save = modal.element.querySelector("[data-avatar-save]");
            if (preview) {
                if (pending) {
                    preview.src = pending.url;
                } else {
                    preview.removeAttribute("src");
                }
                preview.hidden = !pending;
            }
            if (empty) {
                empty.hidden = Boolean(pending);
            }
            if (name) {
                name.textContent = file.name || "";
            }
            if (save) {
                save.disabled = !pending;
            }
            showError(scope, problem);
            modal.api.show();
            return;
        }
        showError(scope, problem);
        if (!pending) {
            return;
        }
        var display = scope.querySelector("[data-avatar-display]");
        if (display) {
            renderDisplay(display, pending.url, "");
        }
        scope.querySelectorAll("[data-avatar-idle]").forEach(function (node) {
            node.hidden = true;
        });
        scope.querySelectorAll("[data-avatar-confirm]").forEach(function (node) {
            node.hidden = false;
        });
        var hint = scope.querySelector("[data-avatar-hint]");
        if (hint) {
            hint.textContent = file.name || "";
        }
    }

    function pick(scope) {
        var input = scope ? scope.querySelector("[data-avatar-input]") : null;
        if (input) {
            input.value = "";
            input.click();
        }
    }

    function save(scope, button) {
        if (!scope || !pending || pending.scope !== scope) {
            return;
        }
        showError(scope, "");
        setBusy(button, true);
        post(scope, { action: "upload", avatar: pending.file })
            .then(function (payload) {
                var modal = modalFor(scope);
                releasePending();
                applyState(payload || {});
                if (modal) {
                    modal.api.hide();
                }
                toast(payload && payload.message, "success");
            })
            .catch(function (error) {
                showError(scope, errorFrom(error, scope));
            })
            .finally(function () {
                setBusy(button, false);
            });
    }

    function remove(scope, button) {
        var ask = window.EMSConfirm
            ? window.EMSConfirm.open({
                  title: scope.dataset.labelRemoveTitle || "",
                  body: scope.dataset.labelRemoveBody || "",
                  confirmLabel: scope.dataset.labelRemoveConfirm || "",
                  danger: true,
              })
            : Promise.resolve(false); // EMSConfirm yüklənməyibsə silmə edilmir (native confirm qadağandır)
        ask.then(function (ok) {
            if (!ok) {
                return;
            }
            setBusy(button, true);
            post(scope, { action: "remove" })
                .then(function (payload) {
                    releasePending();
                    applyState(payload || {});
                    toast(payload && payload.message, "success");
                })
                .catch(function (error) {
                    var message = errorFrom(error, scope);
                    showError(scope, modalFor(scope) ? "" : message);
                    if (modalFor(scope)) {
                        toast(message, "error");
                    }
                })
                .finally(function () {
                    setBusy(button, false);
                });
        });
    }

    window.EMSReady.once("accounts/profile/profile_avatar", function () {
        window.EMSDelegate.on("click", "[data-avatar-scope] [data-avatar-pick]", function (event, button) {
            event.preventDefault();
            pick(scopeOf(button));
        });

        window.EMSDelegate.on("click", "[data-avatar-pick-again]", function (event, button) {
            event.preventDefault();
            pick(scopeForModal(button.closest(".modal")));
        });

        window.EMSDelegate.on("change", "[data-avatar-scope] [data-avatar-input]", function (event, input) {
            var file = input.files && input.files.length ? input.files[0] : null;
            var scope = scopeOf(input);
            if (file && scope) {
                openPreview(scope, file);
            }
        });

        window.EMSDelegate.on("click", "[data-avatar-scope] [data-avatar-save]", function (event, button) {
            event.preventDefault();
            save(scopeOf(button), button);
        });

        window.EMSDelegate.on("submit", "[data-avatar-modal-form]", function (event, form) {
            event.preventDefault();
            save(scopeForModal(form.closest(".modal")), form.querySelector("[data-avatar-save]"));
        });

        window.EMSDelegate.on("click", "[data-avatar-scope] [data-avatar-cancel]", function (event, button) {
            event.preventDefault();
            var scope = scopeOf(button);
            releasePending();
            if (scope) {
                showError(scope, "");
                restoreScope(scope);
            }
        });

        window.EMSDelegate.on("click", "[data-avatar-scope] [data-avatar-remove]", function (event, button) {
            event.preventDefault();
            var scope = scopeOf(button);
            if (scope) {
                remove(scope, button);
            }
        });

        // Modal bağlananda (Ləğv et / X / fon) seçilmiş, saxlanmamış fayl atılır.
        document.addEventListener("hidden.bs.modal", function (event) {
            var scope = scopeForModal(event.target);
            if (scope && pending && pending.scope === scope) {
                releasePending();
            }
        });

        // Şəkil yüklənmədisə (silinmiş fayl, şəbəkə) baş hərflərə düş. `error`
        // hadisəsi bubble etmir — capture fazasında tutulur.
        document.addEventListener(
            "error",
            function (event) {
                var img = event.target;
                if (!img || img.tagName !== "IMG" || !img.hasAttribute("data-avatar-img") || !img.getAttribute("src")) {
                    return;
                }
                var display = img.closest("[data-avatar-display]");
                if (display) {
                    renderDisplay(display, "", "");
                }
            },
            true
        );
    });
})(window, document);
