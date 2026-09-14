import { useEffect, useState } from "react";
import { usePlayer } from "@empirica/core/player/classic/react";

// How long to wait for the server-side scorer before showing an error.
const SCORE_TIMEOUT_MS = 100000; // a bit longer than the server-side scorer limit

// Free-text offer scoring, kept as a chat-like vector on the player:
//   player.calculateHistory = [ {kind:"request"}, {kind:"response"}, … ]
// The client appends a request; the server (callbacks.js) sees that the last
// item is a request, runs the scorer, and appends the response. The UI shows
// the most recent response for this scenario.
//
//   role          scorer role name for the request (main game: the player's
//                 roleName; tutorial: "Candidate")
//   scenario      null for the game's scenario, or an issue-space id such as
//                 "tutorial" for the practice round
//   previousText  the proposer's previous complete offer, for "same offer
//                 but…" revisions
export function useOfferScoring({ role, scenario = null, previousText = "" }) {
  const player = usePlayer();
  const inScope = (e) => (e.scenario || null) === scenario;
  const readHistory = () => player.get("calculateHistory") || [];
  const latestRequestText = (h) => [...h].reverse().find((e) => e.kind === "request" && inScope(e))?.text || "";

  // Seed the textarea with the last calculated text so a page refresh shows the
  // latest response again instead of an "empty vs. scored text" mismatch.
  const [offerText, setOfferText] = useState(() => latestRequestText(readHistory()));
  const [seeded, setSeeded] = useState(() => offerText !== "");
  const [timedOutRequestId, setTimedOutRequestId] = useState(null);

  const history = readHistory();
  const lastEntry = history[history.length - 1] || null;

  // If the history arrived after mount, seed once it does (never overwrite typing).
  useEffect(() => {
    if (seeded || offerText !== "") return;
    const t = latestRequestText(history);
    if (t) { setOfferText(t); setSeeded(true); }
  }, [seeded, offerText, history.length]);

  const awaitingServer =
    lastEntry?.kind === "request" && inScope(lastEntry) && lastEntry.id !== timedOutRequestId;
  const latestResponse = [...history].reverse().find((e) => e.kind === "response" && inScope(e)) || null;

  // Shape consumed by negotiationDisplay: { requestId, text, score, error }.
  const scoreResult =
    lastEntry?.kind === "request" && inScope(lastEntry) && lastEntry.id === timedOutRequestId
      ? { requestId: lastEntry.id, text: lastEntry.text, score: null, error: "The scorer took too long to respond. Please try again." }
      : latestResponse;

  // If the server never answers the outstanding request, stop spinning and let
  // the player try again.
  useEffect(() => {
    if (!awaitingServer) return;
    const id = lastEntry.id;
    const t = setTimeout(() => setTimedOutRequestId(id), SCORE_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [awaitingServer, lastEntry?.id]);

  const calculate = () => {
    const text = offerText.trim();
    if (!text || awaitingServer) return;
    const request = {
      kind: "request",
      id: `${Date.now()}-${player.id}`,
      text,
      role,
      scenario,
      previousText: previousText || "",
      timestamp: Date.now(),
    };
    setTimedOutRequestId(null);
    player.set("calculateHistory", [...history, request]);
  };

  return { offerText, setOfferText, calculating: awaitingServer, scoreResult, calculate };
}
