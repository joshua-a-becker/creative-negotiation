import React, { useState } from "react";
import { usePlayer, useGame } from "@empirica/core/player/classic/react";
import { Button } from "../components/Button";

export function FollowupQuestion({ next }) {
  const player = usePlayer();
  const game = useGame();

  const no_agreement_ending_message =
    game.get("treatment").noAgreementEndingMessage || "";

  // Get bonus and agreement status from player data (set in onRoundEnded callback)
  const bonus = player.get("bonus") || 0;
  const reachedAgreement = bonus > 0;

  const [comments, setComments] = useState("");

  function handleSubmit(event) {
    event.preventDefault();
    player.set("followupComments", comments);
    next();
  }

  function handleSkip() {
    player.set("followupComments", "");
    next();
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
            Negotiation Complete
          </h1>
          <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
        </div>

        <div className="space-y-6">
          {reachedAgreement ? (
            <>
              <div className="bg-green-50 border-l-4 border-green-500 p-6 rounded-r-lg">
                <div className="flex items-center mb-4">
                  <div className="text-5xl mr-4">🎉</div>
                  <h2 className="text-2xl font-bold text-green-900">
                    Congratulations!
                  </h2>
                </div>
                <p className="text-lg text-gray-700">
                  Your group reached an agreement.
                </p>
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center">
                <p className="text-xl text-gray-700 mb-2">Your score is:</p>
                <p className="text-5xl font-bold text-blue-600">
                  {bonus.toFixed(2)} points
                </p>
              </div>
            </>
          ) : (
            <>
              <div className="bg-amber-50 border-l-4 border-amber-500 p-6 rounded-r-lg">
                <div className="flex items-center mb-4">
                  <h2 className="text-2xl font-bold text-amber-900">
                    No Agreement Reached
                  </h2>
                </div>
                <p className="text-lg text-gray-700">
                  Sorry, your group did not reach agreement!
                </p>
              </div>

              <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
                <p className="text-lg text-gray-700">
                  You will receive the base payment only.
                </p>
              </div>
            </>
          )}

          

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-6">
              <label
                htmlFor="comments"
                className="block text-lg font-medium text-gray-700 mb-4"
              >
                Before you go, please share with us any comments you have about
                this activity. Thanks for the feedback!
              </label>
              <textarea
                className="appearance-none block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-empirica-500 focus:border-empirica-500 sm:text-sm"
                dir="auto"
                id="comments"
                name="comments"
                rows={6}
                value={comments}
                onChange={(e) => setComments(e.target.value)}
              />
            </div>

            <div className="flex justify-center gap-4">
              <Button type="submit" autoFocus>
                <span className="text-lg px-4">Submit</span>
              </Button>
              <Button type="button" primary handleClick={handleSkip}>
                <span className="text-lg px-4">Skip</span>
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
