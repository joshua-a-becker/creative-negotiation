// Tutorial content: the Community Make & Meet venue practice from
// server/src/score_offer/app/config/tutorial.json (scenario "community-make-and-meet-tutorial-v3").
// The participant plays the Community Event Organizer (scorer role
// "Candidate"); the scripted counterpart is the
// Venue Manager. The counterpart's two predetermined offers
// are scored once here (values "to you" = the receiver totals) so every
// participant gets the same deterministic training.

export const tutorialScenario = "tutorial";
export const tutorialRole = "Candidate";
export const tutorialCounterpartName = "Venue Manager";
export const tutorialRequiredIssues = ["Venue fee", "Event date", "Closing time"];
export const tutorialOptionalIssues = ["Projector", "Cleanup", "Cancellation notice", "Setup access"];
export const tutorialIssueHints = {"Projector": "“Can the venue projector be included?”", "Cleanup": "“My volunteers can clean up.”", "Cancellation notice": "“I can cancel without a charge if I give one week’s notice.”", "Setup access": "“I need to get in early to set up.”"};

export const demoNarrative = "**PRACTICE ROLE MATERIALS**\n\n**You are a Community Event Organizer negotiating with a Venue Manager.** You are planning a relaxed Make & Meet where neighbors can try creative activities, share food, and meet local makers.\n\n- *Every offer must include:* a venue fee, an event date, and a closing time. The event can take place on any date in August or September next year.\n- **Example:** “I can pay $300 for the venue on September 15 next year and close at 9 p.m.”\n- **The same offer in different words:** “300 bucks for the venue on 15 Sep, ending at 9.”\n- You prefer a lower fee, a later date, and a later closing time. The Venue Manager prefers a higher fee, an earlier date, and an earlier close.\n- **Other ideas you can raise:** ask “Can the venue projector be included?”; offer “My volunteers can clean up”; request “I can cancel without a charge if I give one week’s notice”; or say “I need to get in early to set up.” You can use your own words.\n";

export const demoBATNA = "If you do not reach an agreement in this practice, you receive 0 points. (The practice does not affect your payment.)";

export const demoRP = 0;

export const demoOfferPlaceholder = "Write your offer here, e.g.\n$300 for the venue on September 15 next year, ending at 9.";

export const demoFriendlyProblem = "The system can’t quite understand that offer yet. Try stating the venue price, an August or September date, and an ending time from 5 through 11. For example: “$300 for September 15, ending at 9.” You can then add one extra idea.";

// The Venue Manager's scripted replies, pre-scored (proposer = Recruiter).
export const tutorialReplies = [
  {
    "text": "I can offer the venue for $500 on August 22 next year, closing at 7:00 p.m. The projector is included if your volunteers handle cleanup.",
    "score": {
      "decision": "scorable",
      "message": "",
      "messages": [],
      "findings": [],
      "lines": [
        "- Venue fee: $500  [+0.29]",
        "- Event date: August 22  [+0.30]",
        "- Closing time: 7:00 p.m.  [+0.33]",
        "- Projector: Venue projector included  [-0.25]",
        "- Cleanup: Organizer handles cleanup  [+1.00]"
      ],
      "lines_for_receiver": [
        "- Venue fee: $500  [-0.29]",
        "- Event date: August 22  [-0.30]",
        "- Closing time: 7:00 p.m.  [-0.33]",
        "- Projector: Venue projector included  [+1.00]",
        "- Cleanup: Organizer handles cleanup  [-0.50]"
      ],
      "total": 1.6657142857142857,
      "total_for_proposer": 1.6657142857142857,
      "total_for_receiver": -0.41571428571428565,
      "proposal_allowed": true,
      "valid_pairs": {
        "Venue fee": "$500",
        "Event date": "August 22",
        "Closing time": "7:00 p.m.",
        "Projector": "Venue projector included",
        "Cleanup": "Organizer handles cleanup"
      },
      "novel_terms": [],
      "missing_required": [],
      "required_issues": [
        "Venue fee",
        "Event date",
        "Closing time"
      ],
      "display_text": "- Venue fee: $500  [+0.29]\n- Event date: August 22  [+0.30]\n- Closing time: 7:00 p.m.  [+0.33]\n- Projector: Venue projector included  [-0.25]\n- Cleanup: Organizer handles cleanup  [+1.00]\nTotal: +1.67",
      "proposer_role": "Recruiter",
      "receiver_role": "Candidate",
      "scenario_id": "community-make-and-meet-tutorial-v3",
      "scenario_variant": "tutorial"
    }
  },
  {
    "text": "My final practice offer is $475 for September 1 next year, closing at 8:00 p.m. The projector is included, your volunteers handle cleanup, free cancellation is allowed with notice, and early setup access is included.",
    "score": {
      "decision": "scorable",
      "message": "",
      "messages": [],
      "findings": [],
      "lines": [
        "- Venue fee: $475  [+0.14]",
        "- Event date: September 1  [-0.03]",
        "- Closing time: 8:00 p.m.  [+0.00]",
        "- Cancellation notice: Free cancellation allowed with notice  [-0.50]",
        "- Setup access: Early setup access included  [-0.25]",
        "- Cleanup: Organizer handles cleanup  [+1.00]",
        "- Projector: Venue projector included  [-0.25]"
      ],
      "lines_for_receiver": [
        "- Venue fee: $475  [-0.14]",
        "- Event date: September 1  [+0.03]",
        "- Closing time: 8:00 p.m.  [+0.00]",
        "- Cancellation notice: Free cancellation allowed with notice  [+0.75]",
        "- Setup access: Early setup access included  [+0.75]",
        "- Cleanup: Organizer handles cleanup  [-0.50]",
        "- Projector: Venue projector included  [+1.00]"
      ],
      "total": 0.10952380952380936,
      "total_for_proposer": 0.10952380952380936,
      "total_for_receiver": 1.8904761904761906,
      "proposal_allowed": true,
      "valid_pairs": {
        "Venue fee": "$475",
        "Event date": "September 1",
        "Closing time": "8:00 p.m.",
        "Cancellation notice": "Free cancellation allowed with notice",
        "Setup access": "Early setup access included",
        "Cleanup": "Organizer handles cleanup",
        "Projector": "Venue projector included"
      },
      "novel_terms": [],
      "missing_required": [],
      "required_issues": [
        "Venue fee",
        "Event date",
        "Closing time"
      ],
      "display_text": "- Venue fee: $475  [+0.14]\n- Event date: September 1  [-0.03]\n- Closing time: 8:00 p.m.  [+0.00]\n- Cancellation notice: Free cancellation allowed with notice  [-0.50]\n- Setup access: Early setup access included  [-0.25]\n- Cleanup: Organizer handles cleanup  [+1.00]\n- Projector: Venue projector included  [-0.25]\nTotal: +0.11",
      "proposer_role": "Recruiter",
      "receiver_role": "Candidate",
      "scenario_id": "community-make-and-meet-tutorial-v3",
      "scenario_variant": "tutorial"
    }
  }
];

export const demoTips = `
<h3>Tips on Negotiation</h3>

<p><strong>Know your priorities:</strong> Not all issues are equally important to you. Focus on getting what you want most, and be flexible on items that matter less.</p>

<p><strong>Look for trade-offs:</strong> If something matters a lot to you but less to others, that's an opportunity for a win-win deal. Offer to give on issues you care less about.</p>

<p><strong>Remember your BATNA:</strong> Your Best Alternative To Negotiated Agreement is finding different roommates. Don't accept a deal that gives you negative points. That's worse than your alternative!</p>

<p><strong>Communicate clearly:</strong> Explain why certain things matter to you. Understanding each other's reasoning can help find creative solutions that work for everyone.</p>
`;
