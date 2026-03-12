document.addEventListener("DOMContentLoaded", function () {
    const i18n = window.LIVE_EXAM_JOIN_I18N || {};
    const tr = (key, fallback) => i18n[key] || fallback;
    const catalog = window.LiveAvatarCatalog || {};
    const rememberedPlayer = CONFIG.rememberedPlayer || null;

    const avatarGrid = document.getElementById("avatarGrid");
    const joinBtn = document.getElementById("joinBtn");
    const nicknameInput = document.getElementById("nickname");
    const resumeNoticeBtn = document.getElementById("resumePlayerBtn");
    const resumePrompt = document.getElementById("joinResumePrompt");
    const resumeContinueBtn = document.getElementById("joinResumeContinue");
    const resumeRestartBtn = document.getElementById("joinResumeRestart");
    const resumeCloseBtn = document.getElementById("joinResumeClose");
    if (!avatarGrid || !joinBtn || !nicknameInput) return;

    let selectedAvatar = rememberedPlayer?.avatar_key || catalog.defaultAvatarKey || "avatar_1";
    let allowFreshJoin = !rememberedPlayer;

    if (!nicknameInput.value.trim() && rememberedPlayer?.nickname) {
        nicknameInput.value = rememberedPlayer.nickname;
    }

    (catalog.avatarKeys || []).forEach(function (avatarKey) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "avatar-btn";
        button.dataset.key = avatarKey;
        button.innerHTML = window.LiveAvatarRenderer.renderAvatarMarkup(
            { avatar_key: avatarKey, accessory_key: catalog.defaultAccessoryKey || "accessory_none" },
            { size: 52, className: "join-avatar", interactive: false }
        );
        button.addEventListener("click", function () {
            selectedAvatar = avatarKey;
            avatarGrid.querySelectorAll(".avatar-btn").forEach(function (candidate) {
                candidate.classList.toggle("selected", candidate === button);
            });
        });
        avatarGrid.appendChild(button);
    });

    const initialAvatarButton =
        avatarGrid.querySelector(`.avatar-btn[data-key="${selectedAvatar}"]`) || avatarGrid.querySelector(".avatar-btn");
    initialAvatarButton?.click();

    function openResumePrompt() {
        if (!resumePrompt) return;
        resumePrompt.hidden = false;
        document.body.classList.add("join-modal-open");
    }

    function closeResumePrompt() {
        if (!resumePrompt) return;
        resumePrompt.hidden = true;
        document.body.classList.remove("join-modal-open");
    }

    function continuePreviousPlayer() {
        closeResumePrompt();
        window.location.href = CONFIG.resumeUrl;
    }

    async function submitJoin() {
        const nickname = nicknameInput.value.trim();
        if (!nickname) {
            nicknameInput.focus();
            nicknameInput.style.borderColor = "#ef4444";
            return;
        }

        if (!selectedAvatar) {
            window.alert(tr("alertSelectAvatar", "Select an avatar!"));
            return;
        }

        joinBtn.disabled = true;
        joinBtn.innerHTML = `<i class="fas fa-spinner fa-spin me-2"></i> ${tr("buttonJoining", "Joining...")}`;

        try {
            const formData = new FormData();
            formData.append("nickname", nickname);
            formData.append("avatar_key", selectedAvatar);

            const res = await fetch(CONFIG.joinUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": CONFIG.csrf
                },
                body: formData
            });

            const data = await res.json();
            if (data.ok) {
                window.location.href = data.redirect;
                return;
            }

            window.alert(data.message || tr("errorUnknown", "An error occurred"));
        } catch (error) {
            console.error(error);
            window.alert(tr("errorConnection", "Connection error"));
        } finally {
            joinBtn.disabled = false;
            joinBtn.innerHTML = `<i class="fas fa-play me-2"></i> ${tr("buttonJoin", "Join Game")}`;
        }
    }

    joinBtn.addEventListener("click", function () {
        if (rememberedPlayer && !allowFreshJoin) {
            openResumePrompt();
            return;
        }
        submitJoin();
    });

    resumeNoticeBtn?.addEventListener("click", continuePreviousPlayer);
    resumeContinueBtn?.addEventListener("click", continuePreviousPlayer);
    resumeRestartBtn?.addEventListener("click", function () {
        allowFreshJoin = true;
        closeResumePrompt();
        submitJoin();
    });
    resumeCloseBtn?.addEventListener("click", closeResumePrompt);
    resumePrompt?.addEventListener("click", function (event) {
        if (event.target === resumePrompt) {
            closeResumePrompt();
        }
    });

    nicknameInput.addEventListener("keypress", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            joinBtn.click();
        }
    });

    nicknameInput.addEventListener("input", function () {
        this.style.borderColor = "#e5e7eb";
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            closeResumePrompt();
        }
    });
});
