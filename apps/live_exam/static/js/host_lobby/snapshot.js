import { UI } from './dom.js';
import { state } from './state.js';
import { applySessionSettings } from './settings.js';
import { renderLobbyPlayers, updateAnsweredCounter } from './lobby.js';
import { applyQuestionState } from './question.js';
import { applyRevealState } from './reveal.js';
import { renderPodium } from './podium.js';
import { clearAutoTimers, clearPhaseLoop, setSessionState } from './presentation.js';
import { clearPendingStateSync, stopStatePolling } from './api.js';
import {
    markStateMutation,
    notifyHostShell,
    rememberTimelinePayload,
    shouldApplyTimelinePayload,
    updateServerTimeOffset,
} from './utils.js';

export function applyStateSnapshot(snapshot) {
    if (!snapshot || !snapshot.ok) return;
    updateServerTimeOffset(snapshot);
    if (!shouldApplyTimelinePayload(snapshot)) return;
    rememberTimelinePayload(snapshot);
    markStateMutation();

    if (snapshot.settings) {
        applySessionSettings(snapshot.settings);
    }
    if (snapshot.is_locked != null) {
        state.isLocked = Boolean(snapshot.is_locked);
    }
    if (Array.isArray(snapshot.players)) {
        renderLobbyPlayers(snapshot.players, snapshot.total_players);
    }

    if (snapshot.total_players != null) {
        state.totalPlayers = Number(snapshot.total_players || 0);
        if (UI.playersCount) {
            UI.playersCount.textContent = state.totalPlayers;
        }
    }
    if (snapshot.answered_count != null) {
        state.answeredCount = Number(snapshot.answered_count || 0);
        updateAnsweredCounter();
    }

    if (snapshot.state === "question" && snapshot.question) {
        applyQuestionState(snapshot.question, snapshot.answered_count, snapshot.total_players);
        return;
    }

    if (snapshot.state === "reveal" && snapshot.question) {
        applyRevealState(
            {
                question_id: snapshot.question.id,
                correct_option_ids: snapshot.correct_option_ids || [],
                distribution: snapshot.distribution || { total_answers: 0, counts: [] },
                results: snapshot.results || [],
                top: snapshot.top || [],
                previous_top: snapshot.previous_top || [],
                revealed_at: snapshot.revealed_at,
                leaderboard_starts_at: snapshot.leaderboard_starts_at,
                next_question_at: snapshot.next_question_at,
            },
            snapshot.question
        );
        return;
    }

    if (snapshot.state === "finished") {
        if (state.sessionState === "finished") return;
        clearPhaseLoop();
        clearAutoTimers();
        stopStatePolling();
        clearPendingStateSync();
        setSessionState("finished");
        renderPodium(snapshot.top || []);
        notifyHostShell();
        return;
    }

    setSessionState("lobby");
    notifyHostShell();
}
