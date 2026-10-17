import React, { useState, useEffect, useContext, useRef } from "react";
import { RoleNotesCard } from "./RoleNotesCard";
import { usePlayer, useStage, useRound, useGame } from "@empirica/core/player/classic/react";
import { DailyCallContext } from "../App";
import { useOfferScoring } from "./useOfferScoring";
import {
  ScoringCalculator,
  ProposalDetails,
  proposalValue,
  batnaThreshold,
  canSubmit,
  submitErrorMessage,
  formatValue,
} from "./negotiationDisplay";
import {
  isTableMode,
  tableComplete,
  tableValue,
  buildTableOptions,
  TableScoringCalculator,
  TableProposalDetails,
} from "./tableScoring";

// Quit ("declare an impasse"), ported from workshop-app: after two
// confirmations the initiator starts a shared countdown (game.quitRequest) that
// every player sees and only the initiator can cancel. When it runs out,
// game.forceQuit is set and Stage.jsx submits the stage for everyone — the
// round ends with no agreement.
const QUIT_COUNTDOWN_SECONDS = 15;
// Extra time non-initiators wait past zero before force-ending the game themselves,
// covering clock skew between clients and an initiator who disconnected mid-countdown.
const QUIT_GRACE_SECONDS = 5;

export function MaterialsPanel({
  roleName,
  roleNarrative,
  roleBATNA,
  roleRP,
}) {
  const player = usePlayer();
  const stage = useStage();
  const round = useRound();
  const game = useGame();
  const { playerCount, experimentalTreatmentText, mainPlaceholderText } = game.get("treatment");

  const threshold = batnaThreshold(roleRP);

  // Scoring mode: "table" = pick one option per issue from the role's payoff
  // table (tableScoring.jsx); otherwise free text scored by the python scorer.
  const tableMode = isTableMode(game.get("treatment"));
  const roleScoresheet = player.get("roleScoresheet");
  const [selection, setSelection] = useState({}); // table mode: { issue: optionIndex }

  // Free-text proposal + scorer round trip (see useOfferScoring).
  const history = round.get("proposalHistory") || [];
  const currentProposal = history.length > 0 ? history[history.length - 1] : null;
  const { offerText, setOfferText, calculating, scoreResult, calculate: handleCalculate } = useOfferScoring({
    role: roleName,
    previousText: currentProposal?.text || "",
  });
  const [showFinalizeModal, setShowFinalizeModal] = useState(false);
  // null, or which action was blocked for being worth negative value: "accept" | "submit"
  const [negativeValueAction, setNegativeValueAction] = useState(null);
  const [showBlankProposalModal, setShowBlankProposalModal] = useState(false);
  const [showQuitModal, setShowQuitModal] = useState(false);
  const [showQuitConfirmModal, setShowQuitConfirmModal] = useState(false);
  const [quitSecondsLeft, setQuitSecondsLeft] = useState(QUIT_COUNTDOWN_SECONDS);
  const [submitErrorMsg, setSubmitErrorMsg] = useState("");

  const { setMediaLocked } = useContext(DailyCallContext);

  // Check if welcome modal has been shown before (stored in player state)
  const hasSeenWelcomeModal = player.get("hasSeenWelcomeModal") || false;
  const [showWelcomeModal, setShowWelcomeModal] = useState(!hasSeenWelcomeModal);

  // "Let's Go!" is disabled for the first few seconds to force reading.
  const WELCOME_LOCK_SECONDS = 3;
  const [welcomeSecondsLeft, setWelcomeSecondsLeft] = useState(WELCOME_LOCK_SECONDS);

  const proposalsColumnRef = useRef(null);
  const [wiggleStoppedId, setWiggleStoppedId] = useState(null); // proposal id whose wiggle the user interrupted

  // Compute proposal state from vote counts (derived state, no useEffect needed)
  let proposalState = "none"; // "none" | "collecting-initial" | "collecting-final" | "complete"

  if (currentProposal) {
    const initialVoteCount = Object.keys(currentProposal.initialVotes).length;

    if (initialVoteCount < playerCount) {
      proposalState = "collecting-initial";
    } else {
      const rejectCount = Object.values(currentProposal.initialVotes).filter(v => v === "reject").length;

      if (rejectCount >= 1) {
        proposalState = "complete"; // Failed at initial stage
      } else {
        // All accepted, check final votes
        const finalVoteCount = Object.keys(currentProposal.finalVotes).length;

        if (finalVoteCount < playerCount) {
          proposalState = "collecting-final";
        } else {
          proposalState = "complete"; // Either finalized or failed at ratification
        }
      }
    }
  }

  // Determine what to show
  const pendingProposal = proposalState === "collecting-initial" ? currentProposal : null;
  // The proposer auto-votes "accept" on submit, so their own proposal needs no attention cues.
  const isOwnPending = pendingProposal?.submittedBy === player.id;

  // Determine if we should show the finalize modal (persist even after voting completes)
  let acceptedPendingProposal = null;
  if (currentProposal) {
    const allInitialAccept = Object.keys(currentProposal.initialVotes).length === playerCount &&
                            Object.values(currentProposal.initialVotes).every(v => v === "accept");

    if (allInitialAccept) {
      const finalVoteCount = Object.keys(currentProposal.finalVotes).length;
      const allFinalize = finalVoteCount === playerCount &&
                         Object.values(currentProposal.finalVotes).every(v => v === "finalize");
      const hasPlayerDismissed = currentProposal.modalDismissed?.[player.id];

      // Show modal if:
      // - Still collecting final votes, OR
      // - Voting complete but not unanimous finalize AND player hasn't dismissed
      if (finalVoteCount < playerCount || (!allFinalize && !hasPlayerDismissed)) {
        acceptedPendingProposal = currentProposal;
      }
    }
  }

  const allHistoryProposals = proposalState === "none" || proposalState === "complete" ? history : history.slice(0, -1);

  // Quit countdown: driven by shared game state so every participant sees it.
  // Each client counts down locally from quitRequest.startedAt — no per-second server writes.
  const quitRequest = game.get("quitRequest");
  useEffect(() => {
    if (!quitRequest) {
      setQuitSecondsLeft(QUIT_COUNTDOWN_SECONDS);
      return;
    }

    const tick = () => {
      const elapsed = (Date.now() - quitRequest.startedAt) / 1000;
      const remaining = Math.max(0, QUIT_COUNTDOWN_SECONDS - Math.floor(elapsed));
      setQuitSecondsLeft(remaining);

      if (game.get("forceQuit")) return;

      const isInitiator = quitRequest.by === player.id;
      const deadline = isInitiator
        ? QUIT_COUNTDOWN_SECONDS
        : QUIT_COUNTDOWN_SECONDS + QUIT_GRACE_SECONDS;

      if (elapsed >= deadline) {
        game.set("forceQuitBy", quitRequest.by);
        game.set("forceQuit", true);
      }
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [quitRequest?.startedAt, quitRequest?.by, player.id]);

  // Auto-show finalize modal when acceptedPendingProposal exists and player hasn't voted
  useEffect(() => {
    if (acceptedPendingProposal && !acceptedPendingProposal.finalVotes[player.id] && !showFinalizeModal) {
      setShowFinalizeModal(true);
    }
  }, [acceptedPendingProposal?.id, player.id, showFinalizeModal]);

  // Check if everyone voted to finalize and submit for this player
  useEffect(() => {
    if (currentProposal) {
      const finalVoteCount = Object.keys(currentProposal.finalVotes).length;
      if (finalVoteCount === playerCount) {
        const allFinalize = Object.values(currentProposal.finalVotes).every(v => v === "finalize");
        if (allFinalize) {
          player.stage.set("submit", true);
        }
      }
    }
  }, [currentProposal?.finalVotes, playerCount, player]);

  // Count down the "Let's Go!" lock while the welcome modal is open.
  useEffect(() => {
    if (!showWelcomeModal || welcomeSecondsLeft <= 0) return;
    const t = setTimeout(() => setWelcomeSecondsLeft(s => s - 1), 1000);
    return () => clearTimeout(t);
  }, [showWelcomeModal, welcomeSecondsLeft]);

  // While the welcome modal is open, authoritatively force mic + camera off (the
  // track effect in App.jsx honors this regardless of the per-toggle state, so it
  // wins the mount-time race with VideoChat). Releasing the lock on "Let's Go!" /
  // unmount reveals whatever state VideoChat maintains = the player's arrival state.
  useEffect(() => {
    setMediaLocked(showWelcomeModal);
    return () => setMediaLocked(false);
  }, [showWelcomeModal, setMediaLocked]);

  // Viewer descriptor for value lookups on stored proposals.
  const viewerFor = (proposal) => ({ roleName, isProposer: proposal?.submittedBy === player.id });

  // Value of a stored proposal to this player (null when it has none).
  const valueOf = (proposal) => {
    if (!proposal) return null;
    return tableMode
      ? tableValue(roleScoresheet, proposal.options)
      : proposalValue(proposal, viewerFor(proposal));
  };

  const submittable = tableMode
    ? tableComplete(roleScoresheet, selection)
    : canSubmit(scoreResult, offerText);

  const renderProposalDetails = (proposal, small = false) =>
    tableMode ? (
      <TableProposalDetails roleScoresheet={roleScoresheet} proposal={proposal} small={small} />
    ) : (
      <ProposalDetails proposal={proposal} viewer={viewerFor(proposal)} small={small} />
    );

  // Handle proposal submission
  const handleSubmitProposal = () => {
    if (!submittable) {
      setSubmitErrorMsg(tableMode
        ? "You must choose an option for every issue."
        : submitErrorMessage(scoreResult, offerText));
      setShowBlankProposalModal(true);
      return;
    }

    // Same rule as voting: you can't put forward a deal worth negative value to you.
    const ownValue = tableMode
      ? tableValue(roleScoresheet, selection)
      : proposalValue(scoreResult, { roleName, isProposer: true });
    if (ownValue !== null && ownValue < 0) {
      setNegativeValueAction("submit");
      return;
    }

    const newProposal = {
      id: `${Date.now()}-${player.id}`,
      submittedBy: player.id,
      submittedByName: player.get("displayName") || player.id,
      submittedByRole: roleName,
      timestamp: Date.now(),
      ...(tableMode
        ? { options: buildTableOptions(roleScoresheet, selection) }
        : { text: scoreResult.text, score: scoreResult.score }),
      // Proposer automatically votes "accept" on their own proposal.
      initialVotes: { [player.id]: "accept" },
      finalVotes: {},
      modalDismissed: {}
    };
    round.set("proposalHistory", [...history, newProposal]);
  };

  // Handle vote on proposal (initial votes)
  const handleVote = (proposalId, vote) => {
    // If voting "accept", check the proposal isn't worth negative value to you.
    if (vote === "accept") {
      const proposal = history.find(p => p.id === proposalId);
      const value = valueOf(proposal);
      if (value !== null && value < 0) {
        setNegativeValueAction("accept");
        return;
      }
    }

    const updatedHistory = [...history];
    const proposal = updatedHistory.find(p => p.id === proposalId);

    if (!proposal) return;

    // Update initial vote
    proposal.initialVotes[player.id] = vote;
    round.set("proposalHistory", updatedHistory);
  };

  // Handle modifying a past proposal (load its terms back into the calculator)
  const handleModifyProposal = (proposal) => {
    if (tableMode) setSelection({ ...(proposal.options || {}) });
    else setOfferText(proposal.text || "");
    // The calculator sits at the top of the proposals column.
    proposalsColumnRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Handle finalize decision (finalize or continue)
  const handleFinalizeVote = (proposalId, decision) => {
    const updatedHistory = [...history];
    const proposal = updatedHistory.find(p => p.id === proposalId);

    if (!proposal) return;

    // Update final vote
    proposal.finalVotes[player.id] = decision;

    round.set("proposalHistory", updatedHistory);
    // useEffect will handle stage submission if everyone votes to finalize
  };

  // Handle dismissing the finalize modal
  const handleDismissModal = (proposalId) => {
    const updatedHistory = [...history];
    const proposal = updatedHistory.find(p => p.id === proposalId);

    if (!proposal) return;

    if (!proposal.modalDismissed) {
      proposal.modalDismissed = {};
    }
    proposal.modalDismissed[player.id] = true;

    round.set("proposalHistory", updatedHistory);
    setShowFinalizeModal(false);
  };

  return (
    <div className="w-full h-full bg-gray-300 p-6 flex flex-col relative overflow-hidden">
      {/* Bottom fade overlay */}
      <div className="fixed left-0 bottom-0 w-[82%] h-12 bg-gradient-to-t from-gray-300 to-transparent pointer-events-none z-10"></div>

      {/* Two columns: narrative on the left, proposals on the right */}
      <div className="flex-1 min-h-0 flex gap-4">
        {/* Narrative column: header + tabs stay put, only the tab content scrolls */}
        <div className="w-1/2 min-w-0 h-full pb-12 flex flex-col">
          <RoleNotesCard
            roleNarrative={roleNarrative}
            introText={experimentalTreatmentText}
            onQuit={() => setShowQuitModal(true)}
          />
        </div>

        {/* Proposals column (scrolls independently) */}
        <div ref={proposalsColumnRef} className="w-1/2 min-w-0 h-full overflow-y-auto pb-12">
          <div className="space-y-4">
            {/* BATNA Card */}
            <div className="bg-white rounded-lg shadow-sm p-4">
              <h4 className="text-base font-bold text-gray-900 mb-2">
                What if I don't reach agreement?
              </h4>
              {roleBATNA && (
                <p className="text-sm text-gray-700 mb-1">{roleBATNA}</p>
              )}
            </div>

            {/* Main Scoring Area: payoff table (table mode) or free text → scorer */}
            {(() => {
              const submitButton = (
                <button
                  onClick={handleSubmitProposal}
                  disabled={pendingProposal !== null || !submittable}
                  className={`inline-block px-4 py-2 rounded font-semibold transition-colors text-sm whitespace-nowrap ${
                    pendingProposal !== null || !submittable
                      ? "bg-gray-400 text-gray-200 cursor-not-allowed"
                      : "bg-green-600 text-white hover:bg-green-700"
                  }`}
                >
                  {pendingProposal !== null ? "Proposal Pending" : "Submit Proposal"}
                </button>
              );
              return tableMode ? (
                <TableScoringCalculator
                  roleScoresheet={roleScoresheet}
                  selection={selection}
                  onSelectionChange={setSelection}
                  roleRP={roleRP}
                  footer={submitButton}
                />
              ) : (
                <ScoringCalculator
                  text={offerText}
                  onTextChange={setOfferText}
                  onCalculate={handleCalculate}
                  calculating={calculating}
                  result={scoreResult}
                  roleRP={roleRP}
                  roleName={roleName}
                  placeholder={mainPlaceholderText}
                  footer={submitButton}
                />
              );
            })()}

            {/* Pending Proposal */}
            {pendingProposal ? (
              <div
                onClick={() => setWiggleStoppedId(pendingProposal.id)}
                className={`bg-white rounded-lg shadow-md p-6 ${
                  isOwnPending || wiggleStoppedId === pendingProposal.id ? "" : "animate-wiggle"
                }`}
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-gray-900">
                    Current Proposal
                  </h3>
                  <span className="text-sm text-gray-500">
                    Submitted by: {pendingProposal.submittedByName}
                  </span>
                </div>

                {(() => {
                  const value = valueOf(pendingProposal);

                  return (
                    <div className="mb-2">
                      {/* Vote buttons or status, above the proposal */}
                      {pendingProposal.initialVotes[player.id] ? (
                        <div className="text-center p-4 bg-gray-100 rounded mb-4">
                          <p className="text-sm text-gray-600">
                            {isOwnPending ? (
                              <span className="font-bold">Your proposal</span>
                            ) : (
                              <>
                                You voted: <span className="font-bold">
                                  {pendingProposal.initialVotes[player.id] === "accept" ? "✓ Accept" : "✗ Reject"}
                                </span>
                              </>
                            )}
                          </p>
                          <p className="text-xs text-gray-500 mt-1">
                            Waiting for other players... ({Object.keys(pendingProposal.initialVotes).length}/{playerCount} voted)
                          </p>
                        </div>
                      ) : (
                        <div className="flex gap-3 mb-4">
                          <button
                            onClick={() => handleVote(pendingProposal.id, "accept")}
                            className="flex-1 px-4 py-3 bg-green-600 text-white rounded hover:bg-green-700 transition-colors font-semibold"
                          >
                            ✓ Accept
                          </button>
                          <button
                            onClick={() => handleVote(pendingProposal.id, "reject")}
                            className="flex-1 px-4 py-3 bg-red-600 text-white rounded hover:bg-red-700 transition-colors font-semibold"
                          >
                            ✗ Reject
                          </button>
                        </div>
                      )}

                      {/* Proposal: details on the left, value to this player on the right */}
                      <div className="bg-blue-50 rounded p-4 flex gap-4 items-start">
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-bold text-gray-700 mb-2">Proposal Details:</h4>
                          {renderProposalDetails(pendingProposal)}
                        </div>
                        <div className="shrink-0 text-center bg-white rounded p-3 border border-gray-300 min-w-[140px]">
                          <p className="text-sm text-gray-600 mb-1">Total value to you</p>
                          <p className={`text-4xl font-bold ${value === null ? "text-gray-300" : "text-blue-600"}`}>
                            {formatValue(value)}
                          </p>
                          {value !== null && (
                            <p className={`text-sm font-semibold mt-1 ${
                              value >= threshold ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {value >= threshold ? '✓ Beats your best alternative' : '✗ Below your best alternative'}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow-md p-6 text-center">
                <p className="text-gray-500">
                  {tableMode
                    ? "No pending proposal. Choose an option for every issue above, then Submit Proposal."
                    : "No pending proposal. Describe an offer above, click Calculate, then Submit Proposal."}
                </p>
              </div>
            )}

            {/* Proposal History (Rejected + Accepted Pending) */}
            {allHistoryProposals.length > 0 && (
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-4">
                  Proposal History
                </h3>
                <div className="space-y-3">
                  {[...allHistoryProposals].reverse().map((proposal) => {
                    // Value for this player
                    const value = valueOf(proposal);

                    // Count yes votes (from initial votes)
                    const yesVotes = Object.values(proposal.initialVotes).filter(v => v === "accept").length;

                    // Calculate acceptance percentage for color coding
                    const acceptancePercentage = (yesVotes / playerCount) * 100;

                    // Determine color based on percentage: red (0%) -> yellow (50%) -> green (100%)
                    let voteColor;
                    if (acceptancePercentage === 0) {
                      voteColor = "text-red-400 opacity-95";
                    } else if (acceptancePercentage < 50) {
                      voteColor = "text-orange-500 opacity-95";
                    } else if (acceptancePercentage === 50) {
                      voteColor = "text-yellow-600";
                    } else if (acceptancePercentage < 100) {
                      voteColor = "text-lime-600";
                    } else {
                      voteColor = "text-green-600";
                    }

                    return (
                      <div key={proposal.id} className="bg-gray-50 rounded p-4 border border-gray-200">
                        <div className="flex items-start justify-between gap-4 mb-3">
                          {/* Proposal items list */}
                          <div className="flex-1">
                            <h5 className="text-xs font-bold text-gray-600 uppercase mb-2">Proposal:</h5>
                            {renderProposalDetails(proposal, true)}
                          </div>

                          {/* Vote count and value - more prominent */}
                          <div className="text-center bg-white rounded p-3 border border-gray-300 min-w-[120px]">
                            <p className={`text-3xl font-bold ${voteColor} mb-1`}>
                              {yesVotes}/{playerCount}
                            </p>
                            <p className="text-xs text-gray-500 uppercase font-semibold mb-2">
                              Accepted
                            </p>
                            <p className="text-lg font-bold text-gray-700">
                              {formatValue(value)} value
                            </p>
                          </div>
                        </div>
                        <button
                          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors text-sm font-medium"
                          onClick={() => handleModifyProposal(proposal)}
                        >
                          Modify
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Finalize Modal - Popup */}
      {showFinalizeModal && acceptedPendingProposal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
            {/* Value for this player */}
            {(() => {
              const value = valueOf(acceptedPendingProposal);

              const finalVoteCount = Object.keys(acceptedPendingProposal.finalVotes).length;
              const hasVoted = !!acceptedPendingProposal.finalVotes?.[player.id];
              const allVoted = finalVoteCount === playerCount;
              const allFinalize = allVoted && Object.values(acceptedPendingProposal.finalVotes).every(v => v === "finalize");

              // If player has voted, show waiting screen
              if (hasVoted) {
                return (
                  <div>
                    <div className="text-center mb-6">
                      <div className="text-6xl mb-4">⏳</div>
                      <h3 className="text-2xl font-bold text-gray-900 mb-3">
                        Waiting for other votes...
                      </h3>
                      <p className="text-lg text-gray-600 mb-4">
                        {allVoted && !allFinalize ? (
                          <span>Outcome: <span className="font-bold text-blue-700">Continue</span></span>
                        ) : (
                          <span>You voted: <span className="font-bold text-green-700">
                            {acceptedPendingProposal.finalVotes[player.id] === "finalize" ? "Finalize" : "Continue"}
                          </span></span>
                        )}
                      </p>
                      <div className="text-center p-4 bg-gray-100 rounded">
                        <p className="text-4xl font-bold text-blue-600 mb-2">
                          {finalVoteCount}/{playerCount}
                        </p>
                        <p className="text-sm text-gray-600">
                          players have voted
                        </p>
                      </div>
                    </div>

                    {/* Show close button if voting is complete but not unanimous */}
                    {allVoted && !allFinalize && (
                      <button
                        onClick={() => handleDismissModal(acceptedPendingProposal.id)}
                        className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
                      >
                        Close
                      </button>
                    )}
                  </div>
                );
              }

              // If player hasn't voted, show decision screen
              return (
                <div>
                  <div className="text-center mb-6">
                    <h3 className="text-3xl font-bold text-green-700 mb-3">
                      🎉 Congratulations!
                    </h3>
                    <p className="text-lg text-gray-700 mb-2">
                      Everyone has accepted this proposal.
                    </p>
                    <p className="text-md text-gray-600">
                      Would you like to finalize this deal, or keep discussing?
                    </p>
                  </div>

                  <div className="text-center mb-6 p-4 bg-green-50 rounded">
                    <p className="text-sm text-gray-600 mb-1">Your value with this proposal:</p>
                    <p className="text-4xl font-bold text-green-600">
                      {formatValue(value)}
                    </p>
                  </div>

                  <div className="flex flex-col gap-3">
                    <button
                      onClick={() => {
                        handleFinalizeVote(acceptedPendingProposal.id, "finalize");
                      }}
                      className="w-full px-6 py-4 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-bold text-lg"
                    >
                      Finalize Deal
                    </button>
                    <button
                      onClick={() => {
                        handleFinalizeVote(acceptedPendingProposal.id, "continue");
                      }}
                      className="w-full px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-bold text-lg"
                    >
                      Keep Discussing
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Negative Value Warning Modal */}
      {negativeValueAction && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-sm w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⚠️</div>
              <h3 className="text-2xl font-bold text-red-600 mb-3">
                {negativeValueAction === "submit" ? "Cannot Submit Proposal" : "Cannot Accept Deal"}
              </h3>
              <p className="text-lg text-gray-700">
                {negativeValueAction === "submit"
                  ? "You can't propose a deal worth negative value."
                  : "You can't accept a deal worth negative value."}
              </p>
            </div>
            <button
              onClick={() => setNegativeValueAction(null)}
              className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
            >
              OK
            </button>
          </div>
        </div>
      )}

      {/* Incomplete Proposal Warning Modal */}
      {showBlankProposalModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-sm w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⚠️</div>
              <h3 className="text-2xl font-bold text-red-600 mb-3">
                Cannot Submit Proposal
              </h3>
              <p className="text-lg text-gray-700">
                {submitErrorMsg}
              </p>
            </div>
            <button
              onClick={() => setShowBlankProposalModal(false)}
              className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
            >
              OK
            </button>
          </div>
        </div>
      )}

      {/* Quit Modal - Step 1 */}
      {showQuitModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⚠️</div>
              <h3 className="text-2xl font-bold text-red-600 mb-3">
                Are you sure you want to declare an impasse?
              </h3>
              <p className="text-lg text-gray-700">
                This will end the negotiation for everybody without an agreement. You should talk this through with the other players before declaring an impasse.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <button
                onClick={() => setShowQuitModal(false)}
                className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
              >
                Return to Negotiation
              </button>
              <button
                onClick={() => {
                  setShowQuitModal(false);
                  setShowQuitConfirmModal(true);
                }}
                className="w-full px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-semibold"
              >
                End Negotiation for Everyone
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Quit Confirm Modal - Step 2 */}
      {showQuitConfirmModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⚠️</div>
              <h3 className="text-2xl font-bold text-red-600 mb-3">
                Are you sure?
              </h3>
              <p className="text-lg text-gray-700">
                Ending the negotiation now will end it for everybody.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <button
                onClick={() => setShowQuitConfirmModal(false)}
                className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
              >
                Return to Negotiation
              </button>
              <button
                onClick={() => {
                  setShowQuitConfirmModal(false);
                  const now = Date.now();
                  const byName = player.get("displayName") || player.id;
                  const quitLog = game.get("quitLog") || [];
                  game.set("quitLog", [...quitLog, { event: "initiated", by: player.id, byName, timestamp: now }]);
                  game.set("quitRequest", { by: player.id, byName, startedAt: now });
                }}
                className="w-full px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-semibold"
              >
                End Negotiation for Everyone
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Quit Countdown Modal - Step 3 (shared: shown to all participants) */}
      {quitRequest && !game.get("forceQuit") && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⏳</div>
              {quitRequest.by === player.id ? (
                <h3 className="text-2xl font-bold text-red-600 mb-3">
                  The negotiation will end in {quitSecondsLeft} second{quitSecondsLeft !== 1 ? 's' : ''}
                </h3>
              ) : (
                <>
                  <h3 className="text-2xl font-bold text-red-600 mb-3">
                    {quitRequest.byName} has declared an impasse
                  </h3>
                  <p className="text-lg text-gray-700">
                    The negotiation will end in {quitSecondsLeft} second{quitSecondsLeft !== 1 ? 's' : ''} unless {quitRequest.byName} cancels.
                  </p>
                </>
              )}
            </div>
            {quitRequest.by === player.id && (
              <button
                onClick={() => {
                  const now = Date.now();
                  const quitLog = game.get("quitLog") || [];
                  game.set("quitLog", [...quitLog, { event: "canceled", by: player.id, byName: quitRequest.byName, timestamp: now }]);
                  game.set("quitRequest", null);
                }}
                className="w-full px-6 py-4 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-bold text-lg"
              >
                Cancel — Continue Negotiation
              </button>
            )}
          </div>
        </div>
      )}

      {/* Welcome Modal */}
      {showWelcomeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-lg w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">🤝</div>
              <h3 className="text-3xl font-bold text-blue-700 mb-4">
                It's Time to Negotiate!
              </h3>
              <div className="text-left text-gray-700 leading-relaxed space-y-3">
                <p className="text-red-600 text-opacity-80 font-semibold">
                  {tableMode
                    ? <>To <strong>submit</strong> a proposal, choose an option for every issue under Proposals, then click "Submit Proposal".</>
                    : <>To <strong>submit</strong> a proposal, describe it in your own words under Proposals, click "Calculate" to see its value, then click "Submit Proposal".</>}
                </p>
                <p>
                  <strong>To end the negotiation without an agreement, click "Quit."</strong>
                </p>
              </div>
            </div>
            <button
              disabled={welcomeSecondsLeft > 0}
              onClick={() => {
                player.set("hasSeenWelcomeModal", true);
                // Releasing the media lock (via the showWelcomeModal effect) restores
                // the audio/video state the player arrived with.
                setShowWelcomeModal(false);
              }}
              className={`w-full px-6 py-3 rounded-lg transition-colors font-semibold text-lg ${
                welcomeSecondsLeft > 0
                  ? "bg-gray-400 text-gray-200 cursor-not-allowed"
                  : "bg-blue-600 text-white hover:bg-blue-700"
              }`}
            >
              {welcomeSecondsLeft > 0 ? `Let's Go! (${welcomeSecondsLeft})` : "Let's Go!"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
