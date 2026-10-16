import React, { useState } from "react";
import { usePlayer } from "@empirica/core/player/classic/react";
import { DemoUI } from "./DemoUI";
import { DemoLayout } from "./DemoLayout";
import { RoleNarrative } from "../components/RoleNarrative";
import { tableValue } from "../components/tableScoring";
import { formatValue } from "../components/negotiationDisplay";
import {
  demoTableNarrative,
  demoBATNA,
  demoRP,
  tutorialCounterpartName,
  tutorialTableScoresheet,
  tutorialTableReplies,
} from "./demoContent";

/**
 * Tutorial for table-mode treatments (scoringMode: "table"): the same Venue
 * Manager practice as Demo.jsx, but offers are built by choosing one option
 * per issue from a payoff table. As in the real negotiation, the proposer's
 * own proposal counts as their accept vote. The Venue Manager rejects both
 * practice offers and replies with two scripted offers.
 *
 * Sequence:
 *   INTRO         "This is a tutorial" → read the practice role
 *   MAKE_OFFER_1  choose an option for every issue, Submit
 *   COUNTER_1     the Venue Manager's counteroffer (worth -3) — must be Rejected
 *   MAKE_OFFER_2  Modify (copy) an offer, change it, Submit
 *   COUNTER_2     the Venue Manager's final offer (worth +2) — must be Accepted
 *   FINALIZE      confirm the agreement (Finalize Deal)
 *   COMPLETE
 */

const STATES = {
  INTRO: "INTRO",
  MAKE_OFFER_1: "MAKE_OFFER_1",
  COUNTER_1: "COUNTER_1",
  MAKE_OFFER_2: "MAKE_OFFER_2",
  COUNTER_2: "COUNTER_2",
  FINALIZE: "FINALIZE",
  COMPLETE: "COMPLETE",
};

const COUNTERPART_ID = "counterpart";
const sheet = tutorialTableScoresheet;
const valueOf = (options) => tableValue(sheet, options);

export function DemoTable({ next }) {
  const player = usePlayer();

  // Persisted on the player so a refresh resumes where the participant left off.
  const [state, setStateRaw] = useState(() => player.get("demoTable_state") || STATES.INTRO);
  const [proposals, setProposalsRaw] = useState(() => player.get("demoTable_proposals") || []);
  const [copyUsed, setCopyUsedRaw] = useState(() => player.get("demoTable_copyUsed") || false);

  const saveState = (s) => { setStateRaw(s); player.set("demoTable_state", s); };
  const saveProposals = (p) => { setProposalsRaw(p); player.set("demoTable_proposals", p); };
  const saveCopyUsed = (v) => { setCopyUsedRaw(v); player.set("demoTable_copyUsed", v); };

  // Modal: { title, body (node), button, onClose?, wide?, emoji? }
  const [modal, setModal] = useState(() => (player.get("demoTable_state") ? null : introModal()));
  const [showNegativeModal, setShowNegativeModal] = useState(false);

  function introModal() {
    return {
      emoji: "📋",
      title: "This is a tutorial",
      body: "Before the main activity, you will complete a short practice negotiation. It will teach you how to build an offer from your scoring table, respond to the other party, modify an offer, and reach an agreement. The tutorial does not affect your payment.",
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
          <RoleNarrative>{demoTableNarrative}</RoleNarrative>
        </div>
      ),
      button: "Yes, I have read and understand the negotiation and am ready to make an offer",
      onClose: () => {
        saveState(STATES.MAKE_OFFER_1);
        setModal({
          emoji: "✍️",
          title: "Make your first offer",
          body: "In the scoring table, choose one option for each issue. The table shows what each option is worth to you and adds up the total. When every issue has an option, click Submit Proposal. Submitting counts as your own vote to accept.",
          button: "OK",
        });
      },
    };
  }

  const counterpartOffer = (index) => ({
    id: `counterpart-${index}`,
    submittedBy: COUNTERPART_ID,
    submittedByName: tutorialCounterpartName,
    options: tutorialTableReplies[index],
    initialVotes: { [COUNTERPART_ID]: "accept" },
    finalVotes: {},
    status: "pending",
  });

  // ---- proposals -----------------------------------------------------------

  // Returns null when accepted, or a modal object explaining why not.
  const handleProposalSubmit = ({ options }) => {
    if (state !== STATES.MAKE_OFFER_1 && state !== STATES.MAKE_OFFER_2) {
      return { title: "Not yet", body: "Please follow the tutorial steps before submitting.", button: "OK" };
    }
    // Same rule as the real negotiation: you can't propose a deal worth < 0 to you.
    if (valueOf(options) < 0) {
      return { title: "Cannot Submit Proposal", body: "You can't propose a deal worth negative value.", button: "OK" };
    }
    if (state === STATES.MAKE_OFFER_2 && !copyUsed) {
      return { title: "Copy an offer first", body: "For this practice step, click Modify under one of the offers in the history to copy it into the table, then change it.", button: "OK" };
    }

    // Your proposal counts as your accept; the Venue Manager rejects both practice offers.
    const mine = {
      id: `you-${Date.now()}`,
      submittedBy: "user",
      submittedByName: "You",
      options,
      initialVotes: { user: "accept", [COUNTERPART_ID]: "reject" },
      finalVotes: {},
      status: "failed",
    };
    const replyIndex = state === STATES.MAKE_OFFER_1 ? 0 : 1;
    const reply = counterpartOffer(replyIndex);
    saveProposals([...proposals, mine, reply]);

    if (replyIndex === 0) {
      saveState(STATES.COUNTER_1);
      setModal({
        emoji: "💬",
        title: "Review and reject the counteroffer",
        body: "Your offer has been rejected. The other player (not real yet) has made a counteroffer. Review and reject that counteroffer.",
        button: "OK",
      });
    } else {
      saveState(STATES.COUNTER_2);
      setModal({
        emoji: "🤝",
        title: "Accept the final practice offer",
        body: `The ${tutorialCounterpartName} rejected your proposal again, but made a better offer: it is worth ${formatValue(valueOf(reply.options))} to you. In the real negotiation the choice is yours; for this tutorial, click Accept to finish.`,
        button: "OK",
      });
    }
    return null;
  };

  const handleVote = (proposalId, vote) => {
    const proposal = proposals.find((p) => p.id === proposalId);
    if (!proposal) return;

    // Same rule as the real negotiation: never accept a deal worth < 0 to you.
    if (vote === "accept" && valueOf(proposal.options) < 0) {
      setShowNegativeModal(true);
      return;
    }

    const settle = (status) => proposals.map((p) =>
      p.id === proposalId ? { ...p, status, initialVotes: { ...p.initialVotes, user: vote } } : p
    );

    if (state === STATES.COUNTER_1) {
      if (vote === "accept") return; // can't happen: the first counteroffer is negative
      saveProposals(settle("failed"));
      saveState(STATES.MAKE_OFFER_2);
      setModal({
        emoji: "🔧",
        title: "Copy and change an offer",
        body: (<>Click <strong>Modify</strong> under your offer or the {tutorialCounterpartName}'s offer to copy its choices into the table. Change at least one option, then click Submit Proposal.</>),
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
      body: "You built an offer from your scoring table, rejected a counteroffer, copied and changed an offer, and reached an agreement. We'll now take you to the next step.",
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
    <DemoLayout
      modal={modal}
      onCloseModal={closeModal}
      showNegativeModal={showNegativeModal}
      onCloseNegative={() => setShowNegativeModal(false)}
    >
      <DemoUI
        roleName="Community Event Organizer"
        roleNarrative={demoTableNarrative}
        roleBATNA={demoBATNA}
        roleRP={demoRP}
        displayData={displayData}
        viewerFor={() => ({})}
        onProposalSubmit={handleProposalSubmit}
        onCopyOffer={() => saveCopyUsed(true)}
        onVote={handleVote}
        onFinalizeVote={handleFinalizeVote}
        tableScoresheet={sheet}
      />
    </DemoLayout>
  );
}
