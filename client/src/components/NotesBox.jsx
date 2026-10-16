import React, { useEffect, useRef, useState } from "react";
import { usePlayer } from "@empirica/core/player/classic/react";

// Free-text notes, kept on player.notes so they carry from the read-role stage
// into the negotiation. Saved 5 s after the player pauses typing (each save is
// a server write, so not on every keystroke), and on unmount (stage change,
// tab switch) so the last edit isn't lost.
const SAVE_DELAY_MS = 5000;

export function NotesBox({ className = "" }) {
  const player = usePlayer();
  const [text, setText] = useState(() => player.get("notes") || "");
  const pending = useRef(null); // unsaved text, or null when saved
  const timer = useRef(null);

  const save = () => {
    clearTimeout(timer.current);
    if (pending.current === null) return;
    player.set("notes", pending.current);
    pending.current = null;
  };

  const handleChange = (e) => {
    setText(e.target.value);
    pending.current = e.target.value;
    clearTimeout(timer.current);
    timer.current = setTimeout(save, SAVE_DELAY_MS);
  };

  useEffect(() => save, []);

  return (
    <textarea
      value={text}
      onChange={handleChange}
      placeholder="Jot down notes for yourself here. Only you can see them."
      className={`w-full p-3 border border-gray-300 rounded text-sm text-gray-800 resize-none focus:outline-none focus:border-blue-400 ${className}`}
    />
  );
}
