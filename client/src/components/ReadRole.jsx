import React, { useState } from "react";
import { usePlayer, useStageTimer } from "@empirica/core/player/classic/react";
import { ReadRoleContent } from "./ReadRoleContent";

export function ReadRole({ profileComponent }) {
  const player = usePlayer();
  const timer = useStageTimer();
  const remainingSeconds = timer?.remaining ? Math.round(timer.remaining / 1000) : 0;
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  const remainingTime = `${minutes}:${seconds.toString().padStart(2, '0')}`;

  // Welcome modal state
  const hasSeenReadRoleModal = player.get("hasSeenReadRoleModal") || false;
  const [showWelcomeModal, setShowWelcomeModal] = useState(!hasSeenReadRoleModal);

  // After dismissing modal, show the actual content
  if (!showWelcomeModal) {
    return <ReadRoleContent profileComponent={profileComponent} />;
  }

  // Show the welcome modal over a neutral backdrop (no video during prep)
  return (
    <div className="relative">
      {/* Neutral backdrop behind the modal. Deliberately NOT the lobby (which
          would mount VideoChat and re-acquire the camera): this is a prep stage,
          so the camera stays released and nothing is recorded. */}
      <div className="min-h-screen bg-gray-100" />

      {/* Welcome Modal */}
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg shadow-2xl p-8 max-w-xl w-full mx-4">
          <div className="text-center mb-6">
            {/*<div className="text-6xl mb-4">📚</div>*/}
            <h2 className="text-3xl font-bold mb-2">
              Your Group is Ready
            </h2>
            <h3 className="text-2xl font-semibold text-blue-700 mb-4">
              Prepare for Your Negotiation!
            </h3>
            <div className="text-left text-gray-700 leading-relaxed space-y-3">
              <p>
                You now have <strong>{remainingTime}</strong> to review your role materials.
              </p>
              <p>
                Don't worry if you need more time, <strong>you'll still have this information while you negotiate.</strong>
              </p>
              <p>
                These negotiation tips will also remain available throughout the activity.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              player.set("hasSeenReadRoleModal", true);
              setShowWelcomeModal(false);
            }}
            className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold text-lg"
          >
            Got It!
          </button>
        </div>
      </div>
    </div>
  );
}
