import React from "react";

// Page frame shared by both tutorials (Demo.jsx free text, DemoTable.jsx
// table): the practice negotiation panel on the left, a video placeholder on
// the right, and the tutorial's guidance and negative-value modals.
export function DemoLayout({ children, modal, onCloseModal, showNegativeModal, onCloseNegative }) {
  return (
    <div className="h-screen flex overflow-hidden">
      {/* Left side: Demo UI (82% width, as in the real negotiation) */}
      <div className="w-[82%] h-full">
        {children}
      </div>

      {/* Right side: Placeholder for video chat (18% width) */}
      <div className="w-[18%] bg-gray-800 flex items-center justify-center">
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
              onClick={onCloseModal}
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
              onClick={onCloseNegative}
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
