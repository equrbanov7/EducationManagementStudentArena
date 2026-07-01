import { STATE_POLL_INTERVAL_MS } from './config.js';
import { state } from './state.js';
import { getPlaySocket } from './sockets.js';

export function stopStatePolling() {
    if (state.pollTimer) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

export function startStatePolling(fetchState) {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(() => {
        const playWS = getPlaySocket();
        if (!document.hidden && (!playWS || playWS.readyState !== WebSocket.OPEN)) {
            fetchState();
        }
    }, STATE_POLL_INTERVAL_MS);
}
