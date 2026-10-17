import React, { useRef, useState } from "react";
import { useGame } from "@empirica/core/player/classic/react";
import { RoleNotesCard } from "../components/RoleNotesCard";
import {
  ScoringCalculator,
  ProposalDetails,
  proposalValue,
  batnaThreshold,
  canSubmit,
  submitErrorMessage,
  formatValue,
} from "../components/negotiationDisplay";
import { useOfferScoring } from "../components/useOfferScoring";
import {
  tableComplete,
  tableValue,
  buildTableOptions,
  TableScoringCalculator,
  TableProposalDetails,
} from "../components/tableScoring";
import { tutorialScenario, tutorialRole } from "./demoContent";

/**
 * DemoUI - the negotiation panel for the tutorial. Same two-column layout as
 * MaterialsPanel (Role / Notes card on the left; calculator, pending proposal
 * and history on the right) but it renders what displayData tells it to; the
 * tutorial state machine lives in Demo.jsx / DemoTable.jsx.
 *
 * With `tableScoresheet` it runs in table mode (DemoTable.jsx): offers are
 * built by picking options from the payoff table, and proposals carry
 * `options` ({ issue: optionIndex }) instead of text + score.
 */
export function DemoUI({
  roleName,
  roleNarrative,
  roleBATNA,
  roleRP,
  displayData,
  viewerFor,
  onProposalSubmit,
  onCopyOffer,
  onVote,
  onFinalizeVote,
  tableScoresheet = null,
}) {
  const game = useGame();
  const proposalsColumnRef = useRef(null);
  const [blocked, setBlocked] = useState(null); // { title, body, button }
  const [submitErrorMsg, setSubmitErrorMsg] = useState("");
  const threshold = batnaThreshold(roleRP);
  const playerCount = displayData.playerCount || 2;

  const lastOwnOffer = [...(displayData.proposals || [])].reverse().find((p) => p.submittedBy === "user");
  const { offerText, setOfferText, calculating, scoreResult, calculate } = useOfferScoring({
    role: tutorialRole,
    scenario: tutorialScenario,
    previousText: lastOwnOffer?.text || "",
  });

  const tableMode = !!tableScoresheet;
  const [selection, setSelection] = useState({}); // table mode: { issue: optionIndex }
  const valueOf = (p) => (tableMode ? tableValue(tableScoresheet, p?.options) : proposalValue(p, viewerFor(p)));
  const submittable = tableMode ? tableComplete(tableScoresheet, selection) : canSubmit(scoreResult, offerText);
  const renderDetails = (p, small = false) =>
    tableMode
      ? <TableProposalDetails roleScoresheet={tableScoresheet} proposal={p} small={small} />
      : <ProposalDetails proposal={p} viewer={viewerFor(p)} small={small} />;

  const handleSubmitProposal = () => {
    if (displayData.submitBlockedMessage) {
      setBlocked({ title: "Not Yet", body: displayData.submitBlockedMessage, button: "OK" });
      return;
    }
    if (!displayData.canSubmitProposal) return;
    if (!submittable) {
      setSubmitErrorMsg(tableMode
        ? "You must choose an option for every issue."
        : submitErrorMessage(scoreResult, offerText));
      return;
    }
    const problem = tableMode
      ? onProposalSubmit({ options: buildTableOptions(tableScoresheet, selection) })
      : onProposalSubmit({ text: scoreResult.text, score: scoreResult.score });
    if (problem) {
      setBlocked(problem);
      return;
    }
    if (tableMode) setSelection({});
    else setOfferText("");
  };

  const handleModifyProposal = (proposal) => {
    if (tableMode) setSelection({ ...(proposal.options || {}) });
    else setOfferText(proposal.text || "");
    if (onCopyOffer) onCopyOffer();
    // The calculator sits at the top of the proposals column.
    proposalsColumnRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  const pendingProposal = displayData.currentProposal;
  const submitDisabled = !displayData.submitBlockedMessage &&
    (!displayData.canSubmitProposal || pendingProposal || !submittable);

  return (
    <div className="w-full h-full bg-gray-300 p-6 flex flex-col relative overflow-hidden">
        {/* Bottom fade overlay */}
        <div className="fixed left-0 bottom-0 w-[82%] h-12 bg-gradient-to-t from-gray-300 to-transparent pointer-events-none z-10"></div>

        {/* Two columns, as in the real negotiation: role/notes on the left, proposals on the right */}
        <div className="flex-1 min-h-0 flex gap-4">
          <div className="w-1/2 min-w-0 h-full pb-12 flex flex-col">
            <RoleNotesCard roleNarrative={roleNarrative} notesAttribute="tutorialNotes" />
          </div>

          {/* Proposals column (scrolls independently) */}
          <div ref={proposalsColumnRef} className="w-1/2 min-w-0 h-full overflow-y-auto pb-12">
            <div className="space-y-4">
            {/* BATNA Card */}
            <div className="bg-white rounded-lg shadow-sm p-4">
              <h4 className="text-base font-bold text-gray-900 mb-2">What if I don't reach agreement?</h4>
              {roleBATNA && <p className="text-sm text-gray-700 mb-1">{roleBATNA}</p>}
              <p className="text-sm text-gray-700">
                If you don't reach agreement, you will earn <span className="font-bold">{threshold} value</span>.
              </p>
            </div>

            {/* Payoff table (table mode) or free text → scorer */}
            {(() => {
              const submitButton = (
                <button
                  onClick={handleSubmitProposal}
                  disabled={submitDisabled}
                  className={`px-4 py-2 rounded font-semibold transition-colors text-sm whitespace-nowrap ${
                    submitDisabled
                      ? "bg-gray-400 text-gray-200 cursor-not-allowed"
                      : "bg-green-600 text-white hover:bg-green-700"
                  }`}
                >
                  {pendingProposal ? "Proposal Pending" : "Submit Proposal"}
                </button>);
              return tableMode ? (
                <TableScoringCalculator
                  roleScoresheet={tableScoresheet}
                  selection={selection}
                  onSelectionChange={setSelection}
                  roleRP={roleRP}
                  footer={submitButton}
                />
              ) : (
                <ScoringCalculator
                  text={offerText}
                  onTextChange={setOfferText}
                  onCalculate={calculate}
                  calculating={calculating}
                  result={scoreResult}
                  roleRP={roleRP}
                  roleName={roleName}
                  placeholder={game?.get("treatment")?.tutorialPlaceholderText}
                  footer={submitButton}
                />
              );
            })()}

            {/* Pending Proposal */}
            {pendingProposal ? (
              <div className="bg-white rounded-lg shadow-md p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-gray-900">Current Proposal</h3>
                  <span className="text-sm text-gray-500">Submitted by: {pendingProposal.submittedByName}</span>
                </div>
                {(() => {
                  const value = valueOf(pendingProposal);
                  const voted = pendingProposal.initialVotes?.user;
                  return (
                    <div className="mb-6">
                      <div className="text-center mb-4">
                        <p className="text-sm text-gray-600 mb-1">Value to you:</p>
                        <p className={`text-4xl font-bold ${value === null ? "text-gray-300" : "text-blue-600"}`}>
                          {formatValue(value)}
                        </p>
                        {value !== null && (
                          <p className={`text-sm font-semibold mt-1 ${value >= threshold ? "text-green-600" : "text-red-600"}`}>
                            {value >= threshold ? "✓ Beats your best alternative" : "✗ Below your best alternative"}
                          </p>
                        )}
                      </div>
                      <div className="bg-blue-50 rounded p-4 mb-4">
                        <h4 className="text-sm font-bold text-gray-700 mb-2">Proposal Details:</h4>
                        {renderDetails(pendingProposal)}
                      </div>
                      {voted ? (
                        <div className="text-center p-4 bg-gray-100 rounded">
                          <p className="text-sm text-gray-600">
                            You voted: <span className="font-bold">{voted === "accept" ? "✓ Accept" : "✗ Reject"}</span>
                          </p>
                        </div>
                      ) : (
                        <div className="flex gap-3">
                          <button
                            onClick={() => onVote(pendingProposal.id, "accept")}
                            className="flex-1 px-4 py-3 bg-green-600 text-white rounded hover:bg-green-700 transition-colors font-semibold"
                          >
                            ✓ Accept
                          </button>
                          <button
                            onClick={() => onVote(pendingProposal.id, "reject")}
                            className="flex-1 px-4 py-3 bg-red-600 text-white rounded hover:bg-red-700 transition-colors font-semibold"
                          >
                            ✗ Reject
                          </button>
                        </div>
                      )}
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

            {/* Proposal History */}
            {displayData.proposals.length > 0 && (
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-xl font-bold text-gray-900 mb-4">Proposal History</h3>
                <div className="space-y-3">
                  {[...displayData.proposals].reverse().map((proposal) => {
                    const value = valueOf(proposal);
                    const yesVotes = Object.values(proposal.initialVotes || {}).filter((v) => v === "accept").length;
                    const pct = (yesVotes / playerCount) * 100;
                    let voteColor;
                    if (pct === 0) voteColor = "text-red-400 opacity-95";
                    else if (pct < 50) voteColor = "text-orange-500 opacity-95";
                    else if (pct === 50) voteColor = "text-yellow-600";
                    else if (pct < 100) voteColor = "text-lime-600";
                    else voteColor = "text-green-600";

                    return (
                      <div key={proposal.id} className="bg-gray-50 rounded p-4 border border-gray-200">
                        <div className="flex items-start justify-between gap-4 mb-3">
                          <div className="flex-1">
                            <h5 className="text-xs font-bold text-gray-600 uppercase mb-2">
                              Proposal from {proposal.submittedByName}:
                            </h5>
                            {renderDetails(proposal, true)}
                          </div>
                          <div className="text-center bg-white rounded p-3 border border-gray-300 min-w-[120px]">
                            <p className={`text-3xl font-bold ${voteColor} mb-1`}>{yesVotes}/{playerCount}</p>
                            <p className="text-xs text-gray-500 uppercase font-semibold mb-2">Accepted</p>
                            <p className="text-lg font-bold text-gray-700">{formatValue(value)} value</p>
                          </div>
                        </div>
                        <button
                          className={`px-4 py-2 rounded transition-colors text-sm font-medium ${
                            displayData.modifyEnabled
                              ? "bg-blue-600 text-white hover:bg-blue-700"
                              : "bg-gray-300 text-gray-500 cursor-not-allowed"
                          }`}
                          disabled={!displayData.modifyEnabled}
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

        {/* Finalize Modal (same confirmation as the real negotiation) */}
        {displayData.showFinalize && displayData.acceptedProposal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-2xl p-8 max-w-md w-full mx-4">
              <div className="text-center mb-6">
                <h3 className="text-3xl font-bold text-green-700 mb-3">🎉 Congratulations!</h3>
                <p className="text-lg text-gray-700 mb-2">Everyone has accepted this proposal.</p>
                <p className="text-md text-gray-600">Would you like to finalize this deal, or keep discussing?</p>
              </div>
              <div className="text-center mb-6 p-4 bg-green-50 rounded">
                <p className="text-sm text-gray-600 mb-1">Your value with this proposal:</p>
                <p className="text-4xl font-bold text-green-600">
                  {formatValue(valueOf(displayData.acceptedProposal))}
                </p>
              </div>
              <div className="flex flex-col gap-3">
                <button
                  onClick={() => onFinalizeVote("finalize")}
                  className="w-full px-6 py-4 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-bold text-lg"
                >
                  Finalize Deal
                </button>
                <button
                  onClick={() => onFinalizeVote("continue")}
                  className="w-full px-6 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-bold text-lg"
                >
                  Keep Discussing
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Blocked / guidance modal */}
        {blocked && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-2xl p-8 max-w-lg w-full mx-4">
              <div className="text-6xl mb-4 text-center">⚠️</div>
              <h2 className="text-2xl font-bold mb-4 text-center">{blocked.title}</h2>
              <div className="text-lg text-gray-700 mb-6 text-center">{blocked.body}</div>
              <button
                onClick={() => setBlocked(null)}
                className="w-full bg-blue-600 text-white py-4 px-6 rounded-lg hover:bg-blue-700 font-bold text-xl"
              >
                {blocked.button || "OK"}
              </button>
            </div>
          </div>
        )}

        {/* Cannot submit modal */}
        {submitErrorMsg && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-2xl p-8 max-w-sm w-full mx-4">
              <div className="text-center mb-6">
                <div className="text-6xl mb-4">⚠️</div>
                <h3 className="text-2xl font-bold text-red-600 mb-3">Cannot Submit Proposal</h3>
                <p className="text-lg text-gray-700">{submitErrorMsg}</p>
              </div>
              <button
                onClick={() => setSubmitErrorMsg("")}
                className="w-full px-6 py-3 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold"
              >
                OK
              </button>
            </div>
          </div>
        )}
    </div>
  );
}
