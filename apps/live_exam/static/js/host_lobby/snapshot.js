import { state } from './state.js?v=lx20261008';
import { applySessionSettings } from './settings.js?v=lx20261008';
import { renderLobbyPlayers } from './lobby.js?v=lx20261008';
import { applyQuestionState, updateAnsweredCounter, updateReceivedCounter } from './question.js?v=lx20261008';
import { applyRevealState } from './reveal.js?v=lx20261008';
import { renderPodium } from './podium.js?v=lx20261008';
import { clearAutoTimers, clearPhaseLoop, setSessionState } from './presentation.js?v=lx20261008';
import { clearPendingStateSync, stopStatePolling } from './api.js?v=lx20261008';
import {
    markStateMutation,
    notifyHostShell,
    rememberTimelinePayload,
    shouldApplyTimelinePayload,
    toMs,
    updateServerTimeOffset,
} from './utils.js?v=lx20261008';

export function applyStateSnapshot(snapshot) {
    if (!snapshot || !snapshot.ok) return;
    updateServerTimeOffset(snapshot);
    if (!shouldApplyTimelinePayload(snapshot)) return;
    rememberTimelinePayload(snapshot);
    markStateMutation();

    if (snapshot.settings) applySessionSettings(snapshot.settings);
    if (snapshot.is_locked != null) state.isLocked = Boolean(snapshot.is_locked);
    if (snapshot.total_players != null) state.totalPlayers = Number(snapshot.total_players || 0);
    if (Array.isArray(snapshot.players)) {
        // HTTP snapshot həqiqətdir; ondan köhnə WS `lobby_state` artıq tətbiq olunmur.
        state.lobbyStateAt = Math.max(Number(state.lobbyStateAt || 0), toMs(snapshot.server_time));
        // 2026-10-08: oyun gedərkən də (aparıcının «İştirakçılar» siyahısı) — say `roster_count`-dır.
        renderLobbyPlayers(snapshot.players, snapshot.roster_count ?? snapshot.total_players);
    }
    if (snapshot.answered_count != null) {
        state.answeredCount = Number(snapshot.answered_count || 0);
        updateAnsweredCounter();
    }

    if (snapshot.state === "question" && snapshot.question) {
        applyQuestionState(snapshot.question, snapshot.answered_count, snapshot.total_players);
        if (snapshot.received_count != null) {
            state.receivedQuestionId = Number(snapshot.question.id);
            state.receivedCount = Math.max(Number(state.receivedCount || 0), Number(snapshot.received_count || 0));
            updateReceivedCounter();
        }
        return;
    }

    if (snapshot.state === "reveal" && snapshot.question) {
        // Snapshot bütün reveal sahələrini (typed_summary, fastest_correct, …) ötürür.
        applyRevealState(
            Object.assign({}, snapshot, {
                type: "reveal",
                question_id: snapshot.question.id,
                correct_option_ids: snapshot.correct_option_ids || [],
                distribution: snapshot.distribution || { total_answers: 0, counts: [] },
                results: snapshot.results || [],
                top: snapshot.top || [],
                previous_top: snapshot.previous_top || [],
            }),
            snapshot.question
        );
        return;
    }

    if (snapshot.state === "finished") {
        clearPhaseLoop();
        clearAutoTimers();
        stopStatePolling();
        clearPendingStateSync();
        setSessionState("finished");
        renderPodium(snapshot.top || [], snapshot);
        notifyHostShell();
        return;
    }

    setSessionState("lobby");
    notifyHostShell();
}
