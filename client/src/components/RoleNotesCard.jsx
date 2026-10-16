import React, { useEffect, useRef, useState } from "react";
import { RoleNarrative } from "./RoleNarrative";
import { NotesBox } from "./NotesBox";

// Left column of the negotiation screen (MaterialsPanel, and the tutorial's
// DemoUI): a white card with Role / Notes tabs. The title and tabs stay put;
// only the tab content scrolls, with a fade at the bottom while there's more.
//   introText       optional line shown above the narrative (treatment text)
//   notesAttribute  player key the notes are saved under (see NotesBox)
export function RoleNotesCard({ roleNarrative, introText, notesAttribute = "notes" }) {
  const [roleTab, setRoleTab] = useState("narrative"); // "narrative" | "notes"

  const roleScrollRef = useRef(null);
  const [roleMoreBelow, setRoleMoreBelow] = useState(false);
  const updateRoleMoreBelow = () => {
    const el = roleScrollRef.current;
    setRoleMoreBelow(!!el && el.scrollTop + el.clientHeight < el.scrollHeight - 4);
  };
  useEffect(() => {
    updateRoleMoreBelow();
    window.addEventListener("resize", updateRoleMoreBelow);
    return () => window.removeEventListener("resize", updateRoleMoreBelow);
  }, [roleTab, roleNarrative, introText]);

  return (
    <div className="flex-1 min-h-0 bg-white rounded-lg shadow-md p-6 flex flex-col">
      <div className="shrink-0 flex items-center justify-between gap-4 mb-4">
        <h3 className="text-2xl font-bold text-gray-900">
          {roleTab === "notes" ? "Your Notes" : "Your Role"}
        </h3>
        <div className="flex gap-1 p-1 bg-gray-200 rounded-lg">
          {[["narrative", "Role"], ["notes", "Notes"]].map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => setRoleTab(tab)}
              className={`px-6 py-2 rounded-md text-base font-bold transition-all ${
                roleTab === tab
                  ? "bg-blue-600 text-white shadow"
                  : "text-gray-700 hover:bg-gray-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {roleTab === "notes" ? (
        <NotesBox className="flex-1 min-h-0" attribute={notesAttribute} />
      ) : (
        <div className="flex-1 min-h-0 relative">
          <div ref={roleScrollRef} onScroll={updateRoleMoreBelow} className="h-full overflow-y-auto">
            {introText && (
              <p className="text-gray-700 mb-4">{introText}</p>
            )}
            <div className="prose prose-gray max-w-none text-gray-700 leading-snug prose-p:my-2 prose-li:my-0.5 prose-headings:my-3">
              <RoleNarrative>{roleNarrative}</RoleNarrative>
            </div>
          </div>
          {roleMoreBelow && (
            <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white to-transparent pointer-events-none"></div>
          )}
        </div>
      )}
    </div>
  );
}
