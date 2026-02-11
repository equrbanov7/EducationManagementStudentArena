document.addEventListener('DOMContentLoaded', () => {
    // CONFIG artıq template-dən gəlir (global dəyişən)

    // Avatar emoji-ləri
    const AVATAR_EMOJIS = {
        "avatar_1": "🦊",
        "avatar_2": "🐼",
        "avatar_3": "🦁",
        "avatar_4": "🐯",
        "avatar_5": "🐨",
        "avatar_6": "🐷",
        "avatar_7": "🐙",
        "avatar_8": "🦄",
        "avatar_9": "🐸",
        "avatar_10": "🐰",
        "avatar_11": "🐻",
        "avatar_12": "🐶"
    };

    // Avatar grid-i doldur
    const avatarGrid = document.getElementById('avatarGrid');
    if (!avatarGrid) return;
    
    let selectedAvatar = null;

    Object.entries(AVATAR_EMOJIS).forEach(([key, emoji]) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'avatar-btn';
        btn.dataset.key = key;
        btn.textContent = emoji;
        
        btn.addEventListener('click', () => {
            document.querySelectorAll('.avatar-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            selectedAvatar = key;
        });
        
        avatarGrid.appendChild(btn);
    });

    // Auto-select first avatar
    const firstBtn = avatarGrid.querySelector('.avatar-btn');
    if (firstBtn) {
        firstBtn.click();
    }

    // Join button
    const joinBtn = document.getElementById('joinBtn');
    if (!joinBtn) return;

    joinBtn.addEventListener('click', async () => {
        const nickname = document.getElementById('nickname').value.trim();
        
        if (!nickname) {
            document.getElementById('nickname').focus();
            document.getElementById('nickname').style.borderColor = '#ef4444';
            return;
        }

        if (!selectedAvatar) {
            alert('Avatar seç!');
            return;
        }

        joinBtn.disabled = true;
        joinBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Qoşulur...';

        try {
            const formData = new FormData();
            formData.append('nickname', nickname);
            formData.append('avatar_key', selectedAvatar);

            const res = await fetch(CONFIG.joinUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': CONFIG.csrf
                },
                body: formData
            });

            const data = await res.json();

            if (data.ok) {
                window.location.href = data.redirect;
            } else {
                alert(data.message || 'Xəta baş verdi');
                joinBtn.disabled = false;
                joinBtn.innerHTML = '<i class="fas fa-play me-2"></i> Oyuna Qoşul!';
            }
        } catch (err) {
            console.error(err);
            alert('Bağlantı xətası');
            joinBtn.disabled = false;
            joinBtn.innerHTML = '<i class="fas fa-play me-2"></i> Oyuna Qoşul!';
        }
    });

    // Enter key to submit
    const nicknameInput = document.getElementById('nickname');
    if (nicknameInput) {
        nicknameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                joinBtn.click();
            }
        });

        // Reset border color on input
        nicknameInput.addEventListener('input', function() {
            this.style.borderColor = '#e5e7eb';
        });
    }
});