import React from "react";
import { EndingMessage } from "./NegotiationOutcome";

// Last exit step after the survey: thanks, plus the ending message with the
// Prolific completion link (held back from NegotiationOutcome until now).
export function SurveyComplete() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
        <div className="text-center mb-8">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
            Thank You!
          </h1>
          <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
        </div>
        <p className="text-lg text-gray-700 text-center mb-6">
          Your survey responses have been recorded.
        </p>
        <EndingMessage />
      </div>
    </div>
  );
}
