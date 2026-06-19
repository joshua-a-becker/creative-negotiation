import React, { useEffect, useState } from "react";
import { Button } from "../components/Button.jsx";
import { useGame } from "@empirica/core/player/classic/react";

// Key used to remember which page the participant has reached, so a browser
// refresh resumes on the same page instead of restarting from the beginning.
const STORAGE_KEY = "zopa_consent_page";
const PAGE_COUNT = 4;

function secToMinSec(x) {
  const m = Math.floor(x / 60);
  const s = x % 60;

  return s === 0 ? `${m} minutes` : `${m} minutes ${s} seconds`;
}

// Small dot indicator showing progress through the consent pages.
function PageIndicator({ page }) {
  return (
    <div className="flex justify-center gap-2 mb-6">
      {Array.from({ length: PAGE_COUNT }).map((_, i) => (
        <div
          key={i}
          className={`h-2 rounded-full transition-all ${
            i === page ? "w-8 bg-indigo-600" : "w-2 bg-gray-300"
          }`}
        />
      ))}
    </div>
  );
}

// Page 1 — Introduction / what to expect.
function IntroductionPage({ onNext }) {
  const game = useGame();
  const readRoleTime = game?.get("treatment")?.readRoleTime;
  const readTimeLabel = readRoleTime ? secToMinSec(readRoleTime) : "some time";

  return (
    <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
      <div className="text-center mb-8">
        <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
          Welcome to the Negotiation Club
        </h1>
        <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
      </div>

      <div className="space-y-6 text-gray-700">
        <div className="bg-blue-50 border-l-4 border-blue-500 p-5 rounded-r-lg">
          <h2 className="text-xl font-semibold text-gray-900 mb-3">What to Expect</h2>
          <p className="text-base leading-relaxed">
            This research activity is based on classroom exercises for a standard MBA negotiation course.
          </p>
          <p className="text-base leading-relaxed">
            <br/>For this activity, you will be assigned a fictional role as a member of a group planning a vacation.
          </p>
          <br/>
          <p className="text-base leading-relaxed">
            You will have <span className="font-semibold">{readTimeLabel} to read and prepare</span>. You will then be placed into a <span className="font-semibold">video chat</span> with your negotiation group.  Your role materials will remain available.
          </p>
          <br/>
          <p className="text-base leading-relaxed">
            Your goal is to reach agreement, but also to get as many points as possible.  Points determine bonus (1 point = £1.00) and no agreement means no bonus.
          </p>
        </div>

        <div className="bg-amber-50 border-l-4 border-amber-500 p-5 rounded-r-lg">
          <p className="text-base leading-relaxed">
            <b>If you are not comfortable being on video, please close this page.</b>
          </p>
        </div>

        <p className="text-base leading-relaxed text-center text-gray-600 pt-4">
          The next pages will describe the time commitment and ask you to provide formal consent for your data to be used.
        </p>
      </div>

      <div className="mt-8 flex justify-center">
        <Button handleClick={onNext} autoFocus>
          <span className="text-lg px-4">Continue</span>
        </Button>
      </div>
    </div>
  );
}

// Page 2 — Time commitment.
function TimeCommitmentPage({ onNext, onBack }) {
  const game = useGame();
  const treatment = game?.get("treatment");
  const playerCount = treatment?.playerCount || 3;

  return (
    <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
      <div className="text-center mb-8">
        <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
          Time Commitment
        </h1>
        <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
      </div>

      <div className="space-y-6 text-gray-700">
        <div className="bg-blue-50 border-l-4 border-blue-500 p-5 rounded-r-lg">
          <p className="text-base leading-relaxed">
            In this activity, you will complete a collaborative decision-making process with <span className="font-semibold">{playerCount - 1} other {playerCount - 1 === 1 ? "participant" : "participants"}</span> <span style={{ color: "red", fontWeight: "bold" }}>on a video call</span>.
            <br/><br/>You can end the task at any time with no penalty.  If you leave before reaching agreement, the other participants will be unable to continue and nobody will get a bonus.
            <br/><br/>We expect this task will take approximately 30 minutes.
          </p>
        </div>

        <div className="bg-amber-50 border-l-4 border-amber-500 p-5 rounded-r-lg">
          <p className="text-base leading-relaxed font-semibold">
            Please do not continue unless you have time for the full activity.
          </p>
        </div>
      </div>

      <div className="mt-8 flex justify-center gap-4">
        <Button handleClick={onBack} primary>
          <span className="text-lg px-4">Back</span>
        </Button>
        <Button
          handleClick={() => window.location.href = "https://ucl.ac.uk"}
          primary
        >
          <span className="text-lg px-4">Exit</span>
        </Button>
        <Button handleClick={onNext} autoFocus>
          <span className="text-lg px-4">Continue</span>
        </Button>
      </div>
    </div>
  );
}

// Page 3 — Note on the difficulty of the task.
function DifficultyNotePage({ onNext, onBack }) {
  return (
    <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full p-8 md:p-12">
      <div className="text-center mb-8">
        <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">
          Please Note
        </h1>
        <div className="w-24 h-1 bg-indigo-600 mx-auto rounded-full"></div>
      </div>

      <div className="space-y-6 text-gray-700">
        <div className="bg-amber-50 border-l-4 border-amber-500 p-5 rounded-r-lg">
          <p className="text-base leading-relaxed">
            Negotiation can be a difficult task!  Some groups succeed, and some don't.  Your success on this task depends on the success of the group, which depends on other participants' behavior.
            <br/><br/>The next page will show a formal research consent form. If you do not wish to take part in this study, you can exit simply by closing your web browser.
          </p>
        </div>
      </div>

      <div className="mt-8 flex justify-center gap-4">
        <Button handleClick={onBack} primary>
          <span className="text-lg px-4">Back</span>
        </Button>
        <Button handleClick={onNext} autoFocus>
          <span className="text-lg px-4">Continue</span>
        </Button>
      </div>
    </div>
  );
}

// Page 4 — Research consent form.
function ConsentPage({ onConsent, onBack }) {
  return (
    <div className="bg-white rounded-lg shadow-2xl max-w-4xl w-full p-10 md:p-14 border border-gray-200">
      {/* Header Section */}
      <div className="border-b-2 border-gray-300 pb-6 mb-8">
        <h1 className="text-3xl md:text-4xl font-serif font-bold text-gray-900 text-center mb-2">
          Research Consent Form
        </h1>
        <p className="text-center text-gray-600 font-medium">
          University College London
        </p>
      </div>

      {/* Document Content */}
      <div className="space-y-6 text-gray-800 leading-relaxed">
        {/* Introduction */}
        <div className="bg-blue-50 border border-blue-200 rounded-md p-5">
          <p className="text-base">
            By participating in this activity, you are agreeing to the use of your data for research on negotiation and decision making.
          </p>
          <p className="text-base mt-3">
            We will be recording the video and chat data in this activity. You can disable your video and sound at any point during the activity.
          </p>
        </div>

        {/* Purpose */}
        <section>
          <h2 className="text-xl font-bold text-gray-900 mb-3 font-serif border-l-4 border-indigo-600 pl-4">
            Purpose of the Research
          </h2>
          <p className="text-base ml-5">
            We are trying to understand how people seek agreement in classroom negotiation exercises. This research seeks to improve negotiation education and identify methods for improving outcomes by practicing negotiators.
          </p>
        </section>

        {/* Procedures */}
        <section>
          <h2 className="text-xl font-bold text-gray-900 mb-3 font-serif border-l-4 border-indigo-600 pl-4">
            Procedures
          </h2>
          <p className="text-base ml-5">
            You will be provided with a role narrative and a scoresheet. You will be placed into a video chat with two other participants. Your goal in the activity is to maximize the number of points obtained for your role by reaching the best possible agreement, or earning the points of your no-agreement alternative.
          </p>
        </section>

        {/* Safety Statement */}
        <section>
          <h2 className="text-xl font-bold text-gray-900 mb-3 font-serif border-l-4 border-amber-600 pl-4">
            Safety Statement
          </h2>
          <p className="text-base ml-5">
            This session poses the same discomforts you may expect to encounter in a typical classroom setting. You will be negotiating live with other participants and we cannot control your experience. Negotiation exercises can be challenging, and you may encounter rude or argumentative behavior.
          </p>
        </section>

        {/* Benefits */}
        <section>
          <h2 className="text-xl font-bold text-gray-900 mb-3 font-serif border-l-4 border-green-600 pl-4">
            Benefits
          </h2>
          <p className="text-base ml-5">
            By participating, you will receive practice negotiating comparable to university classroom exercises.  After the task is completed, we will provide you a link to free resources to improve your negotiation skills.
          </p>
        </section>

        {/* Anonymity */}
        <section>
          <h2 className="text-xl font-bold text-gray-900 mb-3 font-serif border-l-4 border-indigo-600 pl-4">
            Anonymity
          </h2>
          <p className="text-base ml-5">
            All data will be anonymized prior to analysis. No identifying information will shared outside this research team. All personal data will be stored securely within a UCL research data environment.
          </p>
        </section>
      </div>

      {/* Consent Statement */}
      <div className="mt-10 pt-6 border-t-2 border-gray-300">
        <div className="bg-indigo-50 border-2 border-indigo-300 rounded-md p-6">
          <p className="text-base font-semibold text-gray-900 text-center">
            By clicking "I Consent" below, you acknowledge that you have read and understood this consent form and agree to participate in this research study.
          </p>
        </div>
      </div>

      {/* Buttons */}
      <div className="mt-8 flex justify-center gap-4">
        <Button handleClick={onBack} primary>
          <span className="text-lg px-8 py-1">Back</span>
        </Button>
        <Button handleClick={onConsent} autoFocus>
          <span className="text-lg px-8 py-1">I Consent</span>
        </Button>
      </div>
    </div>
  );
}

export default function CustomConsent({ next, onConsent }) {
  // Works both as an Empirica intro step (`next`) and as the consent gate
  // (`onConsent`); whichever is provided advances past this flow.
  const advance = next || onConsent;

  // Restore the saved page on mount so a refresh resumes where the
  // participant was, rather than starting over.
  const [page, setPage] = useState(() => {
    const saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
    return Number.isInteger(saved) && saved >= 0 && saved < PAGE_COUNT ? saved : 0;
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(page));
    window.scrollTo(0, 0);
  }, [page]);

  const goNext = () => setPage((p) => Math.min(p + 1, PAGE_COUNT - 1));
  const goBack = () => setPage((p) => Math.max(p - 1, 0));

  const finish = () => {
    // Clear progress so a later visit (or another participant on this
    // browser) starts fresh.
    localStorage.removeItem(STORAGE_KEY);
    advance && advance();
  };

  let content;
  switch (page) {
    case 0:
      content = <IntroductionPage onNext={goNext} />;
      break;
    case 1:
      content = <TimeCommitmentPage onNext={goNext} onBack={goBack} />;
      break;
    case 2:
      content = <DifficultyNotePage onNext={goNext} onBack={goBack} />;
      break;
    default:
      content = <ConsentPage onConsent={finish} onBack={goBack} />;
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <PageIndicator page={page} />
      {content}
    </div>
  );
}
