/* wait_room.js */

// Emojilər (Digər fayllarla eyni olmalıdır)
const AVATARS = {
    'avatar_1': '🦊', 'avatar_2': '🐼', 'avatar_3': '🦁', 'avatar_4': '🐯',
    'avatar_5': '🐨', 'avatar_6': '🐷', 'avatar_7': '🐸', 'avatar_8': '🐙',
    'avatar_9': '🐵', 'avatar_10': '🦄', 'avatar_11': '🐰', 'avatar_12': '🐹'
};

const els = {
    myAvatar: document.getElementById("myAvatar"),
    myNickname: document.getElementById("myNickname"),
    list: document.getElementById("playersList"),
    count: document.getElementById("count"),
    wsStatus: document.getElementById("wsStatus")
};

// 1. Mənim Avatarımı Render Et
// HTML-dən gələn açarı (məs: 'avatar_2') emojiyə çevirir
const myKey = CONFIG.myAvatarKey; 
const myEmoji = AVATARS[myKey] || '👤';
if(els.myAvatar) els.myAvatar.textContent = myEmoji;

// 2. Oyunçuları Render Et
function renderPlayers(players) {
    const arr = Array.isArray(players) ? players : [];
    if(els.count) els.count.textContent = arr.length;

    if(els.list) {
        els.list.innerHTML = "";
        arr.forEach(p => {
            // Özümüzü siyahıda göstərmirik (artıq yuxarıda böyük şəkildə var)
            if (p.nickname === CONFIG.myNickname) return; 

            const div = document.createElement("div");
            div.className = "mini-player";
            const emoji = AVATARS[p.avatar_key] || '👤';
            div.innerHTML = `<div style="font-size:1.5rem">${emoji}</div><div>${p.nickname}</div>`;
            els.list.appendChild(div);
        });
    }
}

// İlkin yükləmə
try {
    const initial = JSON.parse(document.getElementById("initialPlayers").textContent || "[]");
    renderPlayers(initial);
} catch (e) {
    console.error("Initial parsing error", e);
}

// 3. WebSocket Logic
function wsUrl() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}${CONFIG.wsPath}`;
}

let socket = null;
let reconnectTimer = null;

function connectWs() {
    if (reconnectTimer) clearTimeout(reconnectTimer);

    if(els.wsStatus) els.wsStatus.textContent = "Bağlantı qurulur...";
    
    socket = new WebSocket(wsUrl());

    socket.onopen = () => {
        if(els.wsStatus) {
            els.wsStatus.textContent = "Onlayn ✅";
            els.wsStatus.style.color = "#00c853";
        }
    };

    socket.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            const payload = msg.data ? msg.data : msg;

            // OYUN BAŞLADI -> Redirect
            if (payload.type === "game_started" && payload.redirect) {
                window.location.href = payload.redirect;
                return;
            }

            // LOBBY UPDATE -> Siyahını yenilə
            if (payload.type === "lobby_state" && Array.isArray(payload.players)) {
                renderPlayers(payload.players);
            }
        } catch (_) {}
    };

    socket.onclose = () => {
        if(els.wsStatus) {
            els.wsStatus.textContent = "Bağlantı kəsildi ❌";
            els.wsStatus.style.color = "#ff4081";
        }
        reconnectTimer = setTimeout(connectWs, 2000);
    };
}

connectWs();