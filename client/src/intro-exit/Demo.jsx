import React, { useState } from "react";
import { usePlayer } from "@empirica/core/player/classic/react";
import { DemoUI } from "./DemoUI";
import { RoleNarrative } from "../components/RoleNarrative";
import { proposalValue, isScorable } from "../components/negotiationDisplay";
import {
  demoNarrative,
  demoTips,
  demoBATNA,
  demoRP,
  tutorialRole,
  tutorialCounterpartName,
  tutorialRequiredIssues,
  tutorialOptionalIssues,
  tutorialIssueHints,
  tutorialReplies,
} from "./demoContent";

/**
 * Tutorial: the Community Make & Meet venue practice (from
 * original_Creative-Negotiations), fitted into this app's proposal / vote /
 * history flow. The participant is the Community Event Organizer; the Venue
 * Manager is scripted with two predetermined, pre-scored offers.
 *
 * Sequence (mirrors the original tutorial):
 *   INTRO          "This is a tutorial" → read the practice role materials
 *   MAKE_OFFER_1   type a first offer, Calculate, Submit
 *   VOTE_ON_OWN_1  vote on it (the Venue Manager has already rejected it)
 *   COUNTER_1      the Venue Manager's counteroffer — must be Rejected
 *   MAKE_OFFER_2   Modify (copy) either offer, edit it, add ONE new issue
 *   VOTE_ON_OWN_2  vote on it (rejected again)
 *   COUNTER_2      the Venue Manager's final offer — must be Accepted
 *   FINALIZE       confirm the agreement (Finalize Deal)
 *   COMPLETE
 */

const STATES = {
  INTRO: "INTRO",
  MAKE_OFFER_1: "MAKE_OFFER_1",
  VOTE_ON_OWN_1: "VOTE_ON_OWN_1",
  COUNTER_1: "COUNTER_1",
  MAKE_OFFER_2: "MAKE_OFFER_2",
  VOTE_ON_OWN_2: "VOTE_ON_OWN_2",
  COUNTER_2: "COUNTER_2",
  FINALIZE: "FINALIZE",
  COMPLETE: "COMPLETE",
};

const COUNTERPART_ID = "counterpart";

const naturalList = (items) => {
  const list = items.filter(Boolean);
  if (list.length <= 1) return list.join("");
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
};

const HintList = ({ names }) => (
  <ul className="text-left text-base text-gray-700 space-y-1 mt-3">
    {names.map((name) => (
      <li key={name}>
        <span className="font-semibold">{name}:</span> {tutorialIssueHints[name]}
      </li>
    ))}
  </ul>
);

export function Demo({ next }) {
  const player = usePlayer();

  // Single source of truth for the tutorial, persisted on the player so a
  // refresh resumes where the participant left off.
  const [state, setStateRaw] = useState(() => player.get("demo_state") || STATES.INTRO);
  const [proposals, setProposalsRaw] = useState(() => player.get("demo_proposals") || []);
  const [copyUsed, setCopyUsedRaw] = useState(() => player.get("demo_copyUsed") || false);
  const [priorIssues, setPriorIssuesRaw] = useState(() => player.get("demo_priorIssues") || []);

  const saveState = (s) => { setStateRaw(s); player.set("demo_state", s); };
  const saveProposals = (p) => { setProposalsRaw(p); player.set("demo_proposals", p); };
  const saveCopyUsed = (v) => { setCopyUsedRaw(v); player.set("demo_copyUsed", v); };
  const savePriorIssues = (v) => { setPriorIssuesRaw(v); player.set("demo_priorIssues", v); };

  // Modal: { title, body (node), button, onClose?, wide?, emoji? }
  const [modal, setModal] = useState(() => (player.get("demo_state") ? null : introModal()));
  const [showNegativeModal, setShowNegativeModal] = useState(false);

  function introModal() {
    return {
      emoji: "📋",
      title: "This is a tutorial",
      body: "Before the main activity, you will complete a short practice negotiation. It will teach you how to make an offer in your own words, review how the system understood it, respond to the other party, add a new issue, and reach an agreement. The tutorial does not affect your payment.",
      button: "Yes — read role materials",
      onClose: () => setModal(roleModal()),
    };
  }
  function roleModal() {
    return {
      title: "Read your practice role",
      wide: true,
      body: (
        <div className="text-left prose prose-gray max-w-none text-gray-700 max-h-[55vh] overflow-auto pr-2">
          <RoleNarrative>{demoNarrative}</RoleNarrative>
        </div>
      ),
      button: "Yes, I have read and understand the negotiation and am ready to make an offer",
      onClose: () => {
        saveState(STATES.MAKE_OFFER_1);
        setModal({
          emoji: "✍️",
          title: "Make your first offer",
          body: "Type your first offer in the Proposals tab, in your own words. Click Calculate to see how the system understood it and what it is worth to you, then click Submit Proposal.",
          button: "OK",
        });
      },
    };
  }

  const viewerFor = (p) => ({ roleName: tutorialRole, isProposer: p?.submittedBy === "user" });
  const issuesOf = (score) => Object.keys(score?.valid_pairs || {});

  // ---- proposals -----------------------------------------------------------

  // Returns null when accepted, or a modal object explaining why not.
  const handleProposalSubmit = ({ text, score }) => {
    if (state !== STATES.MAKE_OFFER_1 && state !== STATES.MAKE_OFFER_2) {
      return { title: "Not yet", body: "Please follow the tutorial steps before submitting.", button: "OK" };
    }
    if (!isScorable(score)) {
      return { title: "Not scored yet", body: "Fix the points the scorer raised, then Calculate again.", button: "OK" };
    }

    const introduced = issuesOf(score).filter((n) => !priorIssues.includes(n) && !tutorialRequiredIssues.includes(n));
    const available = tutorialOptionalIssues.filter((n) => !priorIssues.includes(n));

    if (state === STATES.MAKE_OFFER_2) {
      if (!copyUsed) {
        return { title: "Copy an offer first", body: "For this practice step, click Modify under one of the offers in the history to copy it, then edit the copied offer.", button: "OK" };
      }
      if (available.length && introduced.length === 0) {
        return {
          title: "Add one new issue",
          body: (<>Add one new issue that has not appeared before. For example:<HintList names={available} /></>),
          button: "OK",
        };
      }
    }

    const mine = {
      id: `you-${Date.now()}`,
      submittedBy: "user",
      submittedByName: "You",
      text,
      score,
      initialVotes: { [COUNTERPART_ID]: "reject" }, // the Venue Manager rejects both practice offers
      finalVotes: {},
      status: "pending",
    };
    saveProposals([...proposals, mine]);
    savePriorIssues([...new Set([...priorIssues, ...issuesOf(score)])]);

    if (state === STATES.MAKE_OFFER_1) {
      saveState(STATES.VOTE_ON_OWN_1);
      setModal({ emoji: "✅", title: "Proposal submitted", body: "Great! Now you have to vote on it, even though it's your own proposal.", button: "OK" });
    } else {
      saveState(STATES.VOTE_ON_OWN_2);
      setModal({
        emoji: "✅",
        title: "New issue introduced",
        body: introduced.length
          ? `Great. Before, you were only negotiating on ${naturalList(priorIssues)}. You introduced ${naturalList(introduced)}. Now vote on your proposal.`
          : "Good! Now vote on your modified proposal.",
        button: "OK",
      });
    }
    return null;
  };

  const counterpartOffer = (index) => ({
    id: `counterpart-${index}`,
    submittedBy: COUNTERPART_ID,
    submittedByName: tutorialCounterpartName,
    text: tutorialReplies[index].text,
    score: tutorialReplies[index].score,
    initialVotes: { [COUNTERPART_ID]: "accept" },
    finalVotes: {},
    status: "pending",
  });

  const handleVote = (proposalId, vote) => {
    const proposal = proposals.find((p) => p.id === proposalId);
    if (!proposal) return;

    // Same rule as the real negotiation: never accept a deal worth < 0 to you.
    if (vote === "accept") {
      const value = proposalValue(proposal, viewerFor(proposal));
      if (value !== null && value < 0) { setShowNegativeModal(true); return; }
    }

    const settle = (status) => proposals.map((p) =>
      p.id === proposalId ? { ...p, status, initialVotes: { ...p.initialVotes, user: vote } } : p
    );

    if (state === STATES.VOTE_ON_OWN_1 || state === STATES.VOTE_ON_OWN_2) {
      const replyIndex = state === STATES.VOTE_ON_OWN_1 ? 0 : 1;
      const reply = counterpartOffer(replyIndex);
      saveProposals([...settle("failed"), reply]);
      savePriorIssues([...new Set([...priorIssues, ...issuesOf(reply.score)])]);
      if (replyIndex === 0) {
        saveState(STATES.COUNTER_1);
        setModal({
          emoji: "💬",
          title: "Review and reject the counteroffer",
          body: `The ${tutorialCounterpartName} rejected your proposal and made a counteroffer. In the real negotiation you could accept or reject it. For this tutorial, click Reject so you can practise making a counteroffer.`,
          button: "OK",
        });
      } else {
        saveState(STATES.COUNTER_2);
        setModal({
          emoji: "🤝",
          title: "Accept the final practice offer",
          body: "This offer covers all of the practice issues and gives both sides positive value. In the real negotiation the choice is yours; for this tutorial, click Accept to finish.",
          button: "OK",
        });
      }
      return;
    }

    if (state === STATES.COUNTER_1) {
      if (vote === "accept") {
        setModal({ emoji: "⚠️", title: "Practice this step first", body: "Normally you may accept or reject. For this tutorial, reject the first counteroffer so you can practise copying, editing, and adding a new issue.", button: "OK" });
        return;
      }
      saveProposals(settle("failed"));
      saveState(STATES.MAKE_OFFER_2);
      const available = tutorialOptionalIssues.filter((n) => !priorIssues.includes(n) && !issuesOf(proposal.score).includes(n));
      setModal({
        emoji: "🔧",
        title: "Copy, edit, and add one new issue",
        body: (<>Click <strong>Modify</strong> under your offer or the {tutorialCounterpartName}'s offer to copy it into the box. Edit it, then add one new issue in your own words:<HintList names={available} /></>),
        button: "OK",
      });
      return;
    }

    if (state === STATES.COUNTER_2) {
      if (vote === "reject") {
        setModal({ emoji: "⚠️", title: "Accept this practice offer", body: "Normally you could reject it. For this tutorial, accept the final mutually beneficial offer to practise completing an agreement.", button: "OK" });
        return;
      }
      saveProposals(settle("accepted"));
      saveState(STATES.FINALIZE);
    }
  };

  const handleFinalizeVote = (decision) => {
    if (state !== STATES.FINALIZE) return;
    if (decision === "continue") {
      setModal({ emoji: "⚠️", title: "Please finalize", body: "Normally you could keep discussing. For this tutorial, finalize the deal to complete the practice.", button: "OK" });
      return;
    }
    saveState(STATES.COMPLETE);
    setModal({
      emoji: "🎉",
      title: "Practice complete",
      body: "You made an offer in your own words, reviewed how the system read it, rejected a counteroffer, copied and edited an offer, introduced a new issue, and reached an agreement. We'll now take you to the next step.",
      button: "Continue",
      onClose: () => next(),
    });
  };

  // ---- display data -----------------------------------------------------------

  const pending = proposals.find((p) => p.status === "pending") || null;
  const accepted = proposals.find((p) => p.status === "accepted") || null;
  const displayData = {
    playerCount: 2,
    proposals: proposals.filter((p) => p.status !== "pending" && p.status !== "accepted"),
    currentProposal: pending,
    showFinalize: state === STATES.FINALIZE && !!accepted,
    acceptedProposal: accepted,
    canSubmitProposal: state === STATES.MAKE_OFFER_1 || state === STATES.MAKE_OFFER_2,
    submitBlockedMessage:
      state === STATES.INTRO ? "Please read the practice role materials first." : null,
    modifyEnabled: state === STATES.MAKE_OFFER_2,
    highlightProposalsTab: state === STATES.MAKE_OFFER_1,
  };

  const closeModal = () => {
    const m = modal;
    setModal(null);
    if (m?.onClose) m.onClose();
  };

  return (
    <div className="h-screen flex">
      {/* Left side: Demo UI (70% width) */}
      <div className="w-[70%]">
        <DemoUI
          roleName={tutorialRole}
          roleNarrative={demoNarrative}
          roleBATNA={demoBATNA}
          roleRP={demoRP}
          tips={demoTips}
          displayData={displayData}
          viewerFor={viewerFor}
          onProposalSubmit={handleProposalSubmit}
          onCopyOffer={() => saveCopyUsed(true)}
          onVote={handleVote}
          onFinalizeVote={handleFinalizeVote}
        />
      </div>

      {/* Right side: Placeholder for video chat (30% width) */}
      <div className="w-[30%] bg-gray-800 flex items-center justify-center">
        <div className="text-center">
          <div className="text-6xl mb-4">🎥</div>
          <p className="text-white text-xl font-semibold">Video Chat Will Go Here</p>
        </div>
      </div>

      {/* Tutorial Modal */}
      {modal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className={`bg-white rounded-lg shadow-2xl p-8 w-full mx-4 ${modal.wide ? "max-w-3xl" : "max-w-lg"}`}>
            {modal.emoji && <div className="text-6xl mb-4 text-center">{modal.emoji}</div>}
            <h2 className="text-2xl font-bold mb-4 text-center">{modal.title}</h2>
            <div className="text-lg text-gray-700 mb-6 text-center">{modal.body}</div>
            <button
              onClick={closeModal}
              className="w-full bg-green-600 text-white py-4 px-6 rounded-lg hover:bg-green-700 font-bold text-xl"
            >
              {modal.button}
            </button>
          </div>
        </div>
      )}

      {/* Negative Value Warning Modal */}
      {showNegativeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-2xl p-8 max-w-sm w-full mx-4">
            <div className="text-center mb-6">
              <div className="text-6xl mb-4">⚠️</div>
              <h3 className="text-2xl font-bold text-red-600 mb-3">Cannot Accept Deal</h3>
              <p className="text-lg text-gray-700">You can't accept a deal worth negative value.</p>
            </div>
            <button
              onClick={() => setShowNegativeModal(false)}
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
