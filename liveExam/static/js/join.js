/* join.js */

// Backend-dəki stringləri vizual Emojilərə çevirən xəritə
// Əgər backend 'avatar_13' göndərsə və burda yoxdursa, random seçəcək.
const AVATARS = {
    'avatar_1': '🦊',   // Fox
    'avatar_2': '🐼',   // Panda
    'avatar_3': '🦁',   // Lion
    'avatar_4': '🐯',   // Tiger
    'avatar_5': '🐨',   // Koala
    'avatar_6': '🐷',   // Pig
    'avatar_7': '🐸',   // Frog
    'avatar_8': '🐙',   // Octopus
    'avatar_9': '🐵',   // Monkey
    'avatar_10': '🦄',  // Unicorn
    'avatar_11': '🐰',  // Rabbit
    'avatar_12': '🐹'   // Hamster
};
const avatarContainer = document.getElementById("avatarGrid");
const joinBtn = document.getElementById("joinBtn");
const nicknameInput = document.getElementById("nickname");
let selectedAvatar = "avatar_1"; // Default

// 1. Avatarları Hazırla (Buttonlara Emoji və Click Event əlavə et)
document.querySelectorAll(".avatar-btn").forEach(btn => {
    const key = btn.dataset.key;
    
    // Mətni Emojiyə çevir
    const emoji = AVATARS[key] || '👤';
    btn.textContent = emoji;

    // Click Event
    btn.addEventListener("click", () => {
        // Hamısından selected klasını sil
        document.querySelectorAll(".avatar-btn").forEach(b => b.classList.remove("selected"));
        // Buna əlavə et
        btn.classList.add("selected");
        selectedAvatar = key;
        
        // Kiçik vibrasiya (telefonda hissiyyat üçün)
        if(navigator.vibrate) navigator.vibrate(10);
    });
});

// Default olaraq birincini seçili et
const firstBtn = document.querySelector(`.avatar-btn[data-key="${selectedAvatar}"]`) || document.querySelector(".avatar-btn");
if(firstBtn) {
    firstBtn.classList.add("selected");
    selectedAvatar = firstBtn.dataset.key;
}

// 2. Input Enter Event
nicknameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") joinBtn.click();
});

// 3. Qoşulma Məntiqi (Sənin orijinal kodun saxlanılıb)
joinBtn.addEventListener("click", async () => {
    const nickname = nicknameInput.value.trim();
    if (!nickname) {
        // Inputu silkələ (animasiya)
        nicknameInput.style.borderColor = "#ff4081";
        nicknameInput.classList.add("shake");
        setTimeout(() => nicknameInput.classList.remove("shake"), 500);
        nicknameInput.focus();
        return;
    }
    nicknameInput.style.borderColor = "#eceff1";

    // Düyməni loading rejiminə sal
    joinBtn.disabled = true;
    joinBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gözləyin...';

    const form = new FormData();
    form.append("nickname", nickname);
    form.append("avatar_key", selectedAvatar);

    try {
        const res = await fetch(CONFIG.joinUrl, {
            method: "POST",
            body: form,
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": CONFIG.csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json"
            }
        });

        let data;
        try {
            data = await res.json();
        } catch (_) {
            data = null;
        }

        if (!res.ok || !data || !data.ok) {
            const msg = (data && data.message) ? data.message : "Xəta baş verdi";
            alert(msg);
            resetBtn();
            return;
        }

        // Redirect
        if (data.redirect) {
            window.location.href = data.redirect;
            return;
        }

        // Fallback
        joinBtn.textContent = "Qoşuldu ✅";
        joinBtn.style.background = "var(--success)";

    } catch (err) {
        alert("İnternet xətası. Yenidən cəhd edin.");
        console.error(err);
        resetBtn();
    }
});

function resetBtn() {
    joinBtn.disabled = false;
    joinBtn.innerHTML = 'Hadi Başlayaq! 🚀';
}