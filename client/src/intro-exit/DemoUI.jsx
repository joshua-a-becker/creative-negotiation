import React, { useState } from "react";
import { RoleNarrative } from "../components/RoleNarrative";
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
import { tutorialScenario, tutorialRole, demoOfferPlaceholder } from "./demoContent";

/**
 * DemoUI - the negotiation panel for the tutorial. Same look as MaterialsPanel
 * (tabs, free-text calculator, pending proposal, history) but it renders what
 * displayData tells it to; the tutorial state machine lives in Demo.jsx.
 */
export function DemoUI({
  roleName,
  roleNarrative,
  roleBATNA,
  roleRP,
  tips,
  displayData,
  viewerFor,
  onProposalSubmit,
  onCopyOffer,
  onVote,
  onFinalizeVote,
}) {
  const [activeTab, setActiveTab] = useState("proposals");
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

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    window.scrollTo(0, 0);
  };

  const handleSubmitProposal = () => {
    if (displayData.submitBlockedMessage) {
      setBlocked({ title: "Not Yet", body: displayData.submitBlockedMessage, button: "OK" });
      return;
    }
    if (!displayData.canSubmitProposal) return;
    if (!canSubmit(scoreResult, offerText)) {
      setSubmitErrorMsg(submitErrorMessage(scoreResult, offerText));
      return;
    }
    const problem = onProposalSubmit({ text: scoreResult.text, score: scoreResult.score });
    if (problem) {
      setBlocked(problem);
      return;
    }
    setOfferText("");
  };

  const handleModifyProposal = (proposal) => {
    setOfferText(proposal.text || "");
    if (onCopyOffer) onCopyOffer();
    handleTabChange("proposals");
  };

  const pendingProposal = displayData.currentProposal;
  const submitDisabled = !displayData.submitBlockedMessage &&
    (!displayData.canSubmitProposal || pendingProposal || !canSubmit(scoreResult, offerText));

  return (
    <>
      <style>{`
        @keyframes pulse-tab {
          0% { background-color: #fee2e2; color: #b91c1c; border-color: #f87171; }
          50% { background-color: #ffffff; color: #4b5563; border-color: #d1d5db; }
          100% { background-color: #fee2e2; color: #b91c1c; border-color: #f87171; }
        }
        .animate-pulse-tab { animation: pulse-tab 3s ease-in-out infinite; }
      `}</style>
      <div className="w-full bg-gray-300 p-6 flex flex-col relative min-h-screen">
        {/* Bottom fade overlay */}
        <div className="fixed left-0 bottom-0 w-[70%] h-12 bg-gradient-to-t from-gray-300 to-transparent pointer-events-none z-10"></div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-2">
          <button
            onClick={() => handleTabChange("narrative")}
            className={`px-4 py-2 rounded font-medium transition-all border ${
              activeTab === "narrative"
                ? "bg-white text-blue-600 border-blue-400 shadow"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50 hover:border-gray-400"
            }`}
          >
            Narrative
          </button>
          <button
            onClick={() => handleTabChange("proposals")}
            className={`px-4 py-2 rounded font-medium border ${
              activeTab === "proposals"
                ? "bg-white text-blue-600 border-blue-400 shadow"
                : displayData.highlightProposalsTab || pendingProposal
                ? "animate-pulse-tab shadow-md"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50 hover:border-gray-400 transition-all"
            }`}
          >
            Proposals
            {activeTab !== "proposals" && (displayData.highlightProposalsTab || pendingProposal) && (
              <span className="ml-2 inline-flex items-center justify-center w-2 h-2 bg-red-500 rounded-full"></span>
            )}
          </button>
          <button
            onClick={() => handleTabChange("tips")}
            className={`px-4 py-2 rounded font-medium transition-all border ${
              activeTab === "tips"
                ? "bg-white text-blue-600 border-blue-400 shadow"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50 hover:border-gray-400"
            }`}
          >
            Tips
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1">
          {activeTab === "narrative" && (
            <div className="space-y-4">
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-2xl font-bold text-gray-900 mb-4">Your Role</h3>
                <div className="prose prose-gray max-w-none text-gray-700 leading-relaxed">
                  <RoleNarrative>{roleNarrative}</RoleNarrative>
                </div>
              </div>
            </div>
          )}

          {activeTab === "proposals" && (
            <div className="space-y-4">
              {/* BATNA Card */}
              <div className="bg-white rounded-lg shadow-sm p-4">
                <h4 className="text-base font-bold text-gray-900 mb-2">What if I don't reach agreement?</h4>
                {roleBATNA && <p className="text-sm text-gray-700 mb-1">{roleBATNA}</p>}
                <p className="text-sm text-gray-700">
                  If you don't reach agreement, you will earn <span className="font-bold">{threshold} value</span>.
                </p>
              </div>

              {/* Free text → scorer */}
              <ScoringCalculator
                text={offerText}
                onTextChange={setOfferText}
                onCalculate={calculate}
                calculating={calculating}
                result={scoreResult}
                roleRP={roleRP}
                roleName={roleName}
                placeholder={demoOfferPlaceholder}
                footer={
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
                  </button>
                }
              />

              {/* Pending Proposal */}
              {pendingProposal ? (
                <div className="bg-white rounded-lg shadow-md p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-gray-900">Current Proposal</h3>
                    <span className="text-sm text-gray-500">Submitted by: {pendingProposal.submittedByName}</span>
                  </div>
                  {(() => {
                    const value = proposalValue(pendingProposal, viewerFor(pendingProposal));
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
                              {value >= threshold ? "✓ Beats your BATNA" : "✗ Below your BATNA"}
                            </p>
                          )}
                        </div>
                        <div className="bg-blue-50 rounded p-4 mb-4">
                          <h4 className="text-sm font-bold text-gray-700 mb-2">Proposal Details:</h4>
                          <ProposalDetails proposal={pendingProposal} viewer={viewerFor(pendingProposal)} />
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
                  <p className="text-gray-500">No pending proposal. Describe an offer above, click Calculate, then Submit Proposal.</p>
                </div>
              )}

              {/* Proposal History */}
              {displayData.proposals.length > 0 && (
                <div className="bg-white rounded-lg shadow-md p-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-4">Proposal History</h3>
                  <div className="space-y-3">
                    {[...displayData.proposals].reverse().map((proposal) => {
                      const value = proposalValue(proposal, viewerFor(proposal));
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
                              <ProposalDetails proposal={proposal} viewer={viewerFor(proposal)} small />
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
          )}

          {activeTab === "tips" && (
            <div className="space-y-4">
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-2xl font-bold text-gray-900 mb-4">Tips on Negotiation</h3>
                <div className="prose prose-gray max-w-none" dangerouslySetInnerHTML={{ __html: tips }} />
              </div>
            </div>
          )}
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
                  {formatValue(proposalValue(displayData.acceptedProposal, viewerFor(displayData.acceptedProposal)))}
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
    </>
  );
}
