import { useStageTimer, useStage, usePlayer } from "@empirica/core/player/classic/react";
import React, { useState, useEffect } from "react";

// In the negotiation stage the timer stays hidden until this many seconds are
// left; then it appears and a one-time warning modal pops up.
const NEGOTIATE_WARNING_SECONDS = 300;


export function Timer() {
 const timer = useStageTimer();
 const stage = useStage();
 const player = usePlayer();
 const [showModal, setShowModal] = useState(false);


 let remaining;
 if (timer?.remaining || timer?.remaining === 0) {
   remaining = Math.round(timer?.remaining / 1000);
 }


 const isVideoNegotiate = stage?.get("name") === "Time To Negotiate";
 const isUnder5Min = remaining !== undefined && remaining <= NEGOTIATE_WARNING_SECONDS;
 const hidden = isVideoNegotiate && !isUnder5Min;


 // Show the warning once per player per stage (kept on player.stage so a
 // page refresh doesn't pop it again).
 useEffect(() => {
   if (isVideoNegotiate && isUnder5Min && !player.stage.get("fiveMinWarningShown")) {
     player.stage.set("fiveMinWarningShown", true);
     setShowModal(true);
   }
 }, [isVideoNegotiate, isUnder5Min]);


 return (
   <>
     {!hidden && (
       <div className="flex flex-col items-center whitespace-nowrap">
         Time Remaining<h1 className="tabular-nums text-3xl text-gray-500 font-semibold">
            {humanTimer(remaining)}
         </h1>
       </div>
     )}


     {showModal && (
       <div className="fixed inset-0 flex items-center justify-center z-50 bg-black bg-opacity-40">
         <div className="bg-white rounded-xl shadow-xl p-8 max-w-md mx-4 flex flex-col items-center gap-4">
           <div className="text-6xl">⏰</div>
           <p className="text-xl font-bold text-gray-800 text-center">Due to prolific guidelines, we must end this activity in 5 minutes, even if you haven't reached agreement.</p>
           <button
             onClick={() => setShowModal(false)}
             className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
           >
             OK
           </button>
         </div>
       </div>
     )}
   </>
 );
}


function humanTimer(seconds) {
 if (seconds === null || seconds === undefined) {
   return "--:--";
 }


 let out = "";
 const s = seconds % 60;
 out += s < 10 ? "0" + s : s;


 const min = (seconds - s) / 60;
 if (min === 0) {
   return `00:${out}`;
 }


 const m = min % 60;
 out = `${m < 10 ? "0" + m : m}:${out}`;


 const h = (min - m) / 60;
 if (h === 0) {
   return out;
 }


 return `${h}:${out}`;
}



