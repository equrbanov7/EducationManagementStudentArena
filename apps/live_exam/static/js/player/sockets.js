import { BOOTSTRAP } from './config.js';
import { wsUrl } from './utils.js';

let playWS = null;

export function getPlaySocket() {
    return playWS;
}

export function openPlayerSocket({ onOpen, onClose, onError, onMessage }) {
    playWS = new WebSocket(wsUrl(`/ws/live/${BOOTSTRAP.pin}/play/`));
    playWS.onopen = onOpen;
    playWS.onclose = onClose;
    playWS.onerror = onError;
    playWS.onmessage = onMessage;
    return playWS;
}

export function closePlayerSocket() {
    if (playWS && playWS.readyState === WebSocket.OPEN) {
        playWS.close();
    }
}
