import { SESSION_SETTINGS } from './config.js';
import { fetchInitialState } from './api.js';
import { handleOptionClick } from './answer.js';
import { bindPlayerEvents } from './events.js';
import { handleSocketMessage } from './flow.js';
import { startStatePolling } from './polling.js';
import { renderIdle, setOptionClickHandler } from './render.js';
import { applySessionSettings } from './settings.js';
import { openPlayerSocket } from './sockets.js';
import { renderPlayerIdentity, setConnection } from './ui.js';

setOptionClickHandler(handleOptionClick);
bindPlayerEvents();

renderPlayerIdentity();
applySessionSettings(SESSION_SETTINGS);
renderIdle();
setConnection("connecting");

let initialFetchDone = false;

openPlayerSocket({
    onOpen: () => {
        setConnection("online");
        if (!initialFetchDone) {
            initialFetchDone = true;
            fetchInitialState();
        }
    },
    onClose: () => {
        setConnection("offline");
    },
    onError: () => {
        setConnection("offline");
    },
    onMessage: (event) => {
        try {
            handleSocketMessage(JSON.parse(event.data));
        } catch (error) {
            console.error("live player message parse failed", error);
        }
    },
});

startStatePolling(fetchInitialState);
if (!initialFetchDone) {
    initialFetchDone = true;
    fetchInitialState();
}
