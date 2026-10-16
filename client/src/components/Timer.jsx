import { useStageTimer, useStage } from "@empirica/core/player/classic/react";
import React, { useState, useEffect, useRef } from "react";


export function Timer() {
 const timer = useStageTimer();
 const stage = useStage();
 const [showModal, setShowModal] = useState(false);
 const modalShown = useRef(false);


 let remaining;
 if (timer?.remaining || timer?.remaining === 0) {
   remaining = Math.round(timer?.remaining / 1000);
 }


 const isVideoNegotiate = stage?.get("name") === "Time To Negotiate";
 const isUnder5Min = remaining !== undefined && remaining <= 300;


 useEffect(() => {
   if (isVideoNegotiate && isUnder5Min && !modalShown.current) {
     modalShown.current = true;
     setShowModal(true);
   }
 }, [isVideoNegotiate, isUnder5Min]);


 return (
   <>
     <div className="flex flex-col items-center whitespace-nowrap">
       Time Remaining<h1 className="tabular-nums text-3xl text-gray-500 font-semibold">
          {humanTimer(remaining)}
       </h1>
     </div>


     {showModal && (
       <div className="fixed inset-0 flex items-center justify-center z-50 bg-black bg-opacity-40">
         <div className="bg-white rounded-xl shadow-xl p-8 flex flex-col items-center gap-4">
           <p className="text-2xl font-bold text-gray-800"><center>5 min warning!  <br/><br/>In 5 minutes the game will end<br/>to adhere to standards for hourly pay.</center></p>
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



