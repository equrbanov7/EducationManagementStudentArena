import { BOOTSTRAP } from './config.js';
import { applyStateSnapshot } from './flow.js';
import { renderIdle } from './render.js';
import { getPlaySocket } from './sockets.js';
import { state } from './state.js';
import { setConnection } from './ui.js';
import { updateServerTimeOffset } from './utils.js';

export async function fetchInitialState() {
    const playWS = getPlaySocket();
    try {
        const response = await fetch(BOOTSTRAP.stateUrl || `/live/state/${BOOTSTRAP.pin}/`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            if (!playWS || playWS.readyState !== WebSocket.OPEN) {
                setConnection("offline");
            }
            if (!state.currentQuestion && state.phase !== "final") {
                renderIdle();
            }
            return;
        }
        const receivedAtMs = Date.now();
        const snapshot = await response.json();
        updateServerTimeOffset(snapshot, receivedAtMs);
        if (!playWS || playWS.readyState !== WebSocket.OPEN) {
            setConnection("online");
        }
        applyStateSnapshot(snapshot);
    } catch (error) {
        console.error("live player state fetch failed", error);
        if (!playWS || playWS.readyState !== WebSocket.OPEN) {
            setConnection("offline");
        }
        if (!state.currentQuestion && state.phase !== "final") {
            renderIdle();
        }
    }
}
