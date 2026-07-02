/* ═══════════════════════════════════════════════════════════════
   WAIT ROOM - WebSocket & UI Logic
   ═══════════════════════════════════════════════════════════════ */

   document.addEventListener('DOMContentLoaded', () => {
    const i18n = window.LIVE_EXAM_WAIT_ROOM_I18N || {};
    const tr = (key, fallback) => i18n[key] || fallback;
    
    // Avatar Emojis
    const AVATARS = {
        'avatar_1': '🦊', 'avatar_2': '🐼', 'avatar_3': '🦁', 'avatar_4': '🐯',
        'avatar_5': '🐨', 'avatar_6': '🐷', 'avatar_7': '🐸', 'avatar_8': '🐙',
        'avatar_9': '🐵', 'avatar_10': '🦄', 'avatar_11': '🐰', 'avatar_12': '🐹'
    };

    // DOM Elements
    const els = {
        myAvatar: document.getElementById('myAvatar'),
        myNickname: document.getElementById('myNickname'),
        playersList: document.getElementById('playersList'),
        playerCount: document.getElementById('playerCount'),
        wsStatus: document.getElementById('wsStatus')
    };

    // Set my avatar
    if (els.myAvatar && CONFIG.myAvatarKey) {
        els.myAvatar.textContent = AVATARS[CONFIG.myAvatarKey] || '👤';
    }

    // Render players
    function renderPlayers(players) {
        const arr = Array.isArray(players) ? players : [];
        
        // Update count (excluding self)
        const othersCount = arr.filter(p => p.nickname !== CONFIG.myNickname).length;
        if (els.playerCount) {
            els.playerCount.textContent = othersCount;
        }

        // Render player cards
        if (els.playersList) {
            els.playersList.innerHTML = '';
            
            arr.forEach((player, index) => {
                // Skip self
                if (player.nickname === CONFIG.myNickname) return;

                const card = document.createElement('div');
                card.className = 'player-card';
                card.style.animationDelay = `${index * 0.05}s`;

                const emoji = AVATARS[player.avatar_key] || '👤';
                
                card.innerHTML = `
                    <div class="player-avatar">${emoji}</div>
                    <div class="player-name">${escapeHtml(player.nickname)}</div>
                `;
                
                els.playersList.appendChild(card);
            });
        }
    }

    // Escape HTML to prevent XSS
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Update WebSocket status
    function updateWsStatus(status, text) {
        if (!els.wsStatus) return;
        
        els.wsStatus.className = 'ws-status ' + status;
        const statusText = els.wsStatus.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = text;
        }
    }

    // Load initial players
    try {
        const initialData = document.getElementById('initialPlayers');
        if (initialData) {
            const players = JSON.parse(initialData.textContent || '[]');
            renderPlayers(players);
        }
    } catch (e) {
        console.error('Initial players parse error:', e);
    }

    // WebSocket Connection
    function getWsUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}${CONFIG.wsPath}`;
    }

    let socket = null;
    let reconnectTimer = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;

    function connectWebSocket() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }

        updateWsStatus('', tr('wsConnecting', 'Connecting...'));

        try {
            socket = new WebSocket(getWsUrl());

            socket.onopen = () => {
                updateWsStatus('online', tr('wsOnline', 'Online'));
                reconnectAttempts = 0;
            };

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    const payload = msg.data || msg;

                    // Game started - redirect to player screen
                    if (payload.type === 'game_started' && payload.redirect) {
                        updateWsStatus('online', tr('wsStarting', 'Game is starting...'));
                        window.location.href = payload.redirect;
                        return;
                    }

                    // Lobby state update
                    if (payload.type === 'lobby_state' && Array.isArray(payload.players)) {
                        renderPlayers(payload.players);
                    }

                } catch (e) {
                    console.error('Message parse error:', e);
                }
            };

            socket.onclose = (event) => {
                updateWsStatus('offline', tr('wsDisconnected', 'Disconnected'));

                // Reconnect logic
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    const delay = Math.min(1000 * reconnectAttempts, 5000);
                    reconnectTimer = setTimeout(connectWebSocket, delay);
                }
            };

            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                updateWsStatus('offline', tr('wsError', 'Error'));
            };

        } catch (e) {
            console.error('WebSocket connection error:', e);
            updateWsStatus('offline', tr('wsConnectionError', 'Connection error'));
        }
    }

    // Start connection
    connectWebSocket();

    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        if (socket) {
            socket.close();
        }
    });

});
