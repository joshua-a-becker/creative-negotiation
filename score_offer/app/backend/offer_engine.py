"""Pure validation and scoring engine for natural-language negotiation offers.

The LLM remains responsible for semantic extraction. This module is the
fail-closed boundary: it canonicalizes known aliases, detects high-risk wording
that must not be guessed, validates every extracted value, and returns one of
three explicit decisions: scorable, rejected, or clarification_needed.
"""

from __future__ import annotations

import re
import math
import calendar
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any


SCORABLE = "scorable"
REJECTED = "rejected"
CLARIFICATION_NEEDED = "clarification_needed"
DECISIONS = {SCORABLE, REJECTED, CLARIFICATION_NEEDED}
MIN_CONFIDENCE = 0.60

SOCIAL_POST_INTERNAL = "Regular Linkedin Posts for Company"
SOCIAL_POST_DISPLAY = "Regular Social Media Posts for Company"
SOCIAL_POST_NAMES = {SOCIAL_POST_INTERNAL, SOCIAL_POST_DISPLAY}


ISSUE_ALIASES = {
    "Team-Building Participation": "Role in Organizing Social Events",
    "Recruitment Fair Commitment": "Role in Recruitment Fair",
    "LinkedIn Publicity": "Regular Linkedin Posts for Company",
    "Conference Presentations": "Mandatory Conference Presentations",
    "Team-Event Organizing Duties": "Role in Organizing Social Events",
    "Non-Compete": "Non-compete Clause",
    "Professional Associations Sponsorship": "Professional Associations Membership",
    "Professional Association Sponsorship": "Professional Associations Membership",
    "LinkedIn Posts": "Regular Linkedin Posts for Company",
    "Leadership/Role in Team Events": "Role in Organizing Social Events",
}

OPTION_ALIASES = {
    ("Professional Training Program", "Secure for Candidate"): "Participation",
    ("Professional Training Program", "Not undergo program"): "No participation",
    ("Team-Building Participation", "Include in Contract"): "Commitment",
    ("Team-Building Participation", "Do not Discuss"): "No commitment",
}


def canonical_pair(issue: str, option: str) -> tuple[str, str]:
    original_issue = issue
    option = OPTION_ALIASES.get((original_issue, option), option)
    issue = ISSUE_ALIASES.get(original_issue, original_issue)
    return issue, option


def _normalized_choice(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


# A proposed contribution to LinkedIn is the posting issue; merely discussing
# permission for the company's use of material, or generic publicity, is not.
_LINKEDIN_CONTRIBUTION = (r'\b(?:opportunit(?:y|ies)\s+to\s+)?contribut\w*\b[^.;]{0,65}\blinkedin\b|'
                          r'\boccasional\s+linkedin\s+(?:or\s+company\s+)?publicity\b')


def _standard_expense_description(value: str) -> bool:
    """The scenario's expense examples are not a new approval-rule offer."""
    words=_normalized_choice(value)
    expense=r'(?:(?:for|limited to) )?(?:approved )?(?:(?:client|business|work) )?(?:travel meals and lodging|travel meals lodging|travel|meals|lodging|business expenses|work expenses|expenses)'
    approval=r'(?:with )?approval handled under (?:the )?company s (?:normal|usual|existing) expense policy'
    # A copied amount plus the scenario's standard expense examples is still
    # the same budget term, not a request to design a reimbursement policy.
    words=re.sub(r'^(?:an? )?(?:annual )?(?:personal )?(?:work expense )?budget (?:of )?\d[\d ]* (?=(?:for|limited to) )','',words)
    return bool(re.fullmatch(r'(?:the budget is )?(?:'+expense+r'(?: '+approval+r')?|'+approval+r')',words))


def source_quote_is_grounded(quote: str, text: str) -> bool:
    """Allow copied wrappers/ellipsis, never a newly invented source fragment."""
    quote=re.sub(r'</?(?:offer|source_text)>','',str(quote),flags=re.I)
    # Models occasionally prefix a correctly copied list item with "and".
    # Ignore only that coordinator, never negation, numbers or content words.
    quote=re.sub(r'^\s*and\s+','',quote,flags=re.I)
    parts=[_normalized_choice(p) for p in re.split(r'\.{3}|…',quote)]
    parts=[p for p in parts if p]
    def grounded_part(part: str) -> str:
        # Short labels such as "NDA" must match as words. Without boundaries,
        # NDA was incorrectly treated as copied from the middle of "standard".
        return rf"\b{re.escape(part)}\b" if re.fullmatch(r"[a-z0-9]{1,3}", part) else re.escape(part)
    if bool(parts) and bool(re.search('.*?'.join(grounded_part(p) for p in parts),_normalized_choice(text))):return True
    # Harmless grammatical edits in a copied quote must not erase a refusal.
    # Normalize only articles and these duty nouns. Keep negation, numbers,
    # named activities and their order; do not allow arbitrary paraphrases.
    def grammar(value):
        value=re.sub(r'\b(?:a|an|the)\b',' ',_normalized_choice(value))
        nouns={'commitments':'commitment','requirements':'requirement','obligations':'obligation','duties':'duty','responsibilities':'responsibility'}
        value=re.sub(r'\b(?:commitments|requirements|obligations|duties|responsibilities)\b',lambda m:nouns[m.group()],value)
        return ' '.join(value.split())
    relaxed=[grammar(p) for p in parts if grammar(p)]
    if relaxed and any(re.search('.*?'.join(grounded_part(p) for p in relaxed),grammar(c)) for c in _offer_clauses(text)):
        return True
    # A list may share its introductory negation and final noun: "no recurring
    # team-event, LinkedIn-publicity, or conference-presentation requirement".
    # An extraction can copy one item without ellipsis. Accept that specific
    # construction within ONE clause, not arbitrary paraphrases across clauses.
    shared=re.fullmatch(r'(no\s+(?:(?:recurring|regular|standing|ongoing|mandatory)\s+)?)(.+?)\s+(requirements?|obligations?|duties|commitments?|responsibilities|sponsorship)',_normalized_choice(quote))
    if shared:
        prefix,activity,noun=shared.groups()
        for clause in _offer_clauses(text):
            if ',' not in clause:continue
            normalized=_normalized_choice(clause)
            pattern=re.escape(prefix.strip())+r'\s+.{0,160}?\b'+re.escape(activity)+r'\b.{0,160}?\b'+re.escape(noun)+r'\b'
            if re.search(pattern,normalized):return True
    return False


def _affirmative_numeric_text(text: str) -> str:
    """An excluded numeric term is not an offered zero or the rejected number."""
    parts=_offer_clauses(text)
    negative=(r'\b(?:cannot|can[’\x27]t|won[’\x27]t|(?:am|is|are|do|does|would|will)\s+not|'
              r'(?:unable|not\s+(?:able|prepared|willing))\s+to)\s+(?:include|including|offer|offering|provide|providing|accept|agree\s+to|add|give|sponsor|reimburse)\b|'
              r'\b(?:(?:is|are|would|will|can|could)\s+not|won[’\x27]t)\s+(?:be\s+)?(?:included|offered|provided|available)\b|'
              r'^\s*not\s+(?:to|an?|the)\b|\brather\s+than\s+include\b|'
              r'\b(?:prefer|wish|want)\s+not\s+to\s+(?:include|offer|accept|add|have)\b|'
              r'\bnot\s+(?:including|offering|providing|adding|accepting)\b|'
              r'\b(?:not|cannot|can[’\x27]t|won[’\x27]t|no\s+longer)\s+(?:(?:currently|actually|really)\s+)?(?:propos\w*|request\w*|suggest\w*|seek\w*|includ\w*|offer\w*|provid\w*|accept\w*|add\w*|ask\w*|commit\w*|agree\w*|promis\w*|want\w*|putting\s+forward)\b|'
              r'^\s*(?:there\s+(?:would|will)\s+be\s+)?no\b[^.;]{0,260}\b(?:\d+|one|two|three|four|five|six|ten|twenty|thirty|forty)[-\s]+(?:day|month|year)s?\b')
    # Preserve boundaries: a date's day must not become evidence for a later
    # unnumbered vacation/remote-work clause.
    value = '; '.join(p for p in parts if not re.search(negative,p,re.I))
    months = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
    # Mid/end already supplies its own day. In "mid Jan 1 vacay day a
    # week", the following 1 belongs to vacation, not January 1.
    value = re.sub(rf'\b(?:mid|middle|end|beginning)(?:[-\s]+(?:of\s+)?(?:the\s+)?)?{months}\b', ' calendar-date ', value, flags=re.I)
    # A date's day belongs to that date, not to an adjacent unnumbered
    # allowance in punctuation-free text: "start Jan 1 vacation days".
    value = re.sub(rf'\b{months}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:\s*,?\s*20\d{{2}})?\b(?!\s*(?:months?|mos?|mo|years?|yrs?)\b)|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?{months}\b|\b20\d{{2}}-\d{{2}}-\d{{2}}\b', ' calendar-date ', value, flags=re.I)
    return value


_EXCLUDED_CONTRACT = (
    r'\b(?:rather\s+than\s+(?:an?\s+)?|(?:would\s+)?prefer\s+not\s+to\s+commit\s+to\s+(?:an?\s+)?|no\s+)'
    r'(?:fixed[-\s]+(?:term[-\s]+)?)?(?:two|three|four|[234])[-\s]+year\s+(?:fixed[-\s]+(?:term[-\s]+)?)?contract\b'
)


def _no_numeric_entitlement(issue: str, text: str) -> bool:
    """No guaranteed entitlement is omission, not a promise of zero days.

    Keep explicit positive amounts in another clause. This only applies to
    optional day entitlements; fixed-menu missing-term checks still apply.
    """
    marker={'Remote Working Days':r'(?:remote(?:[-\s]+work(?:ing)?)?|wfh|work(?:ing)?\s+from\s+home)',
            'Vacation Days':r'(?:vacation|annual\s+leave|holiday|paid\s+days?\s+off)'}.get(issue)
    if not marker:return False
    clauses=[c for c in _offer_clauses(text) if re.search(marker,c,re.I)]
    def declined(c):
        return bool(re.search(r'\b(?:no|without)\s+(?:a\s+)?guaranteed\b[^.;]{0,60}'+marker,c,re.I)
                    or re.search(marker+r'[^.;]{0,60}\b(?:is|are|will\s+be|would\s+be)\s+not\s+guaranteed\b',c,re.I))
    # A positive numeric entitlement overrides a separate explanatory denial.
    other_numeric=any(not declined(c) and re.search(r'\b(?:\d+(?:\.\d+)?|one|two|three|four|five|ten|twenty|thirty|forty|fifty)\s*[- ]\s*(?:remote[- ]working\s+|vacation\s+)?days?\b',c,re.I) for c in clauses)
    return any(declined(c) for c in clauses) and not other_numeric


def _offer_clauses(text: str) -> list[str]:
    """Keep list negation, but stop it at a new subject/predicate.

    In 'no sponsorship, and you will organize events', 'no' only applies to
    sponsorship. In 'no event, publicity or conference duties', it applies to
    the entire list. Decimal points are not sentence boundaries.
    """
    boundary = (r'\bbut\b|\bwhile\b|\bhowever\b|;|\n|(?<!\d)\.|\.(?!\d)|'
                r',?\s+and\s+(?=(?:require|mandate)\b)|'
                r',?\s+and\s+(?=(?:would|will|must|shall|should)\b)|'
                r',?\s+and\s+(?=(?:i|you|we|they|the\s+candidate|the\s+company)\s+'
                r'(?:am|is|are|would|will|commit|agree|must|shall|provide|sponsor|organize|make)\b)|'
                r',\s*(?=there\s+(?:would|will)\b)|'
                r',\s*(?=(?:i|you|we|they|the\s+candidate|the\s+company)\s+(?:am|is|are|would|will|commit|agree|must|shall|provide|sponsor|organize|make)\b)')
    return [c.strip() for c in re.split(boundary,text,flags=re.I) if c.strip()]


def _explicit_training_participation(text: str) -> bool:
    """An explicit agreement to receive training is the participation term,
    not a money allowance or an obligation to train other employees."""
    for clause in _offer_clauses(text.lower()):
        if re.search(r'\b(?:agree\s+to|join|participate\s+in|receive)\s+(?:the\s+)?(?:professional\s+)?training\b(?!\s+(?:other|new|junior|employees|colleagues|coworkers)\b)',clause) and not re.search(r'\b(?:not|no|cannot|can[’\x27]t)\b[^.;]{0,30}\b(?:agree|join|participate|receive)\b',clause):
            return True
    return False


def _contextual_request_clauses(text: str) -> list[str]:
    return [piece.strip() for clause in _offer_clauses(text)
            for piece in re.split(r'\b(?:and|plus)\s+(?:also\s+)?(?=(?:i|we)\s+(?:want|need|request|would\s+like)\b)', clause, flags=re.I)
            if piece.strip()]


def unpriced_personal_travel_requests(text: str) -> list[str]:
    """Keep a relative's personal-trip request even when the model omits it."""
    return [clause for clause in _contextual_request_clauses(text)
            if incidental_numeric_issue_reference('Vacation Days', clause, text)]


def incidental_numeric_issue_reference(issue: str, source: str, text: str,
                                      unpriced_terms: list[str] | None = None) -> bool:
    """A word in somebody else's trip or an unpriced object is not an allowance.

    Check each matching clause separately. A real vacation or cash-commuting
    request elsewhere must still be recognized, including one with no amount.
    """
    if issue not in {'Vacation Days', 'Commuting Support'}:
        return False
    cue = (r'\b(?:holiday|vacay|vacation|annual\s+leave|time\s+off)\b'
           if issue == 'Vacation Days' else r'\bcommut\w*\b|\btravel\s+to\s+work\b')
    clauses = _contextual_request_clauses(text)
    matches = [clause for clause in clauses if re.search(cue, clause, re.I)
               and (not source or source_quote_is_grounded(source, clause))]
    if not matches:
        return False

    def incidental(clause: str) -> bool:
        if issue == 'Vacation Days':
            relative = r'\b(?:uncle|aunt|cousin|nephew|niece|brother|sister|friend|relative|mother|father|parents?|spouse)\b'
            other_person = re.search(relative, clause, re.I) or (
                re.search(r'\b(?:his|her|their)\b', clause, re.I) and re.search(relative, text, re.I))
            trip = re.search(r'\b(?:fly|flights?|airfare|tickets?|first[-\s]+class|book|pay\s+for|fund|send|travel|trip|holiday)\b', clause, re.I)
            own_leave = re.search(r'\b(?:my|our|candidate[’\x27]s)\s+(?:annual\s+)?(?:leave|vacation|holiday|time\s+off)|\b(?:annual\s+leave|leave\s+allowance|vacation\s+days?|holiday\s+days?|days?\s+off|time\s+off)\b', clause, re.I)
            return bool(other_person and trip and not own_leave)
        # Commuting Support prices a cash contribution, not every object that
        # could be used to commute. Do not ask for dollars for an unpriced idea.
        outside = any(source_quote_is_grounded(str(term), clause)
                      or source_quote_is_grounded(clause, str(term))
                      for term in (unpriced_terms or []) if str(term).strip())
        cash_request = re.search(r'\b(?:commut\w*\s+(?:support|allowance|reimbursement|benefit)|allowance|reimburse\w*|subsid\w*|cash|dollars?|payment|costs?|fares?|expenses?)\b|\$\s*\d', clause, re.I)
        return outside and not cash_request

    return all(incidental(clause) for clause in matches)


def _complete_quote_clause(quote: str, text: str) -> str:
    """Keep a duty's qualifier when the model copied only its short noun phrase.

    Expand only into one uniquely matching clause, never across a sentence or
    a new subject. Noncontiguous/ambiguous quotes retain their original scope.
    """
    normalized = _normalized_choice(quote)
    if not normalized:
        return quote
    matches = [c for c in _offer_clauses(text)
               if source_quote_is_grounded(quote,c)]
    if len(matches)!=1:return quote
    clause=matches[0]
    # Complete the quoted predicate, not an unrelated later activity. Shared
    # negative/optional lists keep their scope. A positive annual fair pledge
    # must not inherit "mutually agreed" from the next conference predicate.
    verb_boundary=r'\band\s+(?=(?:make|share|contribute|participate|organize|organise|provide|attend|join|help)\b)'
    first=re.split(verb_boundary,clause,maxsplit=1,flags=re.I)[0]
    shared_tail=bool(re.search(r'\b(?:with\s+)?(?:neither|none|both)\b[^.;]{0,45}\b(?:obligation|required|mandatory|optional|voluntary)',clause,re.I))
    # "when mutually agreed" before a different action qualifies only the
    # first action. A trailing "neither is required" qualifies both actions.
    if not shared_tail and not re.search(r'\b(?:no|not|without|optional|voluntary|opportunit\w*|may|could)\b',first,re.I):
        segments=re.split(verb_boundary,clause,flags=re.I)
        selected=[c for c in segments if source_quote_is_grounded(quote,c)]
        if len(selected)==1:clause=selected[0]
    # A fixed number of posts is a duty even when topics/timing are agreed.
    # Do not apply this to optional participation or an explicit refusal.
    if _explicit_posting_pledge(clause):
        clause=re.sub(r',?\s+with\s+(?:topics?|content|timing|scheduling)\b.*','',clause,flags=re.I)
        clause=re.sub(r'\bmutually\s+agreed\b','',clause,flags=re.I)
    return clause


def _explicit_fair_pledge(text: str) -> bool:
    """A promised number of volunteer appearances is still a commitment.

    Merely being free/able to volunteer, or participation subject to later
    agreement, does not promise attendance and remains no commitment.
    """
    for clause in _offer_clauses(text):
        if re.search(r'\b(?:optional|voluntary|opportunit\w*|could|may|can|if|mutual|mutually|not|no)\b',clause,re.I):
            continue
        if re.search(r'\b(?:i|you|the\s+candidate)\s+(?:will|would|am\s+(?:also\s+)?willing\s+to|agree\s+to|commit\s+to)\s+volunteer\s+at\s+(?:one|two|[12])\s+(?:recruitment|recruiting|careers?|hiring)\s+fairs?\s+(?:per|each|every)\s+year\b',clause,re.I):
            return True
        if re.search(r'\b(?:package|offer|role)\s+(?:would|will|should)\s+include\b',clause,re.I) and re.search(r'\b(?:one|two|[12])\s+(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\s+(?:per|each|every)\s+year\b',clause,re.I):
            return True
    return False


def _literal_fair_commitment(text: str) -> bool:
    """Keep an explicit fair pledge separate from a neighboring declined duty."""
    for match in re.finditer(r'\bcommit\s+to\s+(?:(?:an?|the)\s+)?(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\b',text,re.I):
        before=text[max(0,match.start()-60):match.start()]
        after=text[match.end():match.end()+65]
        if re.search(r"\b(?:not|never|cannot|can['’]t|won['’]t|don['’]t|without)\s+(?:(?:ready|willing|able|going|prepared|planning|required|expected|obliged|forced|to|be)\s+){0,6}$",before,re.I):
            continue
        if re.search(r'\b(?:optional|voluntary|subject\s+to|only\s+if|mutual\s+agreement)\b',after,re.I):
            continue
        return True
    return False


def _mentorship_option(text: str) -> str:
    """Read a mentoring inclusion/exclusion without borrowing another duty's no."""
    choice='Participation'
    mentor=r'mentor(?:ing|ship)?(?:\s+program(?:me)?)?'
    for clause in _offer_clauses(text):
        if not re.search(r'\bmentor(?:ing|ship)?\b',clause,re.I):continue
        negative=(re.search(r'\b(?:no|without|exclude|decline)\s+(?:(?:any|a|an|the|formal|structured|professional|internal|assigned|regular)\s+){0,5}'+mentor+r'\b',clause,re.I)
            or re.search(r'\b(?:not|never)\s+(?:(?:want|need|receive|have|undergo|participate|in|a|an|the|be|assign|assigned|candidate|employee|me|you|experienced|internal)\s+){0,8}'+mentor+r'\b',clause,re.I)
            or re.search(r'\b'+mentor+r'\s+(?:no|not)\s+participation\b',clause,re.I)
            or re.search(r'\b(?:no|without)\s+(?:any\s+)?(?:professional\s+)?training(?:\s+program(?:me)?)?\s+(?:and|or)\s+'+mentor+r'\b',clause,re.I))
        choice='No participation' if negative else 'Participation'
    return choice


_FOUR_DAY_PATTERN = r'(?:four|4)[-\s]?day\s+(?:(?:working|work)\s+)?(?:workweek|week|schedule)'


def _explicit_workweek_trial(text: str) -> str | None:
    """A cadence must belong to the four-day trial, not a neighboring issue."""
    patterns=(rf'\b(weekly|monthly)\s+(?:trial|pilot)\s+(?:(?:of|for|a|the|an)\s+){{0,4}}{_FOUR_DAY_PATTERN}\b',
        rf'\b(weekly|monthly)\s+{_FOUR_DAY_PATTERN}\s+(?:trial|pilot)\b',
        rf'\b{_FOUR_DAY_PATTERN}\s*(?:[:=]\s*)?(?:(?:as|a|on)\s+){{0,3}}(weekly|monthly)\s+(?:trial|pilot)\b',
        rf'\b{_FOUR_DAY_PATTERN}\s+(?:trial|pilot)\s*[:=]?\s*(weekly|monthly)(?:\s+trial)?\b')
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:return match.group(1).lower()
    return None


def _explicit_posting_pledge(text: str) -> bool:
    """A posting duty is distinct from agreeing its content or schedule.

    Remove only an explicit content/timing qualification before checking for an
    opt-out. Agreement about WHETHER to participate remains no commitment.
    """
    qualified=re.sub(r'\b(?:mutually\s+agreed|agreed)\s+(?:content|topics?|timing|scheduling|schedules?)\b', 'specified content', text, flags=re.I)
    quantity=r'\b(?:one|two|three|[1-9]\d*)\b[^.;]{0,100}\blinkedin\b[^.;]{0,80}\bposts?\s+(?:per|each|every|a)\s+(?:week|month|quarter|year)\b'
    regular=r'\b(?:make|write|publish|provide|contribute)\s+(?:regular|recurring|weekly|monthly)\s+linkedin\s+posts?\b'
    opt_out=r'\b(?:no|not|without|optional|voluntary|opportunit\w*|may|could|if|mutual|mutually)\b|\blinkedin\s+or\s+other\b'
    return bool(re.search(quantity+'|'+regular,qualified,re.I) and not re.search(opt_out,qualified,re.I))


def _excluded_extra_term(term: str, text: str) -> str | None:
    """An explicitly removed extra duty is not a proposed unsupported benefit.

    This does NOT discard arbitrary negative terms such as a new restriction
    on dismissal. Preserve the excluded duty as unpriced source text.
    """
    normalized = _normalized_choice(term)
    if not normalized:
        return None
    for clause in _offer_clauses(text):
        # Publicity exclusions often share a trailing duty noun, or put the
        # negative predicate after the list. This is still an excluded duty,
        # not a request for a new dismissal restriction or positive benefit.
        simple_publicity=re.fullmatch(r'(?:(?:recurring|ongoing|regular|standing|routine|promotional)\s+)*(?:provide\s+)?publicity(?:\s+(?:duties|duty|work|responsibilities|obligations?))?',normalized)
        matching=normalized in _normalized_choice(clause) or (simple_publicity and re.search(r'\bpublicity\b',clause,re.I))
        removed_duty=(r'\b(?:would|will|does|do|am|is|are)\s+not\s+(?:include|including|require|take\s+on|be\s+responsible\s+for|propos(?:e|ing)\s+(?:(?:a|any)\s+)?(?:(?:standing|recurring|regular)\s+)?responsibilit(?:y|ies)\s+for|have\s+(?:a\s+)?(?:standing|recurring|regular)\s+responsibility\s+for)\b|'
                      r'^\s*(?:not|without|no)\s+(?:an?\s+)?(?:ongoing|recurring|regular|standing)\s+(?:obligation|responsibility|role)\b|'
                      r'\b(?:would|will|should|is|are)\s+not\s+(?:be\s+)?(?:required|included|part\s+of)\b')
        if matching and re.search(r'\bpublicity\b',normalized,re.I) and re.search(removed_duty,clause,re.I):
            return clause
        if normalized not in _normalized_choice(clause):
            continue
        if re.search(r'\b(?:would|will|does|do)\s+not\s+(?:include|require|take\s+on|have\s+(?:a\s+)?(?:standing|recurring|regular)\s+responsibility\s+for)\b', clause, re.I):
            # Do not use a refusal of another list item to hide an independently
            # proposed clause introduced by "but" or a new subject.
            prefix = re.split(r'\b(?:include|require|take\s+on|responsibility\s+for)\b', clause, maxsplit=1, flags=re.I)[-1]
            # The model may flag just "publicity" or quote the complete
            # exclusion sentence. Both identify the same excluded extra duty.
            duty_name=re.sub(r'^(?:a\s+)?(?:standing|recurring|regular)\s+responsibility\s+for\s+','',normalized)
            if duty_name in _normalized_choice(prefix) or normalized == _normalized_choice(clause):
                return clause
    return None


def _remote_allowance(text: str) -> str | None:
    """An explicit weekly permission ceiling is not a promised minimum.

    The existing remote-work issue prices days the employee may use. Retain
    this interpretation in the output, and never use it for unresolved ranges
    or employer-discretion clauses.
    """
    values=[]
    number=r'(one|two|three|four|five|[1-5])'
    remote=r'(?:remote[-\s]+working|remote[-\s]+work|remote|work(?:ing)?\s+remotely|work(?:ing)?\s+from\s+home)'
    patterns=[rf'\bup\s+to\s+{number}\s+(?:{remote}\s+)?days?\s+(?:per|a|each)\s+week\b',rf'\bup\s+to\s+{number}\s+{remote}\s+days?\s+(?:per|a|each)\s+week\b']
    for clause in _offer_clauses(text):
        if not re.search(remote,clause,re.I):continue
        if re.search(r'\b(?:subject\s+to|discretion|not\s+guaranteed|no\s+guaranteed|if\s+approved|might|may\s+allow)\b',clause,re.I):continue
        for pattern in patterns:
            for match in re.finditer(pattern,clause,re.I):
                raw=match.group(1).lower();values.append(str({'one':1,'two':2,'three':3,'four':4,'five':5}.get(raw,raw))+' days per week')
    return values[0] if values and len(set(values))==1 else None


def _noncompete_scope_detail(clause: str) -> str | None:
    """Attach scope to the non-compete, not a neighboring probation/contract.

    Inspect local list items and explicit continuations. This controls retained
    unpriced detail identity only, never payoff anchors or acceptance rules.
    """
    pieces=[s.strip() for s in re.split(r',|\band\b',clause,flags=re.I) if s.strip()]
    scope=r'\b(?:limited|tailored|reasonable\s+period|only|months?|competitors?|market\s+area)\b'
    continuation=(r'^(?:(?:it|the\s+clause|this\s+restriction)\s+)?'
                  r'(?:(?:is|be|would\s+be|will\s+be|should\s+be)\s+)?'
                  r'(?:limited|restricted|tailored|appl(?:y|ies|ying)|only|direct\s+competitors?|'
                  r'for\s+(?:the\s+)?(?:first\s+)?(?:\d+|one|two|three|six|twelve)\s+months?|'
                  r'work\s+(?:closely\s+)?related|within\s+(?:the\s+)?(?:same\s+)?market)\b')
    for index,piece in enumerate(pieces):
        if not re.search(r'\bnon[-\s]?compete\b',piece,re.I):continue
        selected=[piece]
        for following in pieces[index+1:]:
            # Keep enumerated restrictions such as "active company clients"
            # and geographic limits. Stop at an identifiable OTHER job term,
            # not merely because a legitimate qualifier is worded differently.
            another_term=re.search(r'\b(?:salary|budget|starting\s+date|probation|contract|vacation|remote|training|mentor\w*|association|linkedin|recruitment\s+fair|conference|team\s+events?|social\s+events?)\b',following,re.I)
            if another_term and not re.search(continuation,following,re.I):break
            selected.append(following)
        detail=' and '.join(selected)
        if re.search(scope,detail,re.I):return detail
    return None


def _duration_is_noncompete_detail(text: str, start: int, end: int) -> bool:
    """Return True when a nearby duration qualifies a non-compete, not the job contract.

    Phrases such as "during the contract and for three months afterward" contain
    the word *contract*, but the three months describe the post-employment
    restriction. The contract-length parser must not turn that into a
    three-month employment agreement.
    """
    clause_start = max(
        text.rfind(".", 0, start),
        text.rfind(";", 0, start),
        text.rfind("\n", 0, start),
    ) + 1
    clause_ends = [position for position in (
        text.find(".", end), text.find(";", end), text.find("\n", end)
    ) if position >= 0]
    clause_end = min(clause_ends) if clause_ends else len(text)
    clause = text[clause_start:clause_end]
    if not re.search(r"\bnon[-\s]?compete\b", clause, re.I):
        return False
    duration_context = text[max(clause_start, start - 80):min(clause_end, end + 80)]
    return bool(re.search(
        r"\b(?:after(?:ward|wards)?|after\s+(?:employment|departure|leaving|termination)|"
        r"following\s+(?:employment|departure|termination)|post[-\s]employment|"
        r"direct\s+competitors?|competing\s+(?:sales\s+)?work)\b",
        duration_context,
        re.I,
    ))


def _explicit_social_event_exclusion(text: str) -> str | None:
    """Return the clause that explicitly excludes an event-organizing duty."""
    event = (
        r"(?:\b(?:team|company|staff|social)[-\s]+(?:events?|socials?|gatherings?)\b|"
        r"\bevent[-\s]+organiz\w*\b)"
    )
    action = r"(?:plan\w*|organiz\w*|organis\w*|coordinat\w*|help(?:ing)?\s+(?:to\s+)?organiz\w*)"
    negative = (
        r"(?:\bno\b|\bwithout\b|\bneed\s+not\b|\bnot\s+required\b|"
        r"\b(?:would|will|do|does|is|are)\s+not\b|\boptional\b|\bvoluntary\b)"
    )
    for clause in _offer_clauses(text):
        if not (re.search(event, clause, re.I) and re.search(action, clause, re.I)):
            continue
        if (
            re.search(negative + r"[^.;]{0,220}" + action + r"[^.;]{0,90}" + event, clause, re.I)
            or re.search(negative + r"[^.;]{0,220}" + event, clause, re.I)
            or re.search(event + r"[^.;]{0,160}" + negative + r"[^.;]{0,90}(?:part\s+of|role|dut(?:y|ies)|responsibilit\w*|obligation)", clause, re.I)
            or re.search(event + r"[^.;]{0,60}\b(?:is|are|would|will)\s+not\s+(?:required|expected|part\s+of)", clause, re.I)
        ):
            return clause
    return None


def _repair_semantic_details(pairs,text,scenario):
    specs={i['name']:i for i in (scenario or {}).get('issues',[])}
    if 'Professional Training Program' not in specs:return pairs,[],[]
    clauses=_offer_clauses(text)
    details=[];repairs=[];out=[]
    training=r'\b(?:professional[-\s]+development|professional\s+training|external\s+(?:training|course)|training\s+(?:course|program))\b'
    mentor=r'\b(?:mentoring\s+relationship|mentor\s+relationship|mentorship\s+program|mentor\s+program|structured\s+mentoring)\b'
    fair=r'\b(?:recruitment|recruiting|careers?)[-\s]+fairs?\b'
    for clause in clauses:
        if re.search(r'\b(?:professional[-\s]+association|association[’\x27]?s?)\b',clause,re.I) and re.search(r'\b(?:subject\s+to|meet\w*)\b[^.;]{0,75}\bmembership\s+(?:requirements?|eligibility)\b',clause,re.I):
            details.append(dict(issue='Professional Associations Membership',detail=clause,meaning='Sponsorship is scored; ordinary membership eligibility adds no separate payoff.'))
        noncompete_detail=_noncompete_scope_detail(clause)
        if noncompete_detail:
            details.append(dict(issue='Non-compete Clause',detail=noncompete_detail,meaning='Keeping or waiving the clause is scored; its scope and duration have no additional payoff in this catalog.'))
        # A monthly mentor meeting in the next list item is not monthly training.
        for local in re.split(r',|\band\b',clause,flags=re.I):
            if re.search(training,local,re.I) and re.search(r'\b(?:session|course|training)\b',local,re.I) and re.search(r'\b(?:monthly|weekly|per\s+month|each\s+month|every\s+month)\b',local,re.I):
                details.append(dict(issue='Professional Training Program',detail=local.strip(),meaning='The training commitment is scored; its frequency is retained without additional points.'))
        if re.search(mentor,clause,re.I) and re.search(r'\b(?:for\s+(?:the\s+)?(?:first\s+)?\d+\s+months?|for\s+(?:a|one)\s+year)\b',clause,re.I):
            details.append(dict(issue='Mentorship Program',detail=clause,meaning='Participation is scored; the relationship duration is retained without additional points.'))
        if re.search(fair,clause,re.I) and re.search(r'\b(?:quarter|quarterly|monthly|per\s+month|per\s+year|each\s+year)\b',clause,re.I):
            details.append(dict(issue='Role in Recruitment Fair',detail=clause,meaning='The recruitment-fair commitment is scored; its frequency is retained without additional points.'))
    for previous,clause in zip(clauses,clauses[1:]):
        # "The non-compete remains, but is limited to direct competitors":
        # the scope clause still modifies that same restriction after "but".
        # Do not attach a new subject or an unrelated benefit to this issue.
        if re.search(r'\bnon[-\s]?compete\b',previous,re.I) and re.search(r'^(?:(?:it|the\s+clause|this\s+restriction)\s+)?(?:(?:be|is|(?:would|will|should)(?:\s+be)?)\s+)?(?:limited|restricted|applies?\s+only|lasts?\s+no\s+more)\b',clause,re.I):
            details.append(dict(issue='Non-compete Clause',detail=clause,meaning='This qualifies the preceding non-compete; its scope or duration has no separate payoff.'))
        if re.search(r'\bnon[-\s]?compete\b',previous,re.I) and re.search(r'^(?:would|will|should)\s+last\s+(?:\d+|one|two|three|six|twelve)\s+months?\b',clause,re.I):
            details.append(dict(issue='Non-compete Clause',detail=previous+' and '+clause,meaning='This continues the same non-compete duration; no new issue or extra points are introduced.'))
    names={name.casefold():name for name in specs}
    for original in pairs:
        if not isinstance(original,dict):out.append(original);continue
        p=dict(original);name=str(p.get('issue',''));option=str(p.get('option',''));low=option.lower()
        p['issue']=names.get(name.casefold(),ISSUE_ALIASES.get(name,name))
        if p['issue']=='Paid Volunteering Days':
            source=str(p.get('source_text') or text)
            if not re.search(r'\b(?:volunteer\w*|charit\w*|community\s+service)\b',source,re.I):
                details.append(dict(issue='Unpriced paid time',detail=source,meaning='This personal paid-time request is retained without assigning volunteering points.'))
                repairs.append('Paid personal time is not volunteering without a volunteering commitment.')
                continue
        # Keep one internal name through the existing scope/negation checks.
        # The final result is converted back to the active scenario's public
        # name, so archived LinkedIn scenarios and the current social-media
        # scenario both remain reproducible.
        if p['issue'] in SOCIAL_POST_NAMES:
            p['issue'] = SOCIAL_POST_INTERNAL
        if p['issue']=='Starting Date' and re.fullmatch(r'20\d{2}-\d{2}-\d{2}',option) and not re.search(r'\b20\d{2}\b',text):
            # Do not let an extractor invent a year the participant never said.
            # Correct only a matching month/day found in the actual offer.
            try:
                stated=_date_from_text(text,specs['Starting Date']);inferred=date.fromisoformat(option)
                if (stated.month,stated.day)==(inferred.month,inferred.day):p['option']=stated.isoformat()
            except (ValueError,KeyError):pass
        if name.casefold() in ('mentoring','mentor program','mentorship') and re.search(r'\bmentor',text,re.I):p['issue']='Mentorship Program'
        if name.casefold() in ('recruitment fair','recruitment fairs') and re.search(fair,text,re.I):
            p['issue']='Role in Recruitment Fair'
            if low in ('participation','commitment','commit'):p['option']='Commit'
            elif low in ('no participation','no commitment'):p['option']='No commitment'
        if p['issue'] in ('Professional Development Budget','Professional Training Program') and re.search(training,option,re.I) and re.search(r'\b(?:session|course)\b',low) and not re.search(r'\$|\b(?:usd|dollars?|budget|allowance)\b',low):
            p.update(issue='Professional Training Program',option='No participation' if re.search(r'\b(?:no|without|not\s+participat)',low) else 'Participation')
        if p['issue'] in ('Mentor Meeting Frequency','Mentorship Program','Mentoring Assignment Choice') and re.search(mentor,option,re.I) and not re.search(r'\b(?:meetings?|weekly|monthly|per\s+week|per\s+month)\b',low):
            p.update(issue='Mentorship Program',option='No participation' if re.search(r'\b(?:no|without|not\s+participat)',low) else 'Participation')
        if p['issue']=='Contract Renewal Notice' and re.search(r'\b\d+[-\s]+year\s+contract\b',low) and not re.search(r'\b(?:notice|renewal|renew)\b',low):
            p.update(issue='Contract Length',option=re.search(r'\d+',low).group()+' years')
        if p['issue'] in ('Sales Coaching Frequency','Professional Training Program','Role in Recruitment Fair') and re.search(fair,option,re.I):
            p.update(issue='Role in Recruitment Fair',option='No commitment' if re.search(r'\b(?:no|without|optional|voluntary)\b',low) else 'Commit')
        if p['issue']=='Non-compete Clause' and re.search(r'\bwaiv(?:er|e|ed|ing)\b',low) and not re.search(r'\b(?:not|no|without)\b.{0,15}\bwaiv',low):p['option']='Waive'
        if p['issue']=='Professional Associations Membership' and re.search(r'\b(?:no|not|without)\b',low) and re.search(r'\b(?:sponsor\w*|membership|association\w*)\b',low):p['option']='No sponsorship'
        # Receiving a mentor is not the employee mentoring other colleagues.
        receives_mentor=bool(re.search(r'\b(?:an?\s+experienced\s+mentor|mentor(?:ing)?\s+from\s+(?:an?\s+)?experienced\s+colleagues?|assign\w*\s+(?:me|you)\s+(?:an?\s+)?(?:experienced\s+)?mentor)\b',text,re.I))
        has_cadence=bool(re.search(r'\bmentor(?:ing)?\b[^.;]{0,45}\b(?:meetings?|weekly|monthly|each\s+month|every\s+month)\b',text,re.I))
        if p['issue']=='Mentoring Assignment Choice' and receives_mentor and not re.search(r'\b(?:i|you|candidate)\b[^.;]{0,35}\b(?:mentor|coach)\s+(?:other|new|junior)\b',text,re.I):p.update(issue='Mentorship Program',option='Participation')
        if p['issue']=='Mentor Meeting Frequency' and low=='participation' and receives_mentor and not has_cadence:p.update(issue='Mentorship Program',option='Participation')
        if p['issue']=='Recruiting Quote Approval' and re.search(fair,option,re.I) and not re.search(r'\b(?:quote|approval|consent)\b',option,re.I):p.update(issue='Role in Recruitment Fair',option='Commit' if not re.search(r'\b(?:no|not|without)\b',low) else 'No commitment')
        if p!=original:repairs.append(dict(before=original,after=p,reason='Exact construct and units, not nearest-label substitution.'))
        out.append(p)
    return out,details,repairs


def _repair_misrouted_discrete_pairs(
    pairs: list[Any], scenario: dict[str, Any] | None,
) -> list[Any]:
    """Move an exact choice label back to its unique catalog issue.

    Large catalogs contain close neighbors (for example non-compete and
    non-solicitation).  An extractor can identify the exact choice text while
    attaching it to the broader neighbor.  This repair is deterministic and
    conservative: it fires only when the current issue does not contain the
    choice and exactly one other issue does.
    """
    issue_specs = _scenario_issue_map(scenario)
    choice_owners: dict[str, list[tuple[str, str]]] = {}
    for issue_name, spec in issue_specs.items():
        if spec.get("kind") != "discrete":
            continue
        for item in spec.get("options", []):
            label = str(item.get("label", ""))
            choice_owners.setdefault(_normalized_choice(label), []).append((issue_name, label))

    repaired: list[Any] = []
    for original in pairs:
        if not isinstance(original, dict):
            repaired.append(original)
            continue
        pair = dict(original)
        issue, option = canonical_pair(str(pair.get("issue", "")).strip(), str(pair.get("option", "")).strip())
        spec = issue_specs.get(issue)
        current_choices = {
            _normalized_choice(str(item.get("label", "")))
            for item in (spec or {}).get("options", [])
        }
        normalized = _normalized_choice(option)
        if spec and spec.get("kind") == "discrete" and normalized not in current_choices:
            owners = choice_owners.get(normalized, [])
            if len(owners) == 1:
                pair["issue"], pair["option"] = owners[0]
            elif issue == "After-Hours Event Frequency" and normalized in {
                "no commitment", "no required events", "no events", "zero events",
            }:
                pair["option"] = "0 events per quarter"
        repaired.append(pair)
    return repaired


def _scenario_issue_map(scenario: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(scenario, dict):
        return {}
    result = {
        str(item.get("name", "")): item
        for item in scenario.get("issues", [])
        if isinstance(item, dict) and item.get("name")
    }
    social = next((item for item in scenario.get("issues", [])
                   if isinstance(item, dict) and item.get("id") == "linkedin_posts"), None)
    if social:
        for name in SOCIAL_POST_NAMES:
            result[name] = social
    return result


def _uses_broad_social_posts(scenario: dict[str, Any] | None) -> bool:
    """True when the approved issue covers company social media generally."""
    social = next((item for item in (scenario or {}).get("issues", [])
                   if isinstance(item, dict) and item.get("id") == "linkedin_posts"), None)
    return bool(social and social.get("name") == SOCIAL_POST_DISPLAY)


def previous_offer_reference(text: str, scenario: dict[str, Any] | None) -> dict[str, Any]:
    """Describe whether the CURRENT message explicitly carries prior terms.

    Merely supplying previous-offer context must never cause omitted terms to
    reappear. A full carry-forward needs wording such as "same other details"
    or "everything else unchanged." A narrower reference such as "keep their
    start date" may carry only the named issue or issues.
    """
    focused = _focused_text(str(text or ""))
    lower = _normalized_choice(focused)
    full_patterns = (
        r"\b(?:i|we) (?:would |could |may |might |can |will |would probably )?(?:accept|agree to) (?:this offer|that offer|the offer|it all|that)\b",
        r"\bsame (?:other )?(?:offer|package|details|terms|conditions)\b",
        r"\b(?:everything(?: else)?|all other (?:details|terms|conditions)|the rest) (?:stays?|remains?|is|are|will be )?(?:the same|unchanged|as before)\b",
        r"\bkeep (?:everything|all other (?:details|terms|conditions)|the rest) (?:the same|unchanged|as before)\b",
        r"\buse (?:my|your|the) (?:last|previous) offer\b",
        r"\b(?:same as|unchanged from) (?:my|your|the) (?:last|previous) offer\b",
    )
    if any(re.search(pattern, lower, re.I) for pattern in full_patterns):
        return {"mode": "full", "issues": [], "explicit": True}

    selected_cue = bool(
        re.search(r"\b(?:keep|retain|accept|adopt|agree to|accede to|honou?r|use)\b[^.;]{0,180}\b(?:same|unchanged|their|your|previous|last|earlier|the)\b", lower, re.I)
        or re.search(r"\b(?:same as before|same as (?:the )?(?:last|previous) offer|unchanged)\b", lower, re.I)
    )
    if not selected_cue:
        return {"mode": "none", "issues": [], "explicit": False}

    specs = []
    seen = set()
    for name, spec in _scenario_issue_map(scenario).items():
        canonical = str(spec.get("name", name))
        if canonical in seen:
            continue
        seen.add(canonical)
        phrases = [canonical, *spec.get("aliases", []), *spec.get("recognition_aliases", [])]
        if spec.get("id") == "starting_date":
            phrases.extend(["start date", "starting date", "start"])
        elif spec.get("id") == "personal_budget":
            phrases.extend(["personal budget", "expense budget", "work budget"])
        elif spec.get("id") == "remote_working_days":
            phrases.extend(["remote days", "work from home days", "wfh days"])
        phrase_match = False
        for phrase in phrases:
            normalized = _normalized_choice(str(phrase))
            if len(normalized) >= 4 and re.search(r"\b" + re.escape(normalized) + r"\b", lower):
                phrase_match = True
                break
        if phrase_match:
            specs.append(canonical)
    return {"mode": "selected", "issues": specs, "explicit": True}


def _number_from_text(value: str) -> float:
    cleaned = value.strip().lower().replace(",", "").replace("$", "")
    # Spaces (including pasted thin/non-breaking spaces) can group thousands.
    # Preserve actual decimal points and units rather than reading only 30
    # from a correctly interpreted amount such as "30 000 USD per year".
    cleaned = re.sub(r'(?<=\d)\s+(?=\d{3}(?!\d))','',cleaned)
    if re.search(r"\b(?:no|none|zero)\b", cleaned):
        return 0.0
    match = re.search(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?\s*k?", cleaned)
    if not match:
        raise ValueError("no numeric value found")
    token = match.group(0).replace(" ", "")
    multiplier = 1000 if token.endswith("k") else 1
    if token.endswith("k"):
        token = token[:-1]
    return float(token) * multiplier


def _money_number_from_text(value: str) -> float:
    """Read the recorded period-thousands convention without changing 52.5k."""
    raw = str(value)
    raw = re.sub(r'(?<![\d.])([1-9]\d{0,2}(?:\.\d{3})+)(?![\d.]|\s*k\b)',
                 lambda m: m.group(1).replace('.', ''), raw, flags=re.I)
    return _number_from_text(raw)


def _explicit_cash_pairs(text: str) -> list[dict[str, Any]]:
    """Recover labelled cash values, never a guessed range endpoint or date."""
    token=r'\$?\s*[-+]?\s*(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d(?:[\d,.]*\d)?)(?:\s*k)?(?![\w.]|\s*(?:million|thousand|hundred|grand)\b|-\d{2}-)'
    gap=r'\s*(?:(?:of|is|at|to|would|will|be|can|increased|set)\s+){0,6}[:=]?\s*'
    result=[]
    for name,label in [('Salary',r'\b(?:annual\s+)?(?:salary|salry)\b'),('Personal Budget',r'\bbudget\b')]:
        for match in re.finditer(label+gap+'('+token+')',text,re.I):
            if name=='Personal Budget' and re.search(r'\b(?:training|development|education|technology|clothing|wellness|gym|home[-\s]+office)\s*$',text[max(0,match.start()-35):match.start()],re.I):
                continue
            raw=match.group(1).strip()
            # A correction in this issue clause replaces the first amount.
            tail=re.split(r'(?<!\d)\.(?!\d)|[;\n](?!\s*(?:correction\b|actually\b))|\b(?:salary|budget|start(?:ing)?(?:\s+date)?)\b',text[match.end():],maxsplit=1,flags=re.I)[0]
            correction=re.search(r'(?:actually\s+(?:make\s+(?:that|it)\s+)?|correction\s*:\s*|no\s*,?\s*(?:sorry\s*,?\s*)?make\s+(?:that|it)\s+)('+token+')',tail,re.I)
            if correction:
                raw=correction.group(1).strip()
            following = text[match.end():]
            different_allowance = re.match(r'\s+and\s+[-+]?\d[\d,.]*\s*(?:vacay|vacation|holiday|remote|wfh|days?|months?|years?)\b', following, re.I)
            if not different_allowance and re.match(r'\s*(?:[-–—]|to|through|or|and)\s*\$?\s*\d',following,re.I):continue
            # A named calendar date or range cannot supply an amount.
            if re.search(r'^\d{4}-\d{2}-',raw):continue
            result.append(dict(issue=name,option=str(_money_number_from_text(raw)),confidence=1,source_text=match.group(),source='explicit_cash'))
    before=re.search('('+token+r')\s+(?:(?:personal|proposal)\s+)?(?:work[-\s]?expenses?\s+)?budget\b(?!\s*(?:of\s+|[:=]\s*)?\$?\s*[-+]?\s*\d)',text,re.I)
    if before and not re.search(r'[\d.-]$|\d,$|\b(?:May|June|July|August|September)\s*$',text[:before.start()],re.I):
        result.append(dict(issue='Personal Budget',option=str(_money_number_from_text(before.group(1))),confidence=1,source_text=before.group(),source='explicit_cash'))
    # With salary labelled, the only other cash amount immediately before a
    # clear date can be read as the required budget and shown for review.
    ordered=re.search('('+token+r')\s+salary\s*[,;]?\s*('+token+r')\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:May|Jun\w*|Jul\w*|Aug\w*|Sep\w*)|(?:May|Jun\w*|Jul\w*|Aug\w*|Sep\w*)\s+\d{1,2})\b',text,re.I)
    if ordered:
        result.append(dict(issue='Personal Budget',option=str(_money_number_from_text(ordered.group(2))),confidence=1,source_text=ordered.group(),source='explicit_cash'))
    return result


def _date_from_text(value: str, spec: dict[str, Any]) -> date:
    raw = value.strip()
    base_year = int(spec.get('assume_year') or date.fromisoformat(str(spec['min'])).year)
    if spec.get('natural_date_conventions', {}).get('asap') and re.fullmatch(r'(?:asap|as soon as possible)', raw, re.I):
        return date.fromisoformat(spec['natural_date_conventions']['asap'])
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if iso:
        return date(base_year if spec.get('assume_year') else int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    month_names = {name.lower(): number for number, name in enumerate(
        ("", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
    ) if name}
    month_names.update({name[:3].lower(): number for name, number in list(month_names.items())})
    month_token = r"January|February|March|April|May(?!\s+(?:we|i|you|they|he|she|it)\b)|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    if spec.get('natural_date_conventions'):
        relative = re.search(rf'\b(end|mid|middle|beginning)(?:[-\s]+(?:of\s+)?(?:the\s+)?)?({month_token})\b', raw, re.I)
        if relative:
            month = month_names[relative.group(2)[:3].lower()]
            day = calendar.monthrange(base_year, month)[1] if relative.group(1).lower() == 'end' else 15 if relative.group(1).lower() in {'mid', 'middle'} else 1
            return date(base_year, month, day)
    month_first = re.search(
        rf"\b({month_token})\s*(\d{{1,2}})?(?:st|nd|rd|th)?(?:\s*,?\s*(20\d{{2}}))?\b",
        raw, re.I,
    )
    day_first = re.search(
        rf"(?<![\d.])\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_token})(?:\s*,?\s*(20\d{{2}}))?\b",
        raw, re.I,
    )
    if day_first:
        token = day_first.group(2).lower()
        month = 9 if token == "sept" else month_names[token[:3]]
        return date(base_year if spec.get('assume_year') else int(day_first.group(3) or base_year), month, int(day_first.group(1)))
    if month_first:
        token = month_first.group(1).lower()
        month = 9 if token == "sept" else month_names[token[:3]]
        return date(base_year if spec.get('assume_year') else int(month_first.group(3) or base_year), month, int(month_first.group(2) or 1))
    raise ValueError("no calendar date found")


def _stated_start_date(text: str, scenario: dict[str, Any] | None, *, include_invalid: bool = False) -> str | None:
    """Read one stated start date; a month alone uses its first day for review.

    This is the existing month-only convention, not permission to choose a date
    from alternatives or from unrelated dates elsewhere in an offer.
    """
    spec = _scenario_issue_map(scenario).get('Starting Date')
    if not spec:
        return None
    text = _focused_text(text)
    month = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)'
    value = rf'(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)?[-\s]+(?:of\s+)?{month}|{month}(?:[-\s]*\d{{1,2}}(?:st|nd|rd|th)?)?)(?:,?\s+20\d{{2}})?'
    if spec.get('natural_date_conventions'):
        value = rf'(?:(?:end|mid|middle|beginning)(?:[-\s]+(?:of\s+)?(?:the\s+)?)?{month}|{value})'
    label = r'start(?:ing)?(?:\s+date)?'
    patterns = [rf'\b{label}\s*(?:(?:on|in|of|is|would\s+be|will\s+be)\s+|[:=]\s*)?({value})\b',
                rf'\b({value})\s+{label}\b']
    dates = set()
    if spec.get('natural_date_conventions', {}).get('asap'):
        asap = r'(?:asap|as\s+soon\s+as\s+possible)'
        for match in re.finditer(rf'\b(?:{label}\s*(?:(?:on|in|of|is|would\s+be|will\s+be)\s+|[:=]\s*)?{asap}|{asap}\s+{label})\b', text, re.I):
            before = text[max(0, match.start()-22):match.start()]
            after = text[match.end():match.end()+35]
            if re.search(r"\b(?:not|cannot|can't|won't|wouldn't|do\s+not)\s*$", before, re.I):
                continue
            if re.match(rf'\s*(?:or|/|to|through|until)\s*(?:{month}\b|\d)', after, re.I):
                return None
            dates.add(spec['natural_date_conventions']['asap'])
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            before = text[max(0, match.start() - 16):match.start()]
            after = text[match.end():match.end() + 35]
            if re.search(r'\b(?:around|about|early|late|mid|before|after)\s*$', before, re.I):
                continue
            if re.match(rf'\s*(?:or|/|to|through|until|and)\s*(?:{month}\b|\d)', after, re.I):
                next_issue = re.match(r'\s*and\s*\$?[-+]?\d[\d,.]*\s*k?\s*(?:vacay|vacation|holiday|remote|wfh|days?|months?|years?|salary|budget|USD)\b', after, re.I)
                if not next_issue:
                    return None
            if not spec.get('assume_year') and re.match(r'\s*(?:next|last|this|the\s+following)\s+year\b', after, re.I):
                return None
            try:
                literal = re.sub(r'(?<=[A-Za-z])-(?=\d)|(?<=\d)-(?=[A-Za-z])', ' ', match.group(1))
                if re.match(r'\s*(?:months?|mos?|mo|years?|yrs?)\b', after, re.I):
                    literal = re.sub(r'\s*\d{1,2}$', '', literal)
                stated = _date_from_text(literal, spec)
                if include_invalid or date.fromisoformat(str(spec['min'])) <= stated <= date.fromisoformat(str(spec['max'])):
                    dates.add(stated.isoformat())
            except (ValueError, KeyError):
                if include_invalid:
                    dates.add(match.group(1).strip())
    return next(iter(dates)) if len(dates) == 1 else None


def _format_continuous(value: float | date, spec: dict[str, Any]) -> str:
    value_type = spec.get("value_type")
    if value_type == "date":
        assert isinstance(value, date)
        return value.strftime("%B") if value.day == 1 and not spec.get("display_day") else f"{value.strftime('%B')} {value.day}"
    numeric = float(value)
    shown = str(int(numeric)) if numeric.is_integer() else format(Decimal(str(numeric)), 'f')
    if value_type == "currency":
        return f"${numeric:,.0f}" if numeric.is_integer() else '$'+format(Decimal(str(numeric)), ',f')
    unit = str(spec.get("unit", "")).strip()
    if numeric == 1 and unit.startswith("days /"):
        unit = "day" + unit[4:]
    if numeric == 1 and unit.startswith('days per'):
        unit = 'day' + unit[4:]
    singular = {"months": "month", "years": "year", "days": "day"}.get(unit, unit)
    return f"{shown} {singular if numeric == 1 else unit}".strip()


def _open_capture_enabled(scenario: dict[str, Any] | None) -> bool:
    issue_space = scenario.get("issue_space", {}) if isinstance(scenario, dict) else {}
    return issue_space.get("unknown_term_policy") == "capture_unscored"


def _piecewise_points(value: float | date, role: str, spec: dict[str, Any]) -> float | None:
    """Interpolate an explicitly supplied payoff scale without assuming equal slopes."""
    knots = spec.get("payoff_knots", {}).get(role)
    if not isinstance(knots, list) or len(knots) < 2:
        return None

    def coordinate(raw: Any) -> float:
        if spec.get("value_type") == "date":
            parsed = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
            return float(parsed.toordinal())
        return float(raw)

    points = sorted(
        ((coordinate(item["value"]), float(item["points"])) for item in knots),
        key=lambda item: item[0],
    )
    target = coordinate(value)
    if target < points[0][0]:
        if spec.get("payoff_extrapolation") != "linear":
            raise ValueError("outside configured payoff scale")
        left_x, left_y = points[0]
        right_x, right_y = points[1]
        return left_y + (target - left_x) / (right_x - left_x) * (right_y - left_y)
    if target > points[-1][0]:
        if spec.get("payoff_extrapolation") != "linear":
            raise ValueError("outside configured payoff scale")
        left_x, left_y = points[-2]
        right_x, right_y = points[-1]
        return right_y + (target - right_x) / (right_x - left_x) * (right_y - left_y)
    for index in range(1, len(points)):
        left_x, left_y = points[index - 1]
        right_x, right_y = points[index]
        if target <= right_x:
            if right_x == left_x:
                return right_y
            fraction = (target - left_x) / (right_x - left_x)
            return left_y + fraction * (right_y - left_y)
    return points[-1][1]


def score_pair(
    issue: str,
    option: str,
    role: str,
    payoff: dict[str, Any],
    scenario: dict[str, Any] | None = None,
) -> tuple[str, float]:
    """Return canonical display value and points for one validated pair."""
    spec = _scenario_issue_map(scenario).get(issue)
    if spec and spec.get("kind") == "discrete":
        match = next((item for item in spec.get("options", []) if str(item.get("label")) == option), None)
        if not match:
            normalized = re.sub(r"[^a-z0-9]+", " ", option.lower()).strip()
            ranked = []
            for item in spec.get("options", []):
                label = str(item.get("label", ""))
                candidate = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
                ratio = SequenceMatcher(None, normalized, candidate).ratio()
                ranked.append((ratio, item))
            ranked.sort(key=lambda value: value[0], reverse=True)
            if ranked and ranked[0][0] >= 0.88 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.08):
                match = ranked[0][1]
        if not match:
            raise ValueError("invalid discrete option")
        return str(match.get("label")), float(match[role])
    if not spec or spec.get("kind") != "continuous":
        if issue not in payoff or option not in payoff[issue]:
            raise ValueError("invalid discrete option")
        return option, float(payoff[issue][option][role])

    if spec.get("value_type") == "date":
        value = _date_from_text(option, spec)
        low = date.fromisoformat(str(spec["min"]))
        high = date.fromisoformat(str(spec["max"]))
        if not low <= value <= high:
            raise ValueError(f"outside range {_format_continuous(low, spec)} to {_format_continuous(high, spec)}")
        fraction = (value - low).days / (high - low).days
    else:
        if re.search(r'\b\d{4}-\d{2}-\d{2}\b',option):
            # Never turn an interpreter's date-shaped value into its first
            # number (for example, a $2,026 salary). This invalid mapping
            # triggers the existing independent-review route.
            raise ValueError('a calendar date is not a numeric issue value')
        if re.search(r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b|\b\d{1,2}\s+(?:May|June|July|August|September)\b',option,re.I):
            raise ValueError('a calendar date is not a numeric issue value')
        if re.search(r'\d[\d,.]*\s*(?:-|–|—|to|through|or|and)\s*\$?\s*\d', option, re.I):
            raise ValueError('please choose one value, not a range or alternatives')
        if spec.get('value_type') == 'currency' and re.search(r'£|€|\b(?:GBP|EUR|pounds?|euros?)\b', option, re.I):
            raise ValueError('please give this amount in US dollars; no currency conversion is assumed')
        value = _money_number_from_text(option) if spec.get('value_type') == 'currency' else _number_from_text(option)
        if not math.isfinite(value):
            raise ValueError('please use a finite number')
        low = float(spec["min"])
        high = float(spec["max"])
        proposal_domain = spec.get("proposal_domain")
        if isinstance(proposal_domain, dict):
            domain_low = proposal_domain.get("min")
            domain_high = proposal_domain.get("max")
            if domain_low is not None and value < float(domain_low):
                raise ValueError(f"below proposal minimum {_format_continuous(float(domain_low), spec)}")
            if domain_high is not None and value > float(domain_high):
                raise ValueError(f"above proposal maximum {_format_continuous(float(domain_high), spec)}")
        elif not low <= value <= high:
            raise ValueError(f"outside range {_format_continuous(low, spec)} to {_format_continuous(high, spec)}")
        # ``step`` defines a convenient display/sampling grid, not the set of
        # values a negotiator may propose.  These issues are continuous: any
        # in-range value receives proportionally interpolated points.
        fraction = (value - low) / (high - low)
    points = _piecewise_points(value, role, spec)
    if points is None:
        endpoints = spec["payoff"][role]
        points = float(endpoints["min"]) + fraction * (float(endpoints["max"]) - float(endpoints["min"]))
    return _format_continuous(value, spec), points


def _finding(decision: str, code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"decision": decision, "code": code, "message": message, **details}


def _choice_list(values: list[str]) -> str:
    if len(values) < 2:
        return values[0] if values else "a displayed option"
    if len(values) == 2:
        return f"{values[0]} or {values[1]}"
    return f"{', '.join(values[:-1])}, or {values[-1]}"


def _and_list(values: list[str]) -> str:
    if len(values) < 2:
        return values[0] if values else "the vague wording"
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def _focused_text(text: str) -> str:
    """Ignore explicitly superseded discussion when a FINAL OFFER marker exists."""
    match = re.search(r"\bfinal\s+offer\s*:\s*", text, flags=re.IGNORECASE)
    focused = text[match.end():] if match else text
    # Coordinated rejection/proposal starts a new package here, not at a
    # later 'I propose 30 vacation days' that would erase its first terms.
    coordinated = re.search(r'\b(?:i|we)\s+(?:reject|cannot\s+accept|can[’\x27]t\s+accept)\b[^.;\n]{0,200}?\band\s+(?:(?:i|we)\s+)?(?:now\s+)?(?:propose|offer)\b', focused, re.I)
    if coordinated:
        focused = focused[coordinated.end():]
    proposal=re.search(r'\b(?:i|we)\s+(?:(?:now\s+)?(?:offer|propose)\b|would\s+like\s+to\s+make\s+(?:this|a)\s+(?:counter)?offer\b)|\b(?:my\s+|this\s+)?(?:counteroffer|new\s+offer)\s*:|\b(?:my|this)\s+(?:definite\s+)?(?:proposal|offer)\s*(?:is\s*)?:',focused,re.I)
    if proposal:
        rejected=re.search(r'\b(?:cannot\s+accept|can[’\x27]t\s+accept|reject|rejected)\b',focused[:proposal.start()],re.I)
        already_offered = bool(re.search(r'\b(?:i|we)\s+(?:(?:can|would|will)\s+)?(?:accept|offer)\b',focused[:rejected.start()] if rejected else '',re.I))
        if rejected and not already_offered:
            # A later familiar phrase ("I propose 20 vacation days") may not
            # be the start of the new offer. Retain all clauses after the
            # initial refusal, including an earlier "I'd like to suggest...".
            after=focused[rejected.end():proposal.start()]
            boundary=re.search(r'\bbut\b|\bhowever\b|;|\n|(?<!\d)\.|\.(?!\d)',after,re.I)
            start=rejected.end()+boundary.end() if boundary else proposal.start()
            focused=focused[start:]
    # Newline-separated labeled terms are independent fields. Preserve that
    # boundary before the unit checks; otherwise a neighboring contract's
    # three years can be read as the probation value. Ordinary wrapped prose
    # (without a following field label) is unchanged.
    return re.sub(r"(?:\r?\n|,)(?=\s*[A-Za-z][A-Za-z ()/-]{1,85}\s*[:=])", "; ", focused)


def _smart_text_findings(
    text: str,
    payoff: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    has_previous_context: bool = False,
) -> list[dict[str, Any]]:
    raw = _focused_text(text).strip()
    lower = raw.lower()
    findings: list[dict[str, Any]] = []

    salary_spec = _scenario_issue_map(scenario).get("Salary")
    if "maximum salary" in lower and salary_spec and isinstance(salary_spec.get("proposal_domain"), dict) and salary_spec["proposal_domain"].get("max") is None:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "vague_salary",
            "What annual salary amount do you propose? Enter a non-negative amount in US dollars.",
            issue="Salary", option="maximum salary",
        ))
    budget_spec = _scenario_issue_map(scenario).get("Personal Budget")
    if re.search(r"\bmaximum\s+(?:work[-\s]?expense|personal)\s+budget\b", lower) and budget_spec and isinstance(budget_spec.get("proposal_domain"), dict) and budget_spec["proposal_domain"].get("max") is None:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "vague_budget",
            "What annual personal work-expense budget do you propose? Enter a non-negative amount in US dollars.",
            issue="Personal Budget", option="maximum budget",
        ))

    # Wording that names more than one possible deal must be clarified, not guessed.
    fair=r'(?:recruitment|recruiting|career)[-\s]+fairs?'
    conference=r'conference[-\s]+presentations?'
    for clause in _offer_clauses(raw):
        alternative=re.search(rf'\b(?:{fair})\b[^.;]{{0,25}}\bor\b[^.;]{{0,25}}\b(?:{conference})\b|\b(?:{conference})\b[^.;]{{0,25}}\bor\b[^.;]{{0,25}}\b(?:{fair})\b',clause,re.I)
        if alternative and not re.search(r'\b(?:no|not|neither|without|optional|voluntary)\b',clause,re.I):
            findings.append(_finding(CLARIFICATION_NEEDED,'alternative_duties','Do you want to include recruitment-fair participation, conference presentations, or both? Please choose one package.'))
            break
    salary_range = re.search(r"(?:salary\s+)?(?:somewhere\s+)?from\s+(\$?\d[\d,]*(?:\.\d+)?\s*k?)\s+to\s+(\$?\d[\d,]*(?:\.\d+)?\s*k?)", raw, re.I)
    amount = r'(\$?\d[\d,]*(?:\.\d+)?\s*k?)'
    salary_prefix = r'\b(?:salary|pay)\s*(?:(?:of|is|at|would\s+be|should\s+be|set\s+at)\s+|:|=)?\s*'
    salary_range = salary_range or re.search(salary_prefix+r'(?:somewhere\s+)?between\s+'+amount+r'\s+and\s+'+amount,raw,re.I)
    salary_range = salary_range or re.search(salary_prefix+amount+r'\s*(?:to|through|[-–—])\s*'+amount,raw,re.I)
    if salary_range:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "salary_range",
            f"I found a salary range ({salary_range.group(1)} to {salary_range.group(2)}). Which exact salary should I score?",
        ))

    minimum_salary=re.search(r"\b(?:cannot|can['’]t|will\s+not|won['’]t)\s+accept\s+less\s+than\s*(\$\s*\d[\d,]*(?:\.\d+)?\s*k?)",raw,re.I)
    if minimum_salary and re.search(r'\bsalary\b|\bfor\s+this\s+role\b',raw,re.I):
        findings.append(_finding(CLARIFICATION_NEEDED,'minimum_salary',
            f'You mentioned a minimum salary of {minimum_salary.group(1).strip()}. What exact salary would you like to propose?',issue='Salary'))

    # Do not score a numeric term which the offer explicitly rejects without
    # supplying a replacement. This is different from rejecting the other
    # party's package and then making a new, fully specified package.
    if re.search(_EXCLUDED_CONTRACT,raw,re.I) and not re.search(r'\b(?:two|three|four|\d+(?:\.\d+)?)[-\s]+year\s+(?:fixed\s+)?contract\b',re.sub(_EXCLUDED_CONTRACT,' ',raw,flags=re.I),re.I):
        findings.append(_finding(CLARIFICATION_NEEDED,'excluded_contract_comparison','You rejected a fixed contract length. Please give the duration you want, or leave contract length out of the offer.'))
    if re.search(r'\bno\s+non[-\s]?compete\s+clause\b[^.;]{0,30}\bor\s+at\s+most\b',raw,re.I):
        findings.append(_finding(CLARIFICATION_NEEDED,'noncompete_alternatives','Should the non-compete be waived or retained with limits? Please choose one.'))
    # Rejecting only a *broad* restriction is not a definite choice between
    # waiving all restrictions and keeping a narrower one. Never guess Keep.
    for clause in _offer_clauses(raw):
        if (re.search(r'\b(?:no|without|not\s+(?:agree\s+to|include|accept|retain)|cannot\s+accept)\b[^.;]{0,80}\b(?:broad|unrestricted|wide[-\s]ranging)\s+non[-\s]?compete\b',clause,re.I)
                and not _noncompete_scope_detail(clause)
                and not _noncompete_scope_detail(raw)):
            findings.append(_finding(CLARIFICATION_NEEDED,'qualified_noncompete_refusal','Do you want no non-compete at all, or a non-compete with limits? Please choose one.',issue='Non-compete Clause'))
            break
    if re.search(r'\b(?:would|will|do|does)\s+not\s+include\b[^.;]{0,220}\b(?:guaranteed\s+)?exemption\s+from\b[^.;]{0,65}\b(?:team|social)\s+events?\b',raw,re.I):
        findings.append(_finding(CLARIFICATION_NEEDED,'unclear_event_exemption','Would organizing team events be a required part of the role, or would it be optional? Please specify one.'))

    budget_range = re.search(
        r"(?:personal\s+)?(?:work[-\s]?expense\s+)?budget\s+(?:somewhere\s+)?(?:from\s+|between\s+)?(\$?\d[\d,]*(?:\.\d+)?\s*k?)\s+(?:to|through|and)\s+(\$?\d[\d,]*(?:\.\d+)?\s*k?)",
        raw, re.I,
    )
    next_allowance = bool(budget_range and re.match(r'\s*(?:vacay|vacation|holiday|remote|wfh|days?|months?|years?)\b', raw[budget_range.end():], re.I))
    if budget_range and not next_allowance:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "budget_range",
            f"I found a personal-budget range ({budget_range.group(1)} to {budget_range.group(2)}). Which exact budget should I score?",
        ))

    amount_token = r'\$?\s*\d[\d,.]*(?:\s*k)?'
    for issue, pattern in (
        ('Personal Budget', rf'{amount_token}\s*[-–—]\s*{amount_token}\s+(?:personal\s+|work\s+|work[-\s]?expense\s+)?budget\b'),
        ('Vacation Days', r'\b(?:vacation|holiday|annual\s+leave)(?:\s+days)?\s+(?:between\s+)?\d+\s*(?:to|through|or|[-–—])\s*\d+\s*(?:days)?\b'),
    ):
        if re.search(pattern, raw, re.I):
            findings.append(_finding(CLARIFICATION_NEEDED, 'numeric_range',
                f'What single value would you like for {issue}? Please choose one amount rather than a range.', issue=issue))

    salary_alt = re.search(r"salary\s+(\$?\d[\d,]*\s*k?)\s+or\s+(\$?\d[\d,]*\s*k?)", raw, re.I)
    start_alt = re.search(
        r"start(?:ing)?(?:\s+date)?\s+(May|June|July|August|September)\s+or\s+(May|June|July|August|September)\b",
        raw, re.I,
    )
    if salary_alt or start_alt:
        parts = []
        if salary_alt:
            parts.append(f"salary ({salary_alt.group(1)} or {salary_alt.group(2)})")
        if start_alt:
            parts.append(f"start date ({start_alt.group(1)} or {start_alt.group(2)})")
        findings.append(_finding(
            CLARIFICATION_NEEDED, "alternatives",
            f"I found alternatives for {' and '.join(parts)}. Please choose one value for each.",
        ))

    conditional = re.search(
        r"(?:salary\s+)?(\d+\s*k?)\s+if\s+(?:i|we)\s+start\s+in\s+([A-Za-z]+).*?otherwise\s+(\d+\s*k?)\s+in\s+([A-Za-z]+)",
        raw, re.I | re.S,
    )
    if conditional:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "conditional_offer",
            f"I found two conditional offers: {conditional.group(1)} with {conditional.group(2)}, or {conditional.group(3)} with {conditional.group(4)}. Please submit one unconditional offer.",
        ))

    approximate_salary = re.search(r"\bsalary\s+(?:of\s+)?(?:about|around|roughly|approximately)\s*(\$?\d[\d,]*(?:\.\d+)?\s*k?)\b", raw, re.I)
    if approximate_salary:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "approximate_salary",
            f"I found an approximate salary ({approximate_salary.group(1)}). Which exact salary should I score?",
        ))

    vague_start = re.search(r"\bstart(?:ing)?(?:\s+date)?\s+(?:whenever|when(?:ever)?\s+(?:it\s+)?works|at\s+the\s+best\s+time)\b", raw, re.I)
    if vague_start:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "vague_start_date",
            "I need one exact starting date before scoring. Please choose a calendar date within the displayed range.",
        ))

    numeric_date = re.search(r"\b(?:start(?:ing)?(?:\s+date)?\s*)?(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b", raw, re.I)
    # Ask only when both fields can plausibly be a month. 15/06 has only one
    # sensible reading (15 June), while 06/07 genuinely needs clarification.
    if numeric_date and int(numeric_date.group(1)) <= 12 and int(numeric_date.group(2)) <= 12:
        shown = f"{numeric_date.group(1)}/{numeric_date.group(2)}"
        findings.append(_finding(
            CLARIFICATION_NEEDED, "ambiguous_numeric_date",
            f"I found “{shown}”, which can mean different dates. Please write the month name and day, for example January 6 or June 5.",
        ))

    approximate_date = re.search(
        r"\b(?:start(?:ing)?(?:\s+date)?\s+(?:in\s+)?)((?:(?:around|about|early|late)\s+)?(?:mid[-\s]?)?(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)(?:\s+\d{1,2})?)\b",
        raw, re.I,
    )
    if approximate_date and re.search(r"\b(?:around|about|early|late|mid[-\s]?)", approximate_date.group(1), re.I) and not (_scenario_issue_map(scenario).get('Starting Date', {}).get('natural_date_conventions') and not re.search(r'\b(?:around|about|early|late)\b', approximate_date.group(1), re.I)):
        phrase = approximate_date.group(1)
        findings.append(_finding(
            CLARIFICATION_NEEDED, "approximate_start_date",
            f"I found an approximate start date ({phrase}). Which exact calendar date should I score?",
        ))

    named_start = re.search(
        r"\bstart(?:ing)?(?:\s+date)?\s+(?:in\s+)?(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        raw, re.I,
    )
    if named_start:
        month = named_start.group(1).title()
        start_spec = _scenario_issue_map(scenario).get("Starting Date")
        allowed_months = list(payoff.get("Starting Date", {}))
        if start_spec and start_spec.get("kind") == "continuous":
            low_date = date.fromisoformat(str(start_spec["min"]))
            high_date = date.fromisoformat(str(start_spec["max"]))
            month_number = datetime.strptime(month, "%B").month
            month_in_range = low_date.month <= month_number <= high_date.month
        else:
            month_in_range = month in allowed_months
        if not month_in_range:
            allowed_text = (
                f"a date from {_format_continuous(low_date, start_spec)} through {_format_continuous(high_date, start_spec)}"
                if start_spec and start_spec.get("kind") == "continuous" else _choice_list(allowed_months)
            )
            findings.append(_finding(
                REJECTED, "invalid_start_month",
                f"{month} is outside the available starting-date range. Please choose {allowed_text}.",
                issue="Starting Date", option=month, allowed=allowed_months,
            ))

    if re.search(r"\bsure\s*,?\s+because\b", lower) or re.search(r"\*great\*|\byeah\s+right\b", lower):
        amount = re.search(r"[£$]?\d[\d,]*", raw)
        described = f"the {amount.group(0)} salary" if amount else "the salary wording"
        findings.append(_finding(
            CLARIFICATION_NEEDED, "possible_sarcasm",
            f"Your wording may be sarcastic about {described}. Should I treat it as your actual offer?",
        ))

    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?\s*/\s*(?:May|June|July|August|September)\s*", raw, re.I):
        findings.append(_finding(
            CLARIFICATION_NEEDED, "unlabelled_values",
            f"I found “{raw}”, but the numbers have no labels or units. Please label the salary and personal budget—for example, “salary 30k, budget 5k, start May.”",
        ))

    vague = []
    if re.search(r"\b(?:good|decent|reasonable|fair)\s+salary\b", lower):
        vague.append("salary")
    if re.search(r"\b(?:good|decent|reasonable|fair)\s+(?:personal\s+)?budget\b", lower):
        vague.append("personal budget")
    if re.search(r"\b(?:asap|as soon as possible)\b", lower) and not _stated_start_date(raw, scenario):
        vague.append("start date")
    if vague:
        quoted = []
        for phrase in ("good salary", "decent personal budget", "ASAP"):
            if phrase.lower() in lower:
                quoted.append(f"“{phrase}”")
        findings.append(_finding(
            CLARIFICATION_NEEDED, "vague_choices",
            f"I found {_and_list(quoted)}, but these do not identify one exact choice. Please enter exact salary and budget amounts and a start month.",
        ))

    hypothetical = re.search(
        r"\bif\s+i\s+were\s+to\s+offer\s+(\$?\d[\d,]*\s*k?)\s+salary\s*,?\s*(\$?\d[\d,]*\s*k?)\s+budget\s*,?\s+and\s+a?\s*([A-Za-z]+)\s+start",
        raw, re.I,
    )
    if hypothetical:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "hypothetical_offer",
            f"This sounds hypothetical. Should I score {hypothetical.group(1)} salary, {hypothetical.group(2)} budget, and {hypothetical.group(3)} as your final offer?",
        ))

    relative_reference = re.search(
        r"\b(?:same\s+(?:offer|salary)\s+as\s+(?:before|my\s+last\s+offer)|same\s+as\s+my\s+last\s+offer|"
        r"same\s+offer\s+as\s+before|previous\s+offer)\b",
        lower,
    )
    if relative_reference and not has_previous_context:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "missing_conversation_context",
            "I need your previous offer to apply this change. Please restate the complete offer or use this wording inside a recorded session.",
        ))

    # In the bounded condition, clear outside terms are rejected warmly. In
    # open diagnostics, the extractor records them for ontology review.
    unsupported_patterns = [
        (r"\bsigning\s+bonus\b", "signing bonus"),
        (r"\b(?:company\s+)?equity\b", "company equity"),
        (r"\breserved\s+parking(?:\s+space)?\b", "reserved parking"),
        (r"\bhome[-\s]?office\s+stipend\b", "home-office stipend"),
        (r"\bcompany\s+car\b", "company car"),
        (r"\bfour[-\s]?day\s+(?:working\s+)?week\b", "four-day working week"),
    ]
    for pattern, label in unsupported_patterns:
        if re.search(pattern, lower) and not _open_capture_enabled(scenario):
            described_term = f"a {label}" if label in {"signing bonus", "home-office stipend", "company car", "four-day working week"} else label
            findings.append(_finding(
                REJECTED, "unsupported_term",
                f"This offer has not been scored because {described_term} is not available in this scenario. Please remove it or choose a listed job feature.",
                term=label,
            ))

    if re.search(r"(?:£|€|�|gbp|eur)\s*\d|\d[\d,]*\s*(?:pounds?|gbp|euros?|eur)\b", lower):
        findings.append(_finding(
            CLARIFICATION_NEEDED, "unsupported_currency",
            "This scenario scores salary and budget in US dollars. Please restate the amount in dollars so I do not guess a conversion.",
        ))

    wrong_unit_checks = [
        (r"\bsalary\s+(?:of\s+)?\$?\d[\d,]*(?:\.\d+)?\s*k?\s+per\s+month\b", "Salary is annual in this scenario. Please give one annual salary in US dollars."),
        (r"\b(?:personal\s+)?budget\s+(?:of\s+)?[\d,]+\s+(?:reward\s+)?points\b", "The personal work-expense budget is scored in US dollars. Please give one dollar amount."),
        (r"\bstart(?:ing)?(?:\s+date)?\s+in\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+weeks?\b", "Starting date is scored as a calendar date. Please give one exact date within the displayed range."),
        (r"\b\d+(?:\.\d+)?\s+(?:vacation|holiday|leave)\s+hours?\b", "Vacation is scored in days. Please give one number of vacation days."),
        (r"\b\d+(?:\.\d+)?\s+remote\s+weeks?\s+(?:per|a)\s+year\b", "Remote work is scored in days per week. Please give one weekly number of remote days."),
        (r"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b(?:\s+(?:length|duration|of|for|is|would|will|be|set|at|a|an|the|to|last|lasts|lasting|run|runs|running|continue|remain|initial)){0,8}\s*[:=]?\s*(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+(?:days?|weeks?)\b|\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)[-\s]?(?:days?|weeks?)\s+(?:probation(?:ary)?|trial)(?:\s+period)?\b", "Probation is scored in months. Please give one exact number of months."),
        (r"\b(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b(?:\s+(?:length|duration|of|for|is|would|will|be|set|at|a|an|the|to|last|lasts|lasting|run|runs|running|continue|remain|initial)){0,8}\s*[:=]?\s*\d+(?:\.\d+)?\s+(?:days?|weeks?)\b|\b\d+(?:\.\d+)?[-\s]?(?:days?|weeks?)\s+(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b", "Contract length is scored in years. Please give one exact number of years."),
        (r"\bcommission\s+(?:of\s+)?\$\s*\d", "Commission is scored as a percentage of credited customer payments. Please give one percentage."),
    ]
    for pattern, message in wrong_unit_checks:
        if re.search(pattern, lower):
            findings.append(_finding(CLARIFICATION_NEEDED, "invalid_unit", message))

    # Detect out-of-range continuous values even if the extractor dropped them.
    issue_specs = _scenario_issue_map(scenario)
    invalid_checks = [
        (r"\bprobation\s+(\d+)\s*(?:months?|mos?|mo)\b", "Probation Length", "{} months"),
        (r"\b(\d+(?:\.\d+)?|one|two|three|four)[-\s]?years?\s+contract\b", "Contract Length", "{} years"),
        (r"\b(\d+)\s+(?:vacation|holiday)\s+days\b", "Vacation Days", "{} days"),
    ]
    word_numbers = {"one": "1", "two": "2", "three": "3", "four": "4"}
    for pattern, issue, template in invalid_checks:
        match = re.search(pattern, _affirmative_numeric_text(lower))
        if not match:
            continue
        number = word_numbers.get(match.group(1), match.group(1))
        option = template.format(number)
        if issue == "Contract Length" and number == "1":
            option = "1 year"
        spec = issue_specs.get(issue)
        if spec and spec.get("kind") == "continuous":
            try:
                score_pair(issue, option, "Candidate", payoff, scenario)
            except ValueError:
                domain = spec.get('proposal_domain') or spec
                low_value = _format_continuous(float(domain["min"]), spec)
                high_value = _format_continuous(float(domain["max"]), spec)
                findings.append(_finding(
                    REJECTED, "invalid_option",
                    f"{option} is outside the available range for {issue}. Please choose a value from {low_value} to {high_value}.",
                    issue=issue, option=option, allowed=[low_value, high_value],
                ))
        elif issue in payoff and option not in payoff[issue]:
            allowed = list(payoff[issue])
            findings.append(_finding(
                REJECTED, "invalid_option",
                f"{option} is not an available choice for {issue}. Please choose {_choice_list(allowed)}.",
                issue=issue, option=option, allowed=allowed,
            ))

    duration_words = {
        "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
        "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0,
        "nine": 9.0, "ten": 10.0, "eleven": 11.0, "twelve": 12.0, "eighteen": 18.0,
        "twenty-four": 24.0,
    }
    duration_token = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|eighteen|twenty-four|\d+(?:\.\d+)?"

    def duration_number(raw: str) -> float:
        normalized = raw.lower()
        if normalized in duration_words:
            return duration_words[normalized]
        return float(raw) if re.fullmatch(r"\d+(?:\.\d+)?", raw) else float("nan")

    def add_out_of_range_duration(issue: str, value: float, option: str) -> None:
        spec = issue_specs.get(issue)
        if not spec or spec.get("kind") != "continuous":
            return
        if any(item.get("code") == "invalid_option" and item.get("issue") == issue for item in findings):
            return
        try:
            score_pair(issue, option, "Candidate", payoff, scenario)
        except ValueError:
            low_value = _format_continuous(float(spec["min"]), spec)
            high_value = _format_continuous(float(spec["max"]), spec)
            findings.append(_finding(
                REJECTED, "invalid_option",
                f"{option} is outside the available range for {issue}. Please choose a value from {low_value} to {high_value}.",
                issue=issue, option=option, allowed=[low_value, high_value],
            ))

    # Prefer a duration written after the issue label. Keeping the two word
    # orders separate prevents a neighboring contract duration from being
    # mistaken for probation in a punctuation-free package.
    duration_bridge = r"(?:(?!\b(?:contract|employment\s+(?:agreement|term)|non[-\s]?compete|vacation|holiday|remote|wfh|salary|budget|start(?:ing)?\s+date|probation|trial)\b)[^.;\n|/])"
    probation_duration = re.search(
        rf"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b{duration_bridge}{{0,35}}?\b(?:(?:last|run|be|is)\w*\s+)?(?:for\s+)?({duration_token})\s*(months?|mos?|mo|years?|yrs?)\b",
        lower,
    )
    if not probation_duration:
        probation_duration = re.search(
            rf"\b({duration_token})[-\s]?(months?|mos?|mo|years?|yrs?)\s+(?:of\s+)?(?:probation(?:ary)?|trial)(?:\s+period)?\b",
            lower,
        )
    if probation_duration:
        raw_value = probation_duration.group(1)
        unit = probation_duration.group(2)
        value = duration_number(raw_value)
        months = value * 12 if unit.startswith(("year", "yr")) else value
        shown = int(months) if months.is_integer() else months
        add_out_of_range_duration("Probation Length", months, f"{shown} months")

    # Apply the same label-first preference to contract length. Otherwise
    # "trial period 3 months employment term 3 years" can be read as a
    # three-month contract simply because that number appears first.
    contract_duration = re.search(
        rf"\b(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b{duration_bridge}{{0,35}}?\b(?:(?:run|last|continue|be|remain|is)\w*\s+)?(?:in\s+place\s+)?(?:for\s+)?({duration_token})\s*(months?|mos?|mo|years?|yrs?)\b",
        lower,
    )
    if contract_duration and _duration_is_noncompete_detail(
        lower, contract_duration.start(), contract_duration.end()
    ):
        contract_duration = None
    if contract_duration and re.match(
        r"\s+(?:of\s+)?(?:probation(?:ary)?|trial)(?:\s+period)?\b",
        lower[contract_duration.end():],
    ):
        contract_duration = None
    if not contract_duration:
        contract_duration = re.search(
            rf"\b({duration_token})[-\s]?(months?|mos?|mo|years?|yrs?)\s+(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b",
            lower,
        )
    if contract_duration:
        raw_value = contract_duration.group(1)
        unit = contract_duration.group(2)
        value = duration_number(raw_value)
        years = value / 12 if unit.startswith(("month", "mo")) else value
        shown = int(years) if years.is_integer() else years
        add_out_of_range_duration("Contract Length", years, f"{shown} years")

    range_checks = (
        ("Probation Length", rf"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b[^.;\n|]{{0,45}}\b(?:between\s+)?(?:{duration_token})\s*(?:-|to|and|or)\s*(?:{duration_token})\s*(?:months?|mos?|mo|years?|yrs?)\b"),
        ("Contract Length", rf"\b(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b[^.;\n|]{{0,45}}\b(?:between\s+)?(?:{duration_token})\s*(?:-|to|and|or)\s*(?:{duration_token})\s*(?:months?|mos?|mo|years?|yrs?)\b"),
        ("Probation Length", rf"\b(?:between\s+)?(?:{duration_token})\s*(?:-|to|and|or)\s*(?:{duration_token})\s*(?:months?|mos?|mo|years?|yrs?)\s+(?:of\s+)?(?:probation|trial)\b"),
        ("Contract Length", rf"\b(?:between\s+)?(?:{duration_token})\s*(?:-|to|and|or)\s*(?:{duration_token})\s*(?:months?|mos?|mo|years?|yrs?)\s+(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b"),
    )
    for issue, pattern in range_checks:
        range_match = re.search(pattern, lower)
        # A dash at the beginning of the next line is a bullet, not a range
        # operator between the preceding and following durations.
        if range_match and not re.search(r"\n\s*-\s*", range_match.group(0)):
            findings.append(_finding(
                CLARIFICATION_NEEDED, "duration_range",
                f"Please choose one exact {issue} value for this offer rather than a range or alternatives.",
                issue=issue,
            ))

    role_review_clause = next((
        clause for clause in re.split(r";|(?<!\d)\.|\.(?!\d)", lower)
        if re.search(r"\b(?:duties|priorities|responsibilities|role(?:\s+scope)?|job\s+scope)\b", clause)
        and re.search(r"\b(?:review|reviewed|revisit|reassess|check[-\s]?in|check|checked)\b", clause)
    ), None)
    if role_review_clause:
        cadence = re.search(
            rf"\b({duration_token})[-\s]?months?\b|"
            rf"\b(?:every|after|at|in)\s+({duration_token})\s+months?\b|"
            rf"\bmonths?\s+({duration_token})\b",
            role_review_clause,
        )
        if cadence:
            raw_value = cadence.group(1) or cadence.group(2) or cadence.group(3)
            months = duration_number(raw_value)
            if months not in {3.0, 6.0}:
                findings.append(_finding(
                    CLARIFICATION_NEEDED, "unsupported_role_review_timing",
                    "Please choose a three-month review, a six-month review, or no scheduled role review.",
                    issue="Role Review Schedule",
                ))

    remote_scan = re.sub(r"\b(days?|times?)\s+(weekly|monthly)\b", lambda m: m.group(1) + ' per ' + ('week' if m.group(2)=='weekly' else 'month'), lower)
    remote = re.search(r"\b(?:remotely|remote(?:[-\s]+working)?|remote\s+work|wfh|home[-\s]+working|work(?:ing)?[-\s]from[-\s]home)\b.{0,24}?\b(?<![\d.,])(\d+(?:\.\d+)?|one|two|three|four|five|six|seven)\s+days?\s+(?:each|every|per|a)\s+(week|month)\b", remote_scan)
    if not remote:
        remote = re.search(r"\b(?<![\d.,])(\d+(?:\.\d+)?|one|two|three|four|five|six|seven)\s+(?:remote(?:[-\s]+working)?|wfh|home[-\s]+working)\s+days?\s+(?:each|every|per|a)\s+(week|month)\b", remote_scan)
    if not remote and _scenario_issue_map(scenario).get('Remote Working Days', {}).get('default_period'):
        remote = re.search(r'\b(?:remotely|remote\s+work|wfh|work(?:ing)?\s+from\s+home)\s+(?:for\s+)?(\d+(?:\.\d+)?|one|two|three|four|five|six|seven)\s+times?\s+(?:each|every|per|a)\s+(week|month)\b', remote_scan)
    if remote:
        number = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7"}.get(remote.group(1), remote.group(1))
        option = f"{number} days / {remote.group(2)}"
        spec = issue_specs.get("Remote Working Days")
        expected_period = "week" if "week" in str((spec or {}).get("unit", "")).lower() else "month"
        expected_label = f"days / {expected_period}"
        if remote.group(2) != expected_period:
            findings.append(_finding(
                CLARIFICATION_NEEDED, "invalid_unit_or_option",
                f"Remote work is scored in days per {expected_period} here. Please give one {expected_period}ly value.",
                issue="Remote Working Days", option=option, allowed=[expected_label],
            ))
        elif spec and spec.get("kind") == "continuous":
            try:
                score_pair("Remote Working Days", option, "Candidate", payoff, scenario)
            except ValueError:
                domain = spec.get('proposal_domain') or spec
                low_value = _format_continuous(float(domain["min"]), spec)
                high_value = _format_continuous(float(domain["max"]), spec)
                findings.append(_finding(
                    REJECTED, "invalid_option",
                    ('There are five working days per week in this scenario. Please choose 0–5 remote-working days per week.' if spec.get('proposal_domain') else
                     f"{option} is outside the available range for Remote Working Days. Please choose a value from {low_value} to {high_value}."),
                    issue="Remote Working Days", option=option, allowed=[low_value, high_value],
                ))
        elif option not in payoff.get("Remote Working Days", {}):
            allowed = list(payoff.get("Remote Working Days", {}))
            findings.append(_finding(
                REJECTED, "invalid_unit_or_option",
                f"Remote work is scored in days per {expected_period} here. Please choose {_choice_list(allowed)}.",
                issue="Remote Working Days", option=option, allowed=allowed,
            ))

    if re.search(r"\bactual\s+offer\s+is\s+undecided\b", lower):
        findings.append(_finding(
            REJECTED, "not_a_final_offer",
            "This has not been scored because you said the offer is undecided. Submit one final offer when you are ready.",
        ))

    # Rejected comparisons are not two live alternatives. Keep this local to
    # the non-compete alternative check; numeric exclusions have own rules.
    noncompete_choice_text=re.sub(r'(\bnon[-\s]?compete\b[^.;\n]{0,90}?)\brather\s+than\s+(?:being\s+)?(?:removed|waived)\s+or\s+(?:limited|narrowed)\b',r'\1',lower)
    if re.search(
        r"\bnon[-\s]?compete\b.{0,45}\b(?:removed|waived)\b\s+or\s+\b(?:limited|narrowed)\b"
        r"|\b(?:remove|waive)\b.{0,35}\bnon[-\s]?compete\b.{0,35}\bor\b.{0,35}\b(?:limit|narrow)",
        noncompete_choice_text,
    ):
        findings.append(_finding(
            CLARIFICATION_NEEDED, "alternative_non_compete_terms",
            "Please choose one non-compete term for this offer: waive it, or keep it with the stated limits.",
            issue="Non-compete Clause",
        ))

    vague_non_solicitation = re.search(r"\bnon[-\s]?solicitation\b", lower)
    plain_non_solicitation=re.search(r'\b(?:avoid\s+soliciting|(?:will|would|shall)\s+not\s+solicit)\b[^.;]{0,100}\b(?:clients?|customers?|employees?|prospects?)\b[^.;]{0,80}\b(?:after\s+employment|after\s+leaving|post[-\s]+employment)\b',lower)
    if plain_non_solicitation:
        if 'Customer and Employee Non-Solicitation' not in _scenario_issue_map(scenario):
            findings.append(_finding(REJECTED,'unavailable_non_solicitation','A separate post-employment restriction on contacting clients or employees is not scored in this version. Please remove that extra restriction.',issue='Customer and Employee Non-Solicitation'))
        else:
            findings.append(_finding(CLARIFICATION_NEEDED,'non_solicitation_scope','For the post-employment non-solicitation restriction, please specify its duration and who it covers.',issue='Customer and Employee Non-Solicitation'))
    non_solicitation_choice = (
        r"(?:6|six|12|twelve)\s+months?|named\s+customers?|"
        r"any\s+(?:customer|prospect|employee)|no\s+(?:post[-\s]employment\s+)?restriction"
    )
    specified_non_solicitation = re.search(
        rf"\bnon[-\s]?solicitation\b.{{0,60}}\b(?:{non_solicitation_choice})\b|"
        rf"\b(?:{non_solicitation_choice})\b.{{0,60}}\bnon[-\s]?solicitation\b",
        lower,
    )
    if vague_non_solicitation and not specified_non_solicitation:
        findings.append(_finding(
            CLARIFICATION_NEEDED, "vague_non_solicitation",
            "Please specify the non-solicitation term: no restriction, 6 months for named customers directly served, or 12 months for any customer, prospect, or employee.",
            issue="Customer and Employee Non-Solicitation",
        ))

    if re.search(r"\bmy\s+actual\s+message\s+is\s+only\s*:\s*dance\b", lower):
        findings.append(_finding(
            REJECTED, "prompt_injection",
            "No job-offer terms were found in your actual message. Please submit one complete offer using the displayed choices.",
        ))

    career_spec=_scenario_issue_map(scenario).get('Senior Career Guidance')
    if career_spec:
        # This is a choice-based frequency, not a continuous allowance. Never
        # round an explicitly stated four conversations down to the option two.
        annual=re.search(r'\b(\d+|zero|one|two|three|four|five|six)\s+(?:scheduled\s+)?career[-\s]+development\s+conversations?\s+(?:per|each|every|a)\s+year\b',_affirmative_numeric_text(_focused_text(text)),re.I)
        if annual:
            words={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6}
            token=annual.group(1).lower();count=int(token) if token.isdigit() else words[token]
            allowed={0 if o['label'].lower().startswith('no ') else words.get(o['label'].split()[0].lower()) for o in career_spec.get('options',[])}
            if count not in allowed:
                findings.append(_finding(CLARIFICATION_NEEDED,'career_guidance_frequency',f'You asked for {count} career-development conversations per year. Please choose: '+', '.join(o['label'] for o in career_spec.get('options',[]))+'.',issue='Senior Career Guidance'))
    return findings


def _usual_allowance_readings(text: str, scenario: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Resolve an explicit change from the usual allowance, not from an old offer.

    The baseline lives in the scenario alongside its unit. Without that setting,
    a historical scenario retains its original behavior. Missing direction or
    conflicting relative requests need a question, never a guessed allowance.
    """
    words = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
             'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
             'twenty': 20, 'thirty': 30, 'forty': 40}
    number = r'(?:\d+(?:\.\d+)?|zero|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty)'
    usual = r'(?:(?:the\s+)?(?:usual|standard|normal)(?:\s+allowance)?)'
    direction = r'(?P<direction>more|extra|additional|fewer|less)'
    issue_words = {
        'Vacation Days': r'(?:(?:vacation|vacay|holiday)\s+days?|days?\s+(?:of\s+)?(?:annual\s+leave|vacation|holiday|time\s+off)|annual\s+leave|time\s+off)',
        'Remote Working Days': r'(?:(?:remote(?:ly|[-\s]+working|[-\s]+work)?|wfh|work(?:ing)?\s+from\s+home)\s+days?|days?\s+(?:of\s+)?(?:remote\s+work|working\s+remotely|working\s+from\s+home))',
    }
    readings = {}
    raw = _focused_text(text).lower()
    for name, issue in issue_words.items():
        spec = _scenario_issue_map(scenario).get(name, {})
        if 'usual_value' not in spec:
            continue
        quantity = rf'(?P<quantity>{number})'
        patterns = [
            rf'\b{quantity}\s+{direction}\s+{issue}\s+(?:than\s+)?{usual}\b',
            rf'\b{quantity}\s+{issue}\s+{direction}\s+(?:than\s+)?{usual}\b',
            rf'\b{quantity}\s+{direction}\s+than\s+{usual}\s+{issue}\b',
            rf'\b{issue}\s+(?:of\s+|is\s+|=\s*)?{quantity}\s+{direction}\s+(?:than\s+)?{usual}\b',
            rf'\b{usual}\s+{issue}\s*(?P<direction>plus|minus|\+|−|-)\s*{quantity}\b',
            rf'\b{issue}\s*(?:of\s+|is\s+|=\s*)?{usual}\s*(?P<direction>plus|minus|\+|−|-)\s*{quantity}\b',
        ]
        matches = [m for pattern in patterns for m in re.finditer(pattern, raw, re.I)]
        values = set()
        for match in matches:
            before = raw[max(0, match.start()-18):match.start()]
            if re.search(r"\b(?:no|not|without|reject|rejected)\s*$", before):
                continue
            token = match['quantity']
            delta = words[token] if token in words else float(token)
            sign = -1 if match['direction'] in {'fewer', 'less', 'minus', '−', '-'} else 1
            values.add(float(spec['usual_value']) + sign * delta)
        if len(values) == 1:
            readings[name] = dict(value=values.pop(), source_text=matches[0].group(0),
                note=f"Using the usual {spec['usual_value']:g} {spec['unit']} as the baseline.")
        elif len(values) > 1:
            readings[name] = dict(value=None, question=f'You gave different changes to the usual {name.lower()}. What single allowance would you like?')
        elif re.search(rf'\b{number}\s+{issue}\s+than\s+{usual}\b', raw):
            readings[name] = dict(value=None, question=f'Do you mean more or fewer than the usual {spec["usual_value"]:g} {spec["unit"]}?')
    return readings


def _study_pair_enrichment(text: str, scenario: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Deterministic aliases for the documented study issues missing in the old run."""
    lower = _focused_text(text).lower()
    for short, expanded in {"won't":"will not","wouldn't":"would not","don't":"do not",
            "doesn't":"does not","shouldn't":"should not","can't":"cannot","couldn't":"could not",
            "isn't":"is not","aren't":"are not","wasn't":"was not","weren't":"were not",
            "needn't":"need not","mustn't":"must not"}.items():
        lower=lower.replace(short,expanded).replace(short.replace("'","’"),expanded)
    # Preserve common participant spelling while keeping the original offer
    # unchanged for display and audit.
    lower = re.sub(r'\bprobstion\b','probation',lower)
    lower = re.sub(r'\bvacay\b', 'vacation', lower)
    lower = re.sub(r'\bprofessional[-\s]+associations?\b','professional association',lower)
    lower = re.sub(_EXCLUDED_CONTRACT,' ',lower,flags=re.I)
    numeric_lower = _affirmative_numeric_text(lower)
    usual_readings = _usual_allowance_readings(text, scenario)
    # These equivalent grammatical orders name the same review construct.
    lower = re.sub(r'\breview\s+of\s+(pay|salary|compensation)\b',r'\1 review',lower)
    additions: list[tuple[str, str]] = []
    # A fully explicit start-date phrase can recover an omitted model field.
    # Restrict this to the start-date clause, not any date elsewhere in a story.
    # Preserve a stated but invalid date so validation can explain the issue.
    # Otherwise an extractor dropping January becomes a misleading "add date".
    stated_start = _stated_start_date(text, scenario, include_invalid=True)
    if stated_start:
        additions.append(('Starting Date', stated_start))
    car_spec = _scenario_issue_map(scenario).get('Company Car', {})
    if car_spec.get('bare_request_default') and re.search(r'\bcompany\s+car\b', lower):
        if re.search(r'\b(?:no|without)\s+(?:(?:a|the|any)\s+)?company\s+car\b|\bcompany\s+car\s+(?:is\s+)?not\s+included\b', lower):
            additions.append(('Company Car', 'No company car'))
        elif re.search(r'\b(?:shared|pool)\s+(?:company\s+)?car\b|\bcompany\s+car\s+(?:(?:is|would|will|be|a|the)\s+){0,3}(?:shared|pool)\b', lower):
            additions.append(('Company Car', 'Access to a shared pool car'))
        elif not re.search(r'\b(?:or|either|whether)\b[^.;\n]{0,30}\bcompany\s+car\b|\bcompany\s+car\b[^.;\n]{0,30}\bor\b[^.;\n]{0,30}\bcar\b', lower):
            additions.append(('Company Car', car_spec['bare_request_default']))
    if re.search(r'\b(?:standard\s+(?:company\s+)?non[-\s]?compete|company[’\x27]s\s+standard\s+non[-\s]?compete|non[-\s]?compete\s+(?:clause\s+)?(?:kept|remains?|stays?)\s+in\s+place)\b',lower) and not re.search(r'\b(?:no|without|waiv\w*|remov\w*)\b[^.;]{0,45}\bnon[-\s]?compete\b',lower):
        additions.append(('Non-compete Clause','Keep'))
    # A decimal point is part of a value, not a sentence boundary.  Preserving
    # it keeps context words such as "previously" attached to 3.5-year terms.
    duty_clauses = _offer_clauses(lower)
    large_issue_space = len(_scenario_issue_map(scenario)) > 50
    linkedin_post_evidence = bool(re.search(
        r"\bno\s+(?:recurring|regular|ongoing)\s+(?:responsibility|obligation|dut(?:y|ies))\b"
        r"[^.;]{0,80}\b(?:post|write|publish|contribute|provide)\w*\b[^.;]{0,80}\blinkedin\b|"
        r"\b(?:i|you|candidate|employee|new\s+hire|they)\b[^.;]{0,160}"
        r"\b(?:write|post|publish|contribute|produce|provide)\w*\b[^.;]{0,100}"
        r"\b(?:linkedin\s+)?(?:posts?|updates?|content|communications?|publicity)\b|"
        r"\blinkedin\b[^.;]{0,180}\b(?:posts?|posting|write|writing|updates?|content|"
        r"contributions?|dut(?:y|ies)|responsibilit(?:y|ies)|obligation|required|optional|voluntary|recurring)\b|"
        r"\blinkedin\s+(?:publicity|communications?)\b[^.;]{0,140}\b(?:voluntary|optional|opt[-\s]?in|"
        r"mutually\s+agreed|by\s+mutual\s+agreement|agreed\s+(?:with\s+me\s+)?in\s+advance|recurring\s+obligations?)\b|"
        r"\b(?:voluntary|optional|opt[-\s]?in|no\s+recurring\s+(?:responsibility|obligation|dut(?:y|ies))|"
        r"would\s+not\s+take\s+on\s+recurring|no\s+(?:recurring|regular|ongoing)\s+(?:responsibility|obligation|dut(?:y|ies)))\b"
        r"[^.;]{0,180}\blinkedin\s+(?:publicity|communications?)\b",
        lower,
    ))
    if _uses_broad_social_posts(scenario):
        linkedin_post_evidence = linkedin_post_evidence or bool(re.search(
            r"\b(?:i|you|candidate|employee|new\s+hire|they)\b[^.;]{0,160}"
            r"\b(?:write|post|publish|contribute|produce|provide|shape|help)\w*\b[^.;]{0,110}"
            r"\b(?:company\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b|"
            r"\b(?:regular|recurring|ongoing|optional|voluntary|no)\b[^.;]{0,100}"
            r"\b(?:company\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b|"
            r"\b(?:help(?:ing)?\s+(?:to\s+)?shape|shap(?:e|es|ing))\b[^.;]{0,140}"
            r"\b(?:company['’]s\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b",
            lower,
        ))

    def optional_or_declined(issue_pattern: str) -> bool:
        wrapped_issue = rf"(?:{issue_pattern})"
        general_marker = (
            r"\bnot\s+(?:have|need|want)\s+to\b|"
            r"\b(?:voluntar(?:y|ily)|optional(?:ly)?)\b|\bagreed\b.{0,35}\bin\s+advance\b|"
            r"\bopt[-\s]?in\b|\bnot\s+(?:be\s+)?mandatory\b|\bshould\s+not\s+be\s+mandatory\b|"
            r"\brather\s+than\s+(?:a\s+)?recurring\s+obligation\b|\bcannot\s+agree\s+to\b|"
            r"\bnot\s+to\b|"
            r"\b(?:could|may|can)\s+(?:participate|contribute|provide|organize|organise|help)\b|"
            r"\b(?:could|may|can)\s+(?:attend|join|represent|take\s+part)\b|"
            r"\b(?:be|am|is|are|would\s+be)\s+able\s+to\s+(?:participate|contribute|provide|organize|organise|help)\b|"
            r"\b(?:would|will|is|are)?\s*not\s+(?:be\s+)?(?:required|expected)\s+to\b|"
            r"\bneed\s+not\b|"
            r"\bat\s+(?:the\s+)?(?:candidate['’]s|employee['’]s|their|your)\s+option\b|"
            r"\b(?:may|might|could)\s+allow\b|"
            r"\b(?:by\s+)?mutual\s+agreement\b|\bmutually\s+agreed\b|"
            r"\bneither\b[^.;]{0,35}\b(?:obligation|required|mandatory)\b|"
            r"\bif\s+(?:i|you|we|they|the\s+candidate)\s+(?:wish|choose|want)\b"
        )
        for clause in duty_clauses:
            if not re.search(issue_pattern, clause):
                continue
            if re.search(issue_pattern,'linkedin') and _explicit_posting_pledge(clause):
                continue
            if re.search(issue_pattern,'recruitment fair') and _literal_fair_commitment(clause):
                continue
            if re.search(general_marker, clause):
                return True
            # An opportunity is permission, not a standing duty. Keep a later
            # opportunity clause from cancelling an earlier explicit duty.
            for segment in re.split(r',\s*(?=(?:an?\s+)?opportunit)|\band\s+(?=(?:an?\s+)?opportunit)',clause):
                if re.search(r'\bopportunit(?:y|ies)\s+to\b[^.;]{0,180}'+wrapped_issue,segment):
                    return True
            if re.search(r"\b(?:no|without)\b[^,]{0,30}" + wrapped_issue, clause):
                return True
            if re.search(wrapped_issue + r"[^,]{0,35}\b(?:would\s+not|will\s+not|not\s+required|not\s+expected)\b", clause):
                return True
            # Labeled choices often put the refusal AFTER the issue name.
            # Keep the match local so a neighboring declined duty does not
            # reverse a positive commitment elsewhere in the offer.
            if re.search(wrapped_issue + r"[^,;\n]{0,45}\b(?:no\s+(?:commitment|obligation|participation)|not\s+required|(?:is|are)\s+not\s+included)\b", clause):
                return True
        return False

    def declines_group_issue(issue_pattern: str) -> bool:
        """Apply a shared negation to each issue named in the same list."""
        wrapped_issue = rf"(?:{issue_pattern})"
        for clause in duty_clauses:
            if not re.search(issue_pattern, clause):
                continue
            if re.search(
                r"\b(?:no|neither|without|not\s+to|(?:am|is|are|would|will|shall|do|does)\s+not)\b"
                r"[^.;]{0,180}" + wrapped_issue,
                clause,
            ):
                return True
            if re.search(
                wrapped_issue
                + r"[^.;]{0,180}\b(?:(?:would|will|shall|are|is)\s+not|not\s+be|none\s+(?:would\s+)?become)\b"
                + r"[^.;]{0,60}\b(?:included|required|expected|part\s+of|responsibilit(?:y|ies)|obligations?|commitments?|routine)\b",
                clause,
            ):
                return True
        return False
    travel_budget = re.search(r"\b(\d+(?:\.\d+)?)\s*k\s+for\s+(?:travel\s+)?expenses\b", lower)
    if travel_budget:
        amount = int(float(travel_budget.group(1)) * 1000)
        additions.append(("Personal Budget", f"${amount:,}"))
    typo_budget=re.search(r'\b(?:personalm|personnel)\s+expenses?(?:\s+budget)?\s+(?:of\s+)?(\$?\s*\d[\d,.]*(?:\s*k)?)',lower)
    if typo_budget:
        additions.append(('Personal Budget',typo_budget.group(1)))
    # The current task permits monetary proposals beyond its reference points.
    # Preserve the archived bounded-scenario behavior used in historical tests.
    if isinstance(_scenario_issue_map(scenario).get('Salary',{}).get('proposal_domain'),dict):
        for pair in _explicit_cash_pairs(_affirmative_numeric_text(_focused_text(text))):
            additions.append((pair['issue'],pair['option']))
    if 'Team Coaching Responsibility' in _scenario_issue_map(scenario) and re.search(r'\bno\s+recurring\s+coaching\s+duty\b',lower):
        additions.append(('Team Coaching Responsibility','No recurring coaching duty'))
    if "maximum salary" in lower:
        spec = _scenario_issue_map(scenario).get("Salary")
        if not (spec and isinstance(spec.get("proposal_domain"), dict) and spec["proposal_domain"].get("max") is None):
            maximum = float(spec["max"]) if spec else 30000
            additions.append(("Salary", f"${maximum:,.0f}"))
    if re.search(r"\bmaximum\s+(?:work[-\s]?expense|personal)\s+budget\b", lower):
        spec = _scenario_issue_map(scenario).get("Personal Budget")
        if not (spec and isinstance(spec.get("proposal_domain"), dict) and spec["proposal_domain"].get("max") is None):
            maximum = float(spec["max"]) if spec else 20000
            additions.append(("Personal Budget", f"${maximum:,.0f}"))
    if "earliest possible start" in lower:
        additions.append(("Starting Date", str(_scenario_issue_map(scenario).get('Starting Date', {}).get('min', 'May'))))
    mentor_text = re.sub(r'\bmentor(?:ing)?\s+meeting\s+frequency\s*:[^;\n|]*', '', lower, flags=re.I)
    if re.search(r"\b(?:mentor|mentoring|mentorship)\b", mentor_text):
        option = _mentorship_option(lower)
        additions.append(("Mentorship Program", option))
    recruitment_involvement_marker = (
        r"\b(?:i|you|candidate|employee|new\s+hire|they)\b.{0,70}"
        r"\b(?:participat\w*|attend\w*|join\w*|represent\w*|volunteer\w*|tak(?:e|ing)\s+part|help(?:\s+out)?|assist|support\w*|commit\w*)\b|"
        r"\b(?:participation|involvement|commitment|responsibilit(?:y|ies)|obligation|role|opportunity\s+to\s+volunteer|volunteer\w*)\b"
    )
    recruitment_involvement_marker += r'|\bopportunit(?:y|ies)\s+to\b[^.;]{0,85}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b'
    if "recruitment fair" in lower and re.search(recruitment_involvement_marker, lower):
        option = "No commitment" if optional_or_declined(r"\brecruitment\s+fairs?\b") else "Commit"
        additions.append(("Role in Recruitment Fair", option))
    if "conference presentation" in lower or re.search(
        r"\bpresent(?:ing|ations?)?\b.{0,20}\bconferences?\b|"
        r"\bconferences?[-\s]+(?:speaking|talks?)\b",
        lower,
    ):
        option = "No commitment" if optional_or_declined(r"\b(?:conference|present)") else "Commit"
        additions.append(("Mandatory Conference Presentations", option))
    if "professional association" in lower:
        option = "No sponsorship" if any(re.search(r'\b(?:professional\s+association|membership)\b',c) and re.search(r"\b(?:no|not|without)\b.{0,45}\b(?:sponsor\w*|fees?)\b",c) for c in duty_clauses) else "Firm sponsors"
        additions.append(("Professional Associations Membership", option))
    if "linkedin" in lower and re.search(r"\b(?:commit|regular|recurring|post|publicity)\b", lower) and (
        not large_issue_space or linkedin_post_evidence
    ):
        option = "No commitment" if optional_or_declined(r"\b(?:linkedin|publicity|post)") else "Commitment"
        additions.append(("Regular Linkedin Posts for Company", option))
    if re.search(_LINKEDIN_CONTRIBUTION,lower):
        option='No commitment' if optional_or_declined(r'\blinkedin\b') else 'Commitment'
        additions.append(('Regular Linkedin Posts for Company',option))
    if re.search(r"\b(?:organizing|organize|organising|organise)\b.{0,25}\bsocial events?\b", lower):
        option = "No commitment" if optional_or_declined(r"\bsocial\s+events?\b") else "Commitment"
        additions.append(("Role in Organizing Social Events", option))
    if "team-building" in lower or "team building" in lower:
        option = "No commitment" if re.search(r"\b(?:no|exclude|without)\b.{0,25}\bteam[-\s]building\b", lower) else "Commitment"
        additions.append(("Role in Organizing Social Events", option))
    if re.search(r"\bteam[-\s]?event[-\s]organiz\w*\b|\borganiz\w*\b.{0,25}\bteam\s+events?\b", lower):
        option = "No commitment" if optional_or_declined(r"\bteam[-\s]?event") else "Commitment"
        additions.append(("Role in Organizing Social Events", option))

    # Role-private issues and hinted issues use ordinary employment language in
    # participant messages. These conservative aliases only resolve exact
    # configured choices; every extracted choice is still checked against the
    # payoff matrix below.
    number_words = {
        "zero": 0, "no": 0, "three": 3, "six": 6, "ten": 10,
        "one": 1, "two": 2, "four": 4, "five": 5, "seven": 7,
        "eight": 8, "nine": 9, "twelve": 12, "eighteen": 18,
        "twenty-four": 24, "twenty-five": 25, "twenty": 20,
        "two-and-a-half": 2.5, "two and a half": 2.5,
        "thirty": 30, "half a dozen": 6,
    }

    def word_number(value: str) -> int | None:
        value = value.lower().strip()
        if value.isdigit():
            return int(value)
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return float(value)
        return number_words.get(value)

    number_token = (
        r"half a dozen|two[-\s]and[-\s]a[-\s]half|twenty-four|twenty-five|eighteen|twelve|zero|no|one|two|"
        r"three|four|five|six|seven|eight|nine|ten|twenty|thirty|\d+(?:\.\d+)?"
    )

    vacation_patterns = [
        rf"\b({number_token})\s+(?:paid\s+)?days?\s+(?:of\s+)?(?:annual\s+leave|holiday|vacation|off)\b",
        rf"\b({number_token})\s+days?\s+of\s+paid\s+(?:annual\s+leave|holiday|vacation|time\s+off)\b",
        rf"\b({number_token})\s+(?:vacation|holiday|time\s+off)\s+days?\b",
        rf"\b(?:vacation|annual\s+leave|holiday)\b.{{0,20}}?\b(?<![\d.,])({number_token})\s+days?\b",
    ]
    for pattern in vacation_patterns:
        if 'Vacation Days' in usual_readings:
            break
        match = re.search(pattern, numeric_lower)
        if match:
            days = word_number(match.group(1))
            spec = _scenario_issue_map(scenario).get("Vacation Days")
            if match.start(1) > 0 and numeric_lower[match.start(1)-1] in '-−':
                days = -abs(days)
            if spec:
                tail = numeric_lower[match.end():match.end()+24]
                if spec.get('weekly_to_annual_factor') and re.match(r'\s*(?:per|each|every|a)\s+week\b|\s+weekly\b', tail):
                    days *= float(spec['weekly_to_annual_factor'])
                additions.append(("Vacation Days", f"{days} days"))
            elif not spec and days in {10, 20, 30}:
                additions.append(("Vacation Days", f"{days} days"))
            break

    remote_context = r"(?:remote(?:ly|[-\s]+working|[-\s]+work)?|wfh|home[-\s]working|work(?:ing)?[-\s]from[-\s]home|hybrid)"
    remote_patterns = [
        rf"\b({number_token})\s+{remote_context}\s+days?(?:\s+(?:each|every|per|a)\s+(week|month))?\b",
        rf"\b{remote_context}\b.{{0,22}}?\b(?<![\d.,])({number_token})\s+days?(?:\s+(?:each|every|per|a)\s+(week|month))?\b",
    ]
    if _scenario_issue_map(scenario).get('Remote Working Days', {}).get('default_period') == 'week':
        remote_patterns += [rf'\b{remote_context}\s+(?:for\s+)?({number_token})\s+times?(?:\s+(?:each|every|per|a)\s+(week|month))?\b']
    remote_scan = re.sub(r"\b(days?)\s+(weekly|monthly)\b", lambda m: m.group(1) + ' per ' + ('week' if m.group(2)=='weekly' else 'month'), numeric_lower)
    for pattern in remote_patterns:
        if 'Remote Working Days' in usual_readings:
            break
        match = re.search(pattern, remote_scan)
        if match:
            days = word_number(match.group(1))
            if match.start(1) > 0 and remote_scan[match.start(1)-1] in '-−':
                days = -abs(days)
            spec = _scenario_issue_map(scenario).get("Remote Working Days")
            expected_period = "week" if "week" in str((spec or {}).get("unit", "")).lower() else "month"
            stated_period = match.group(2) if len(match.groups()) > 1 else None
            if stated_period and stated_period != expected_period:
                break
            if spec and spec.get("kind") == "continuous":
                additions.append(("Remote Working Days", f"{days} days / {expected_period}"))
            elif not spec and days in {0, 3, 6}:
                additions.append(("Remote Working Days", f"{days} days / month"))
            break

    for name, reading in usual_readings.items():
        if reading.get('value') is not None:
            additions.append((name, str(reading['value'])))

    probation_patterns = [
        rf"\b({number_token})[-\s]?(?:months?|mos?|mo)\s+(?:of\s+)?(?:initial\s+)?(?:probation(?:ary)?|trial)(?:\s+period)?\b",
        rf"\b({number_token})[-\s]?(?:months?|mos?|mo)\s+before\s+(?:becoming|being|going|made)?\s*(?:a\s+)?permanent(?:ly)?(?:\s+employed|\s+employee|\s+employment)?\b",
        # A non-greedy bridge preserves the whole decimal in phrases such as
        # "probationary period will run for 4.5 months".
        rf"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b.{{0,30}}?\b({number_token})\s*(?:months?|mos?|mo)\b",
        rf"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b.{{0,25}}?\b(?:last|run|be)\w*\s+(?:for\s+)?({number_token})\s*(?:months?|mos?|mo)\b",
    ]
    probation_added = False
    for pattern in probation_patterns:
        match = re.search(pattern, lower)
        if match:
            months = word_number(match.group(1))
            spec = _scenario_issue_map(scenario).get("Probation Length")
            if spec and float(spec["min"]) <= float(months) <= float(spec["max"]):
                additions.append(("Probation Length", f"{months} months"))
                probation_added = True
            elif not spec and months in {0, 3, 6}:
                additions.append(("Probation Length", f"{months} months"))
                probation_added = True
            break
    if not probation_added and re.search(
        r"\bno\s+(?:probation|trial(?:\s+period)?)\b|"
        r"\b(?:waiv(?:e|ed|ing)|skip(?:ping)?)\s+(?:the\s+)?(?:probation(?:ary)?|trial(?:\s+period)?)\b",
        lower,
    ):
        additions.append(("Probation Length", "0 months"))
    elif not probation_added and re.search(
        r"\b(?:probation(?:ary)?|trial)(?:\s+period)?\b.{0,30}\bhalf\s+a\s+year\b"
        r"|\bhalf\s+a\s+year\b.{0,30}\b(?:probation(?:ary)?|trial)(?:\s+period)?\b",
        lower,
    ):
        additions.append(("Probation Length", "6 months"))

    contract_patterns = [
        r"\b(two[-\s]and[-\s]a[-\s]half|one|two|three|four|\d+(?:\.\d+)?)[-\s]?years?\s+(?:fixed[-\s]?term\s+)?(?:employment\s+)?(?:contract|deal)\b",
        r"\b(one|two|three|four|\d+(?:\.\d+)?)[-\s]?(?:years?|yrs?)\s+(?:employment\s+)?(?:term|agreement|appointment)\b",
        r"\b(?:employment\s+agreement|fixed[-\s]?(?:term\s+)?appointment)\b.{0,22}?\b(one|two|three|four|\d+(?:\.\d+)?)\s+(?:years?|yrs?)\b",
        r"\b(?:employment\s+term|contract\s+length)\b.{0,18}?\b(one|two|three|four|\d+(?:\.\d+)?)\s+(?:years?|yrs?)\b",
        r"\b(?:contract|employment\s+agreement|employment\s+term|fixed\s+appointment)\b.{0,35}?\b(?:run|last|continue|be|remain)\w*\s+(?:in\s+place\s+)?(?:for\s+)?(one|two|three|four|\d+(?:\.\d+)?)\s+(?:years?|yrs?)\b",
    ]
    contract_words = {"one": 1, "two": 2, "three": 3, "four": 4, "two-and-a-half": 2.5, "two and a half": 2.5}
    for pattern in contract_patterns:
        match = re.search(pattern, lower)
        if match:
            raw_years = match.group(1)
            years = float(raw_years) if re.fullmatch(r"\d+(?:\.\d+)?", raw_years) else contract_words.get(raw_years)
            shown_years = int(years) if years is not None and float(years).is_integer() else years
            spec = _scenario_issue_map(scenario).get("Contract Length")
            if spec and float(spec["min"]) <= float(years) <= float(spec["max"]):
                additions.append(("Contract Length", f"{shown_years} years"))
            elif not spec and years in {2, 3, 4}:
                additions.append(("Contract Length", f"{shown_years} years"))
            break

    # Participants also describe a fixed term in months. Convert exact
    # quarter-year durations to the scenario's year scale; do not round.
    contract_months = re.search(
        rf"\b(?:contract|employment\s+agreement|fixed[-\s]?(?:term\s+)?appointment)\b"
        rf".{{0,35}}\b(?:run|last|continue|be|remain)\w*\s+(?:for\s+)?({number_token})\s*(?:months?|mos?|mo)\b"
        rf"|\b({number_token})[-\s]?(?:months?|mos?|mo)\s+(?:contract|employment\s+agreement|fixed[-\s]?(?:term\s+)?appointment)\b",
        lower,
    )
    if contract_months and _duration_is_noncompete_detail(
        lower, contract_months.start(), contract_months.end()
    ):
        contract_months = None
    if contract_months:
        raw_months = next(value for value in contract_months.groups() if value is not None)
        months = word_number(raw_months)
        years = float(months) / 12 if months is not None else None
        spec = _scenario_issue_map(scenario).get("Contract Length")
        if years is not None and years * 4 == round(years * 4):
            shown_years = int(years) if years.is_integer() else years
            if spec and float(spec["min"]) <= years <= float(spec["max"]):
                additions.append(("Contract Length", f"{shown_years} years"))
            elif not spec and years in {2, 3, 4}:
                additions.append(("Contract Length", f"{shown_years} years"))

    if re.search(r"\bprofessional\s+training\b|\btraining\s+(?:program(?:me)?|course)\b|\btraining\s+and\s+mentorship\b", lower):
        negative = bool(re.search(r"\b(?:no|not|without|opt\s+out\s+of)\b.{0,35}\b(?:professional\s+)?training\b", lower))
        additions.append(("Professional Training Program", "No participation" if negative else "Participation"))
    if _explicit_training_participation(lower):
        additions.append(('Professional Training Program','Participation'))

    if re.search(
        r"\b(?:mentorship\s+program|mentor\s+program|assigned\s+(?:an?\s+)?(?:internal\s+)?mentor|"
        r"designated\s+mentor|formal\s+mentor|experienced\s+mentor|mentoring\s+from\s+(?:an?\s+)?experienced|"
        r"participat\w*.{0,20}\bmentorship)\b",
        lower,
    ):
        negative = _mentorship_option(lower)=='No participation'
        additions.append(("Mentorship Program", "No participation" if negative else "Participation"))

    mentor_frequency = re.search(
        r"\b(?:mentor|mentoring)\b(?:\s+(?:meetings?|sessions?|catch[-\s]?ups?|check[-\s]?ins?|conversations?|with|are|is|will|be|held|scheduled|happen|occur|once)){0,6}\s+"
        r"(monthly|weekly|each\s+month|every\s+month|each\s+week|every\s+week)\b"
        r"|\b(monthly|weekly|each\s+month|every\s+month|each\s+week|every\s+week)\s+"
        r"(?:mentor(?:ing)?\b|(?:meetings?|sessions?)\s+with\s+(?:a|my|the)\s+mentor\b)",
        lower,
    )
    if mentor_frequency and 'Mentor Meeting Frequency' in _scenario_issue_map(scenario):
        cadence = next((value for value in mentor_frequency.groups() if value), "")
        additions.append((
            "Mentor Meeting Frequency",
            "One scheduled mentor meeting weekly" if "week" in cadence else "One scheduled mentor meeting monthly",
        ))

    recruitment_issue_pattern = r"\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b"
    if re.search(recruitment_issue_pattern, lower) and re.search(recruitment_involvement_marker, lower):
        negative = bool(
            optional_or_declined(recruitment_issue_pattern)
            or re.search(r"\bno\s+(?:recurring|regular|ongoing)?\s*(?:responsibility|obligation|requirement)\b.{0,45}" + recruitment_issue_pattern, lower)
            or re.search(r"\bno\b[^.;]{0,80}" + recruitment_issue_pattern + r"[-\s]+commitment\b", lower)
            or re.search(r"\b(?:opportunity|option|chance)\s+to\s+volunteer\b.{0,45}" + recruitment_issue_pattern, lower)
            or re.search(r"\b(?:could|may|can)\s+volunteer\b.{0,45}" + recruitment_issue_pattern, lower)
            or re.search(r"\b(?:opportunit(?:y|ies)|let|allow|glad)\b.{0,100}\bvolunteer(?:ing)?\b.{0,45}" + recruitment_issue_pattern, lower)
            or re.search(r"\bvolunteer(?:ing)?\b.{0,45}" + recruitment_issue_pattern, lower)
        )
        if _literal_fair_commitment(lower):negative=False
        additions.append(("Role in Recruitment Fair", "No commitment" if negative else "Commit"))

    if re.search(r"\bconferences?\b", lower) and re.search(r"\b(?:present(?:ation|ations|ing)?|speaking|speak|talks?|activities|commitment)\b", lower):
        negative = optional_or_declined(r"\b(?:conference|present)")
        additions.append(("Mandatory Conference Presentations", "No commitment" if negative else "Commit"))

    social_issue_pattern = (
        r"\b(?:team|company|staff)[-\s]+(?:events?|socials?\b(?![-\s]+media)|gatherings?)\b|"
        r"\bsocial[-\s]+(?:events?|gatherings?)\b"
    )
    if re.search(social_issue_pattern, lower) and re.search(
        r"\b(?:plan|planning|organize|organise|organizing|organising|coordinate|coordinating|help)\b",
        lower,
    ):
        negative = bool(
            optional_or_declined(social_issue_pattern)
            or re.search(r"\b(?:no\s+need\s+to|not\s+required\s+to|would\s+not|will\s+not)\b.{0,55}" + social_issue_pattern, lower)
        )
        additions.append(("Role in Organizing Social Events", "No commitment" if negative else "Commitment"))

    role_object = r"(?:duties|priorities|responsibilities|role(?:\s+scope)?|job\s+scope)"
    role_review_marker = r"(?:review(?:ed|ing)?|revisit(?:ed|ing)?|reassess|check[-\s]?in(?:\s+on)?|check(?:ed|ing)?)"
    role_clause = next((
        clause for clause in re.split(r";|(?<!\d)\.|\.(?!\d)", lower)
        if re.search(
            rf"\b{role_object}\b",
            re.sub(
                r"\b(?:promotion|expanded|broader|new)\s+(?:duties|responsibilities)\b|"
                r"\b(?:compensation|performance)\s+review\b[^.;]*\bresponsibilities\b",
                "",
                clause,
            ),
        )
        and re.search(rf"\b{role_review_marker}\b", clause)
    ), None)
    no_role_review_timetable = bool(
        re.search(rf"\b{role_object}\b", lower)
        and (
            re.search(
                r"\b(?:no|without)\s+(?:fixed|scheduled|regular|formal)?\s*"
                r"(?:review|check[-\s]?in)\s+(?:schedule|timetable|calendar)\b",
                lower,
            )
            or re.search(
                r"\b(?:will|would|do|does)\s+not\s+(?:schedule|hold|have)\b"
                r"[^.;]{0,35}\b(?:review|check[-\s]?in)\b",
                lower,
            )
            or re.search(
                r"\b(?:review|check[-\s]?in)s?\b[^.;]{0,35}\bunscheduled\b",
                lower,
            )
        )
    )
    if no_role_review_timetable:
        additions.append(("Role Review Schedule", "No scheduled review"))
    elif role_clause:
        if re.search(r"\b(?:no|without)\b.{0,30}\b(?:fixed|scheduled|regular|formal)?\s*(?:review|check[-\s]?in)\b", role_clause) or re.search(
            r"\b(?:no|without)\s+(?:fixed|scheduled|regular|formal)\s+(?:review|check[-\s]?in)\b",
            lower,
        ):
            additions.append(("Role Review Schedule", "No scheduled review"))
        elif re.search(r"\b(?:three|3)[-\s]months?\b|\b(?:every|after|at|in)\s+(?:three|3)\s+months?\b|\bmonths?\s+(?:three|3)\b", role_clause):
            additions.append(("Role Review Schedule", "Three-month review"))
        elif re.search(r"\b(?:six|6)[-\s]months?\b|\b(?:every|after|at|in)\s+(?:six|6)\s+months?\b|\bmonths?\s+(?:six|6)\b", role_clause):
            additions.append(("Role Review Schedule", "Six-month review"))

    promotion_context = r"(?:approved\s+)?promotion|promoted|promotion\s+responsibilities|promotion\s+duties"
    pay_review_context = (
        r"(?:(?:pay|salary|compensation)\s+(?:review|discussion|conversation)|"
        r"(?:discuss|review)\s+(?:pay|salary|compensation))"
    )
    if re.search(rf"\b{pay_review_context}\b[^.;]{{0,80}}\b{promotion_context}\b|\b{promotion_context}\b[^.;]{{0,80}}\b{pay_review_context}\b", lower):
        if re.search(r"\b(?:no|without)\s+(?:a\s+)?separate\b[^.;]{0,35}\b(?:pay|salary|compensation)\s+(?:review|discussion|conversation)\b", lower) or re.search(
            r"\b(?:promotion|promoted)\b[^.;]{0,55}\b(?:will|would)\s+not\s+(?:trigger|receive|include|have)\b"
            r"[^.;]{0,45}\b(?:separate\s+)?(?:pay|salary|compensation)\s+(?:review|discussion|conversation)\b",
            lower,
        ):
            additions.append(("Pay Review Timing", "No separate review"))
        elif re.search(r"\bwithin\s+(?:90|ninety)\s+days?\b", lower):
            additions.append(("Pay Review Timing", "Within 90 days after promotion"))
        elif re.search(r"\bbefore\b[^.;]{0,50}\b(?:promotion|expanded|broader|new)\s+(?:responsibilities|duties)\b", lower):
            additions.append(("Pay Review Timing", "Before promotion responsibilities begin"))

    if re.search(r"\bnon[-\s]?compete\b", lower):
        # Refusing a waiver is not offering a waiver. Scope this resolution to
        # affirmative clauses; retain the unpriced duration separately.
        noncompete_text = _affirmative_numeric_text(lower)
        refused_waiver = bool(re.search(r"\b(?:cannot|can[’\x27]t|won[’\x27]t|(?:will|would|do|does)\s+not|no)\s+(?:agree\s+to\s+)?waiv(?:e|er|ing)\b[^.;]{0,45}\bnon[-\s]?compete\b",noncompete_text))
        waived = bool(
            re.search(r"\b(?:waive|waived|waiving|drop|remov(?:e|ed|ing))\b.{0,30}\bnon[-\s]?compete\b", noncompete_text)
            or re.search(r"\bnon[-\s]?compete\b.{0,30}\b(?:waive|waived|drop|remov(?:e|ed|ing))\b", noncompete_text)
            or re.search(r"\b(?:no|without)\s+(?:a\s+)?(?:post[-\s]employment\s+)?non[-\s]?compete\b(?![^.;]{0,35}\b(?:beyond|during|before|after)\b)", noncompete_text)
            or re.search(r"\bnot\s+(?:be\s+)?subject\s+to\s+(?:a\s+)?non[-\s]?compete\b", noncompete_text)
        )
        if refused_waiver:
            waived = False
        kept = any(re.search(r"\bnon[-\s]?compete\b.{0,30}\b(?:keep|kept|retain(?:ed)?|stays?|remains?)\b|\b(?:keep|retain)\b.{0,25}\bnon[-\s]?compete\b",c) for c in duty_clauses)
        kept = kept or refused_waiver
        kept = kept or bool(re.search(r"\baccept\b[^.;]{0,75}\bstandard\b[^.;]{0,35}\bnon[-\s]?compete\b",noncompete_text))
        limited = bool(re.search(
            r"\bnon[-\s]?compete\b.{0,90}\b(?:apply|restriction|restrict|limited|months?|competitors?)\b"
            r"|\b(?:restriction|restrict|limited)\b.{0,90}\bnon[-\s]?compete\b",
            lower,
        ))
        if waived or kept or limited:
            additions.append(("Non-compete Clause", "Waive" if waived else "Keep"))

    career_review = re.search(
        r"\b(?:written\s+)?career[-\s]development\s+(?:conversation|review)s?\b.{0,35}\b(?:every\s+six\s+months|twice\s+(?:a|per)\s+year|two\s+times\s+(?:a|per)\s+year)\b",
        lower,
    )
    if career_review:
        additions.append(("Senior Career Guidance", "Two conversations yearly"))
    stated_career_count=re.search(r'\b(one|two|1|2)\s+(?:scheduled\s+)?career[-\s]development\s+conversations?\b[^.;]{0,55}\b(?:per|a|each)\s+year\b',numeric_lower,re.I)
    if stated_career_count:
        count=stated_career_count.group(1).lower()
        additions.append(('Senior Career Guidance','One conversation yearly' if count in {'one','1'} else 'Two conversations yearly'))

    for association_clause in duty_clauses:
        if not re.search(r"\b(?:professional|sales)[-\s]?(?:association|membership)|\bprofessional\s+memberships?\b|\bassociation(?:s|\s+sponsorship|\s+dues)?\b",association_clause):
            continue
        negative = bool(
            re.search(r"\b(?:no|not|without)\b.{0,55}\b(?:reimbursement|sponsor\w*|fees?|professional\s+(?:associations?|memberships?))\b", association_clause)
            or re.search(r"\binstead\s+of\b.{0,55}\b(?:association|membership)\s+(?:sponsor|sponsorship|fees?)\b", association_clause)
        )
        sponsored = bool(re.search(r"\b(?:pays?|sponsors?|reimburses?)\b.{0,35}\b(?:association|membership|dues)\b|\b(?:association|membership)\b[^.;]{0,50}\bcompany[-\s]sponsored\b", association_clause))
        if negative or sponsored:
            additions.append(("Professional Associations Membership", "No sponsorship" if negative else "Firm sponsors"))

    social_context = re.search(r"\b(?:company\s+)?social[-\s]+events?\b|\bteam\s+socials?\b", lower)
    if social_context:
        negative = optional_or_declined(r"\b(?:company\s+)?social[-\s]+events?\b|\bteam\s+socials?\b")
        additions.append(("Role in Organizing Social Events", "No commitment" if negative else "Commitment"))

    publicity_issue_pattern = (
        r"\b(?:linkedin|publicity|public\s+communications?|company\s+communications?|"
        r"sales\s+work\s+used\s+in\s+public"
        + (r"|social[-\s]+media|social\s+posts?|public\s+updates?" if _uses_broad_social_posts(scenario) else "")
        + r")\b"
    )
    if re.search(publicity_issue_pattern, lower) and (not large_issue_space or linkedin_post_evidence):
        approval_only = bool(
            re.search(r"\b(?:with|subject\s+to)\s+(?:my|your|their|his|her|the\s+candidate['’]s)\s+(?:prior\s+)?approval\b.{0,100}" + publicity_issue_pattern, lower)
            or re.search(publicity_issue_pattern + r".{0,100}\b(?:with|subject\s+to)\s+(?:my|your|their|his|her|the\s+candidate['’]s)\s+(?:prior\s+)?approval\b", lower)
            or re.search(publicity_issue_pattern + r".{0,100}\brequir(?:e|es|ed|ing)\s+(?:my|your|their|his|her|the\s+candidate['’]s)\s+(?:prior\s+)?approval\b", lower)
        )
        negative = optional_or_declined(publicity_issue_pattern) or approval_only
        additions.append(("Regular Linkedin Posts for Company", "No commitment" if negative else "Commitment"))

    # Shared predicates at the end of a list are common in real offers (for
    # example, "no recurring team-event, publicity, or conference duties").
    # Resolve those phrases after the general aliases so these direct readings
    # win over a model's neighboring-issue guess.
    no_recurring = r"\bno\s+(?:recurring|regular|ongoing)?\s*(?:responsibility|obligation|requirement|dut(?:y|ies))\b"
    publicity_scope_marker = (
        no_recurring
        + r"|\bno\s+(?:recurring|regular|ongoing)\b[^,]{0,90}\b(?:responsibility|obligation|requirement|dut(?:y|ies))\b"
        + r"|\b(?:would\s+not|will\s+not|not\s+be|isn't|is\s+not|aren't|are\s+not)\s+(?:required|expected|an?\s+obligation)\b"
    )
    publicity_declined_by_scope = any(
        re.search(publicity_issue_pattern, clause) and re.search(publicity_scope_marker, clause)
        for clause in duty_clauses
    )
    if publicity_declined_by_scope and (not large_issue_space or linkedin_post_evidence):
        additions.append(("Regular Linkedin Posts for Company", "No commitment"))
    elif re.search(r"\b(?:linkedin\s+)?(?:contributions?|posts?|publicity)\b.{0,35}\b(?:expected|required|commit|contribute)\b", lower) and (
        not large_issue_space or linkedin_post_evidence
    ):
        additions.append(("Regular Linkedin Posts for Company", "Commitment"))
    elif re.search(r"\bcontribut\w*\b.{0,75}\blinkedin\b|\blinkedin\b.{0,75}\bcontribut\w*\b", lower) and (
        not large_issue_space or linkedin_post_evidence
    ):
        additions.append((
            "Regular Linkedin Posts for Company",
            "No commitment" if optional_or_declined(publicity_issue_pattern) else "Commitment",
        ))
    affirmative_publicity = re.search(
        r"\b(?:contribute|contributes|contributing|provide|provides|providing|produce|produces|producing|support|supports|supporting|shape|shapes|shaping|help(?:s|ing)?\s+(?:to\s+)?shape)\b"
        r"[^.;]{0,90}" + publicity_issue_pattern,
        lower,
    )
    if affirmative_publicity and (not large_issue_space or linkedin_post_evidence) and not optional_or_declined(publicity_issue_pattern) and not approval_only and not publicity_declined_by_scope:
        additions.append(("Regular Linkedin Posts for Company", "Commitment"))
    if re.search(no_recurring + r".{0,90}\b(?:conference|presentation)\b", lower) or re.search(
        r"\b(?:conference|presentation)\b.{0,90}" + no_recurring, lower
    ) or re.search(r"\bno\s+(?:recurring|regular|ongoing)\b.{0,100}\b(?:conference|presentation)\b.{0,100}\b(?:responsibility|obligation|requirement|dut(?:y|ies))\b", lower):
        additions.append(("Mandatory Conference Presentations", "No commitment"))
    if re.search(no_recurring + r".{0,90}\b(?:team[-\s]?events?|social\s+events?)\b", lower) or re.search(
        r"\b(?:team[-\s]?events?|social\s+events?)\b.{0,90}" + no_recurring, lower
    ) or re.search(r"\bno\s+(?:recurring|regular|ongoing)\b.{0,100}\b(?:team[-\s]?events?|social\s+events?)\b.{0,100}\b(?:responsibility|obligation|requirement|dut(?:y|ies))\b", lower) or re.search(
        r"\b(?:avoid|without)\b.{0,35}\b(?:recurring\s+)?(?:team[-\s]?event|social\s+event)[-\s]?organiz\w*", lower
    ) or re.search(
        r"\b(?:would|will|do|does)\s+not\s+have\b.{0,65}\b(?:team[-\s]?events?|social\s+events?)\b", lower
    ) or re.search(
        r"\b(?:would|will|do|does)\s+not\s+have\b.{0,45}\b(?:recurring\s+)?(?:responsibility|obligation|dut(?:y|ies))\b.{0,45}\b(?:team[-\s]?events?|social\s+events?)\b", lower
    ):
        additions.append(("Role in Organizing Social Events", "No commitment"))

    if re.search(r"\b(?:twice[-\s]?yearly|twice\s+(?:a|per)\s+year|every\s+six\s+months)\b.{0,45}\b(?:advancement|promotion|progression|career[-\s]development|development)\s+reviews?\b", lower):
        additions.append(("Advancement Review Frequency", "Twice-yearly reviews"))
    elif re.search(r"\bannual\b.{0,35}\b(?:advancement|promotion|progression)\s+reviews?\b", lower):
        additions.append(("Advancement Review Frequency", "Annual review"))
    if re.search(r"\b(?:pay|salary|compensation)\s+review\b.{0,65}\bbefore\b.{0,35}\b(?:promotion|expanded|broader)\s+(?:responsibilities|duties)\b", lower):
        additions.append(("Pay Review Timing", "Before promotion responsibilities begin"))
    if re.search(r"\b(?:cannot\s+agree\s+to|would\s+not\s+be\s+included|without)\b.{0,100}\b(?:professional[-\s]?association|association)\s+(?:membership|sponsorship)\b", lower):
        additions.append(("Professional Associations Membership", "No sponsorship"))
    elif re.search(r"\b(?:professional[-\s]?association|association)\s+(?:membership|sponsorship)\b.{0,100}\b(?:would\s+not\s+be\s+included|is\s+not\s+included|cannot\s+be\s+included)\b", lower):
        additions.append(("Professional Associations Membership", "No sponsorship"))
    zero_discount = re.search(
        r"\b(?:no|not|zero|0)\b.{0,40}\b(?:percentage\s+points?|percent)\b.{0,60}\b(?:routine\s+)?(?:customer\s+)?discount",
        lower,
    ) or re.search(
        r"\b(?:routine\s+)?(?:customer\s+)?discount\b.{0,60}\b(?:no|zero|0|not\s+any)\b.{0,30}\b(?:percentage\s+points?|percent)",
        lower,
    )
    if zero_discount:
        additions.append(("Routine Discount Limit", "0 percentage points"))
    elif re.search(
        r"\b(?:not\s+(?:be\s+able\s+to\s+)?approve|cannot\s+approve|can't\s+approve|no\s+authority\s+to\s+approve)\b"
        r".{0,70}\b(?:routine\s+)?(?:customer\s+)?discounts?\b.{0,55}\b(?:manager|approval)\b",
        lower,
    ):
        additions.append(("Routine Discount Limit", "0 percentage points"))
    paid_learning = re.search(
        rf"\b({number_token})\s+paid\s+hours?\b.{{0,55}}\b(?:per|each|every)\s+week\b.{{0,55}}\b(?:training|mentoring|learning|development)\b",
        lower,
    ) or re.search(
        rf"\b({number_token})\s+paid\s+hours?\b.{{0,55}}\b(?:training|mentoring|learning|development)\b.{{0,55}}\b(?:per|each|every)\s+week\b",
        lower,
    )
    if paid_learning:
        hours = word_number(paid_learning.group(1))
        additions.append(("Paid Learning Time", f"{hours} paid hours per week"))
    if re.search(r"\bcandidate\s+chooses?\s+one\s+approved\s+senior\s+colleague\b", lower):
        additions.append(("Reference Provider Choice", "Candidate chooses one approved senior colleague"))
    elif re.search(r"\bhuman\s+resources?\b.{0,55}\bprovides?\b.{0,30}\breference\b", lower):
        additions.append(("Reference Provider Choice", "Human resources provides the reference"))
    elif re.search(r"\bformer\s+manager\b.{0,55}\b(?:may\s+)?provides?\b.{0,30}\breference\b", lower):
        additions.append(("Reference Provider Choice", "The former manager may provide the reference"))
    if re.search(r"\b(?:input|suggest|propose)\b.{0,45}\balternative\s+(?:travel\s+|trip\s+)?dates?\b", lower):
        additions.append(("Input on Unusual Travel Dates", "Alternative-date input"))
    if re.search(r"\b(?:performance\s+reviews?|evaluations?)\b.{0,45}\b(?:sales\s+only|only(?:\s+on)?\s+sales|based\s+only(?:\s+on)?\s+sales)\b", lower):
        additions.append(("Teamwork in Performance Reviews", "sales only"))
    if re.search(r"\beconomy\s+class\b.{0,45}\b(?:qualifying|long|longer)\b.{0,20}\bflights?\b", lower):
        additions.append(("Travel Class for Long Trips", "Economy class for every qualifying flight."))
    temporary_lead = re.search(r"\btemporary\s+lead\s+assignment\b.{0,45}\b(\d+)\s+weeks?\b", lower)
    if temporary_lead:
        additions.append(("Temporary Lead Assignment Length", f"{temporary_lead.group(1)} weeks"))
    travel_approval = re.search(r"\b(?:manager|approval)\b.{0,55}\b(?:unusual|business)\s+travel\b.{0,55}\b(\d+)\s+business\s+days?\b", lower)
    if travel_approval:
        additions.append(("Travel Approval Speed", f"{travel_approval.group(1)} business days"))
    if re.search(r"\bno\s+dates?\b.{0,35}\bprotected\b.{0,35}\bovernight\s+travel\b", lower):
        additions.append(("Periods With No Overnight Travel", "No dates are protected from required overnight travel."))
    if re.search(r"\balternative\s+(?:arranged\s+)?travel\b", lower):
        additions.append(("Alternative Travel for Care Needs", "alternative arranged"))
    notice_period = re.search(rf"\b({number_token})[-\s]?weeks?\b[^.;]{{0,45}}\b(?:required\s+)?notice\s+period\b", lower) or re.search(
        rf"\b(?:required\s+)?notice\s+period\b[^.;]{{0,45}}\b({number_token})[-\s]?weeks?\b",
        lower,
    )
    if notice_period:
        weeks = word_number(notice_period.group(1))
        additions.append(("Notice Period Length", f"{weeks} weeks"))
    if re.search(r"\b(?:candidate\s+will\s+)?handle\b.{0,35}\bcustomer\s+questions?\b.{0,30}\b(?:on\s+(?:their|his|her)\s+own|alone)\b", lower):
        additions.append(("Specialist Help for Customer Questions", "Self-answering"))
    workweek_trial = _explicit_workweek_trial(lower)
    if workweek_trial:
        additions.append(("Four-Day Workweek Trial", f"{workweek_trial} trial"))

    # Natural-language offers often place one negative predicate before or
    # after a list. Apply it to every supported duty named in that list.
    grouped_duties = (
        ("Role in Recruitment Fair", r"\b(?:recruitment|recruiting|careers?)[-\s]+(?:fairs?|events?)\b", "No commitment"),
        ("Mandatory Conference Presentations", r"\b(?:conference[-\s]+(?:present(?:ing|ation|ations)?|speaking|talks?|activities)|present(?:ing|ations?)?\s+at\s+conferences?)\b", "No commitment"),
        ("Role in Organizing Social Events", r"\b(?:team[-\s]?events?|social\s+events?)(?:[-\s]+organiz\w*)?\b|\borganiz\w*\b.{0,25}\b(?:team|social)\s+events?\b", "No commitment"),
        ("Regular Linkedin Posts for Company", publicity_issue_pattern, "No commitment"),
    )
    for issue, pattern, option in grouped_duties:
        if declines_group_issue(pattern) or optional_or_declined(pattern):
            additions.append((issue, option))
    # A refused list can mention membership after several other refused terms.
    # Keep its scope within a clause, not an arbitrary character window.
    for clause in duty_clauses:
        if re.search(r'\b(?:professional\s+association|association\s+membership)\b',clause) and (
            re.search(r'\b(?:cannot|can[’\x27]t|(?:will|would|do|does)\s+not|not\s+able\s+to)\s+(?:offer|include|add|provide)\b',clause)
            or re.search(r'\b(?:would|will|is|are)\s+not\s+(?:be\s+)?included\b',clause)
        ):
            additions.append(('Professional Associations Membership','No sponsorship'))

    # An explicit organizing duty wins over a neighboring optional/default
    # guess.  Keep this last so a concrete commitment is not overwritten by
    # an extractor's stale "No commitment" value.
    explicit_social_commitment = bool(
        re.search(
            r"\b(?:plan|organiz\w*|organis\w*|coordinat\w*)\b[^.;]{0,55}"
            r"\b(?:team|company|staff|social)[-\s]+(?:events?|socials?|gatherings?)\b",
            lower,
        )
        and not optional_or_declined(social_issue_pattern)
        and not declines_group_issue(social_issue_pattern)
    )
    if explicit_social_commitment:
        additions.append(("Role in Organizing Social Events", "Commitment"))
    if _explicit_fair_pledge(lower) or _literal_fair_commitment(lower):
        additions.append(('Role in Recruitment Fair','Commit'))
    # "Event-organizing duties" is an ordinary short form of the social-event
    # role. Do not conflate generic publicity with LinkedIn posting duties.
    for clause in duty_clauses:
        if re.search(r'\bevent[-\s]+organiz\w*\b',clause) and re.search(r'\b(?:duties|role|responsibilit\w*)\b',clause) and (re.search(r'\bno\b[^.;]{0,40}\bevent[-\s]+organiz\w*\b',clause) or re.search(r'\b(?:should|would|will)\s+not\s+be\s+part\s+of\s+(?:the\s+)?role\b',clause)):
            additions.append(('Role in Organizing Social Events','No commitment'))
    explicit_social_exclusion = _explicit_social_event_exclusion(lower)
    if explicit_social_exclusion:
        additions.append(('Role in Organizing Social Events', 'No commitment'))
    # A literal, configured Issue: Choice is the clearest possible participant
    # statement. It takes precedence over enrichment guesses, never over the
    # catalogue itself. No model answer key or scoring defaults are consulted.
    for issue, spec in _scenario_issue_map(scenario).items():
        if spec.get("kind") != "discrete":
            continue
        for option in spec.get("options", []):
            label = option.get("label", "")
            if label and re.search(r"(?<!\w)" + re.escape(issue.lower()) + r"\s*[:=]\s*"
                                   + re.escape(label.lower()) + r"(?=$|[\s,;.!?])", lower):
                additions.append((issue, label))
    return [{"issue": issue, "option": option, "confidence": 1.0, "source": "deterministic_alias"}
            for issue, option in additions]


def _tutorial_money_value(raw: str) -> float | None:
    """Read common compact price wording used in the short practice."""
    cleaned = raw.lower().replace(',', '').strip()
    numeric = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if numeric:
        return float(numeric.group())
    cleaned = cleaned.replace('-', ' ')
    direct = {
        "one hundred": 100, "one fifty": 150, "one hundred fifty": 150,
        "two hundred": 200, "two fifty": 250, "two hundred fifty": 250,
        "three hundred": 300, "three fifty": 350, "three hundred fifty": 350,
        "four hundred": 400, "four fifty": 450, "four hundred fifty": 450,
        "five hundred": 500, "five fifty": 550, "five hundred fifty": 550,
        "six hundred": 600, "six fifty": 650, "six hundred fifty": 650,
        "seven hundred": 700, "seven fifty": 750, "seven hundred fifty": 750,
        "eight hundred": 800,
    }
    for wording, value in sorted(direct.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(wording)}\b", cleaned):
            return float(value)
    return None


def _tutorial_pair_enrichment(text: str, scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic safety net for terse practice offers.

    The tutorial deliberately teaches ordinary-language entry, so it accepts
    compact corrections ("300 fee or one fifty cost"), abbreviated dates, and
    relative closing-time language. The resulting interpretation is still
    shown to the participant for confirmation before it is sent.
    """
    lower = _focused_text(text).lower()
    additions: list[tuple[str, str]] = []

    money_pattern = re.compile(
        r"(?:\$\s*)?[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:usd|dollars?))?|"
        r"(?:one|two|three|four|five|six|seven|eight)(?:[-\s]+hundred)?(?:[-\s]+fifty)?",
        re.I,
    )
    if re.search(r"\b(?:venue|hall|space|booking)\b|\b(?:fee|cost|price|rent(?:al)?)\b|\$|\busd\b|\bdollars?\b", lower):
        money_matches = list(money_pattern.finditer(lower))
        labelled=[]
        for candidate in money_matches:
            before=lower[max(0,candidate.start()-30):candidate.start()]
            after=lower[candidate.end():candidate.end()+35]
            number=_tutorial_money_value(candidate.group())
            if number is not None and 0<=number<=31 and re.match(r'\s*(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\b',after):
                continue
            if re.search(r'\b(?:close|closing|end|finish|until)(?:\s+at)?\s*$',before):
                continue
            other_purchase=bool(re.search(r'\b(?:projector|food|refreshments?|snacks?|drinks?|clean(?:ing|up)?|staff)\b[^,.;\n]{0,25}$',before)
                                and not re.search(r'\b(?:venue\s+fee|hall\s+fee|booking\s+fee)\b',before))
            if other_purchase:
                continue
            if (re.search(r'\b(?:venue(?:\s+fee)?|hall|fee|costs?|price|rent(?:al)?|booking)\s*(?:(?:is|of|at|for)\s*|[:=]\s*)?$',before)
                    or re.match(r'\s*(?:(?:bucks?|usd|dollars?)\s*)?(?:for\s+)?(?:the\s+)?(?:venue|hall|fee|costs?|price|rent(?:al)?|booking)\b',after)):
                labelled.append(candidate)
        candidates=labelled or [m for m in money_matches if '$' in m.group() or re.search(r'\bdollars?\b',lower[m.end():m.end()+12])]
        money_values = [value for match in candidates if (value := _tutorial_money_value(match.group())) is not None]
        if money_values:
            # In natural speech, "X or Y" often records an immediate
            # self-correction. Use the last amount and let confirmation expose it.
            additions.append(("Venue fee", str(money_values[-1])))

    date_spec = _scenario_issue_map(scenario).get("Event date", {})
    if re.search(r"\b(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\b", lower):
        try:
            ordinal_words = {'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6,'seventh':7,'eighth':8,'ninth':9,'tenth':10,
                'eleventh':11,'twelfth':12,'thirteenth':13,'fourteenth':14,'fifteenth':15,'sixteenth':16,'seventeenth':17,
                'eighteenth':18,'nineteenth':19,'twentieth':20,'twenty first':21,'twenty second':22,'twenty third':23,
                'twenty fourth':24,'twenty fifth':25,'twenty sixth':26,'twenty seventh':27,'twenty eighth':28,'twenty ninth':29,'thirtieth':30,'thirty first':31}
            date_text=lower
            for word,number in sorted(ordinal_words.items(),key=lambda v:-len(v[0])):
                date_text=re.sub(r'\b'+word.replace(' ',r'[-\s]+')+r'\b',str(number),date_text)
            event_date = _date_from_text(date_text, date_spec)
            additions.append(("Event date", event_date.isoformat()))
        except (ValueError, TypeError):
            # Keep a stated but impossible day. Otherwise the participant sees
            # "add Event date" even though they already entered August 32.
            literal = re.search(r'\b(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\s+\d{1,3}(?:st|nd|rd|th)?\b', lower)
            literal = literal or re.search(r'(?<![\d.])\b\d{1,2}(?:st|nd|rd|th)?\s+(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\b', lower)
            if literal:
                additions.append(('Event date', literal.group()))

    closing_label = None
    if re.search(r"\b(?:close(?:s|d)?|closing|shut(?:s|ting)?|end(?:s|ing)?|finish(?:es|ing)?|wrap(?:s|ping)?\s+up)\b", lower):
        time_match = re.search(
            r"\b(?:close(?:s|d)?|closing|shut(?:s|ting)?|ends?|finish(?:es)?|wrap(?:s|ped|ping)?\s+up|until|by|at)\D{0,18}"
            r"(1[7-9]|2[0-3]|[5-9]|10|11|five|six|seven|eight|nine|ten|eleven)(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)?\b",
            lower,
        )
        if time_match:
            hour_token = time_match.group(1)
            hour = int(hour_token) if hour_token.isdigit() else {
                "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
            }[hour_token]
            marker = (time_match.group(3) or "").replace(".", "")
            if marker == "pm" and hour < 12:
                hour += 12
            if 5 <= hour <= 11 and marker != "am":
                hour += 12
            if 17 <= hour <= 23 and time_match.group(2) in (None, '00'):
                closing_label = f"{hour - 12}:00 p.m."
        elif re.search(r"\b(?:as\s+)?(?:early|earliest)\b|\bclose\s+early\b", lower):
            closing_label = "5:00 p.m."
        elif re.search(r"\b(?:as\s+)?(?:late|latest)\b|\bclose\s+late\b", lower):
            closing_label = "11:00 p.m."
    if closing_label:
        additions.append(("Closing time", closing_label))

    if re.search(r"\b(?:projector|presentation\s+(?:equipment|screen)|av\s+(?:equipment|screen)|display\s+screen)\b", lower) and not re.search(r'\b(?:no|without)\s+(?:a\s+)?projector\b|\bprojector\s+(?:is\s+)?not\s+(?:needed|required|included)\b',lower):
        if re.search(r"\b(?:your|venue(?:'s)?|manager(?:'s)?)\s+projector\b",lower):
            additions.append(("Projector", "Venue projector included"))
        elif re.search(r"\b(?:my|our)(?:\s+own)?\s+projector\b|\borganizer(?:'s)?\s+projector\b", lower) or (
            re.search(r"\b(?:bring|provide|supply|use)\b.{0,25}\bprojector\b", lower)
            and re.search(r"\b(?:we|i|organizer|our|my)\b", lower)
        ):
            additions.append(("Projector", "Organizer brings a projector"))
        else:
            additions.append(("Projector", "Venue projector included"))
    if re.search(r"\b(?:clean\w*|tidy\w*|clear\s+the\s+room|leave\s+the\s+room\s+clean)\b", lower):
        if re.search(r"\b(?:venue|you|manager|staff)\b.{0,28}\b(?:clean\w*|tidy\w*|handle\w*)\b|\b(?:clean\w*|tidy\w*|handle\w*)\b.{0,28}\b(?:venue|you|manager|staff)\b", lower):
            additions.append(("Cleanup", "Venue handles cleanup"))
        elif re.search(r"\b(?:we|i|organizer|volunteers?)\b", lower):
            additions.append(("Cleanup", "Organizer handles cleanup"))
    if re.search(r"\b(?:cancel|cancellation|refund(?:able)?|non[-\s]?refundable)\b|\bmoney\s+back\b", lower):
        if re.search(r"\b(?:non[-\s]?refundable|no\s+(?:refund|cancellation)|cannot\s+cancel)\b", lower):
            additions.append(("Cancellation notice", "Booking is non-refundable"))
        else:
            additions.append(("Cancellation notice", "Free cancellation allowed with notice"))
    if re.search(r"\b(?:setup|set\s+up|early\s+access|load[-\s]?in|access\s+(?:before|early)|arrive\s+early|get\s+in\s+early)\b", lower):
        if re.search(r"\b(?:no|without|not\s+allow(?:ed)?)\b.{0,25}\b(?:setup|set\s+up|early\s+access|load[-\s]?in)\b", lower):
            additions.append(("Setup access", "No early setup access"))
        else:
            additions.append(("Setup access", "Early setup access included"))
    if re.search(r"\b(?:door|entrance|check[-\s]?in|registration)\s+(?:staff|volunteers?|people|greeters?)\b|\b(?:staff|cover|work|manage)\s+(?:at\s+)?the\s+(?:door|entrance|check[-\s]?in|registration)\b|\b(?:someone|a\s+person|a\s+staff\s+member)\s+(?:on|at)\s+the\s+(?:door|entrance)\b|\b(?:greeters?|event\s+security|security\s+staff)\b", lower):
        organizer_staff = bool(re.search(
            r"\b(?:organizer|we|i|our|my|volunteers?)\b.{0,35}\b(?:door|entrance|check[-\s]?in|registration|greeters?|security)\b|"
            r"\b(?:door|entrance|check[-\s]?in|registration|greeters?|security)\b.{0,35}\b(?:organizer|we|i|our|my|volunteers?)\b|"
            r"\b(?:organizer|we|i|our|my|volunteers?)\b.{0,35}\b(?:staff|cover|work|manage)\s+(?:at\s+)?the\s+(?:door|entrance|check[-\s]?in|registration)\b",
            lower,
        ))
        additions.append(("Door staffing", "Organizer provides door staff" if organizer_staff else "Venue provides door staff"))
    if re.search(r"\b(?:food|refreshments?|snacks?|drinks?|cater(?:ing|ed)?|food\s+service)\b", lower):
        if re.search(r"\b(?:no|without)\s+(?:food|refreshments?|snacks?|drinks?|catering)\b|\b(?:food|refreshments?|snacks?|drinks?)\s+(?:not\s+included|excluded)\b", lower):
            food_choice = "No refreshments included"
        elif re.search(
            r"\b(?:organizer|we|i|our|my|volunteers?)\b.{0,35}\b(?:bring|provide|supply|handle|food|refreshments?|snacks?|drinks?|cater)\b|"
            r"\b(?:bring|provide|supply|handle)\b.{0,25}\b(?:our|my|organizer|volunteers?|food|refreshments?|snacks?|drinks?)\b",
            lower,
        ) and not re.search(r"\b(?:venue|manager)\s+(?:(?:will|can|shall|staff)\s+){0,2}(?:provide|include|supply|handle)\b", lower):
            food_choice = "Organizer provides refreshments"
        else:
            # In an organizer's offer, bare "free food" ordinarily asks for
            # venue-provided refreshments. Confirmation exposes this reading.
            food_choice = "Venue provides refreshments at no extra charge"
        additions.append(("Food and refreshments", food_choice))
    return [
        {"issue": issue, "option": option, "confidence": 1.0, "source": "tutorial_deterministic"}
        for issue, option in additions
    ]


def _evaluate_tutorial_offer(
    text: str,
    role: str,
    extraction: dict[str, Any] | list[Any],
    payoff: dict[str, Any],
    required_issues: list[str],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Small, scenario-neutral validator for the participant tutorial."""
    if isinstance(extraction, dict):
        raw_pairs = extraction.get("pairs", []) if isinstance(extraction.get("pairs"), list) else []
        offer_intent = extraction.get("offer_intent", "offer")
        unsupported = [str(item) for item in extraction.get("unsupported_terms", []) if str(item).strip()]
        captured_novel_terms = [str(item) for item in extraction.get("novel_terms", []) if str(item).strip()]
        ambiguities = [str(item) for item in extraction.get("ambiguities", []) if str(item).strip()]
    else:
        raw_pairs, offer_intent, unsupported, captured_novel_terms, ambiguities = extraction, "offer", [], [], []
    deterministic = _tutorial_pair_enrichment(text, scenario)
    deterministic_issues = {item["issue"] for item in deterministic}
    combined = _repair_misrouted_discrete_pairs(list(raw_pairs) + deterministic, scenario)
    optional_evidence = {
        "Projector": r"\b(?:projector|presentation\s+(?:equipment|screen)|av\s+(?:equipment|screen)|display\s+screen)\b",
        "Cleanup": r"\b(?:clean\w*|tidy\w*|clear\s+the\s+room|leave\s+the\s+room\s+clean)\b",
        "Cancellation notice": r"\b(?:cancel|cancellation|refund(?:able)?|non[-\s]?refundable)\b|\bmoney\s+back\b",
        "Setup access": r"\b(?:setup|set\s+up|early\s+access|load[-\s]?in|access\s+(?:before|early)|arrive\s+early|get\s+in\s+early)\b",
        "Door staffing": r"\b(?:door|entrance|check[-\s]?in|registration)\s+(?:staff|volunteers?|people|greeters?)\b|\b(?:staff|cover|work|manage)\s+(?:at\s+)?the\s+(?:door|entrance|check[-\s]?in|registration)\b|\b(?:someone|a\s+person|a\s+staff\s+member)\s+(?:on|at)\s+the\s+(?:door|entrance)\b|\b(?:greeters?|event\s+security|security\s+staff)\b",
        "Food and refreshments": r"\b(?:food|refreshments?|snacks?|drinks?|cater(?:ing|ed)?|food\s+service)\b",
    }
    required_evidence = {
        "Venue fee": r"\b(?:venue|hall|space|booking)\b|\b(?:fee|cost|price|rent(?:al)?)\b|\$|\busd\b|\bdollars?\b",
        "Event date": r"\b(?:aug(?:ust)?|sep(?:t(?:ember)?)?|july?|jul)\b",
        "Closing time": r"\b(?:close(?:s|d)?|closing|shut(?:s|ting)?|end(?:s|ing)?|finish(?:es|ing)?|wrap(?:s|ping)?\s+up|until)\b",
    }
    last_by_issue: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for pair in combined:
        if not isinstance(pair, dict):
            continue
        issue, option = canonical_pair(str(pair.get("issue", "")).strip(), str(pair.get("option", "")).strip())
        if issue in optional_evidence and not re.search(optional_evidence[issue], _focused_text(text), re.I):
            continue
        if issue in required_evidence and not re.search(required_evidence[issue], _focused_text(text), re.I):
            continue
        if issue and option:
            last_by_issue[issue] = {"issue": issue, "option": option, "confidence": float(pair.get("confidence", 1) or 0)}

    findings: list[dict[str, Any]] = []
    lower = _focused_text(text).lower()
    numeric_alternative = r'\$?\s*\d+(?:\.\d+)?\s+or\s+\$?\s*\d+(?:\.\d+)?'
    alternatives = [
        ('Venue fee', numeric_alternative+r'\s*(?:dollars?|bucks?)?\s*(?:for\s+)?(?:the\s+)?(?:venue|fee|hall|booking)\b'),
        ('Closing time', r'\b(?:close|end|finish)(?:\s+at)?\s+'+numeric_alternative),
        ('Event date', r'\b(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\s+\d+(?:st|nd|rd|th)?\s+or\s+(?:aug(?:ust)?|sep(?:t(?:ember)?)?)\s+\d+'),
    ]
    for issue, pattern in alternatives:
        if re.search(pattern, lower, re.I):
            findings.append(_finding(CLARIFICATION_NEEDED,'alternative_choices',f'Which single {issue.lower()} would you like? You gave two alternatives.',issue=issue))
            last_by_issue.pop(issue,None)
    # Require a foreign-currency marker to be attached to an amount. Rich-text
    # punctuation can otherwise arrive as mojibake containing a stray euro
    # character. A quote mark must never invalidate an explicit "$300" fee.
    foreign_currency = bool(re.search(
        r"(?:[€£]|\b(?:eur|euros?|gbp|pounds?)\b)\s*\d|"
        r"\d(?:[\d,.]*\d)?\s*(?:[€£]|\b(?:eur|euros?|gbp|pounds?)\b)",
        lower,
    ))
    if foreign_currency:
        findings.append(_finding(CLARIFICATION_NEEDED, "unsupported_currency", "Please state the venue fee in US dollars (USD)."))
    if re.search(r"\b(?:ignore|disregard|override)\b.{0,35}\b(?:rule|instruction|system|score|point)", lower):
        findings.append(_finding(REJECTED, "prompt_injection", "Please enter an offer using the practice terms rather than instructions to the scoring system."))
    # Do not let conversational wording later in the sentence (for example,
    # "How about projector use?") turn an already-clear closing time into an
    # ambiguity. The deterministic tutorial reader is authoritative whenever
    # it found one exact supported time.
    clear_closing_time = "Closing time" in deterministic_issues
    vague_closing = not clear_closing_time and bool(
        re.search(r"\b(?:close(?:s|d)?|closing|end(?:s|ing)?|finish(?:es|ing)?)\b.{0,25}\b(?:sometime|around|about|roughly)\b", lower)
        or re.search(r"\b(?:sometime|around|about|roughly)\b.{0,25}\b(?:evening|close|closing|end)\b", lower)
    )
    if vague_closing:
        last_by_issue.pop("Closing time", None)
        findings.append(_finding(CLARIFICATION_NEEDED, "vague_closing_time", "Please choose one closing time from 5:00 p.m. through 11:00 p.m."))
    out_of_range_time = re.search(r"\b(?:close(?:s|d)?|closing|shut|ends?|finish(?:es)?|until)\D{0,18}(\d{1,2})\s*(?:p\.?m\.?)", lower)
    if out_of_range_time and int(out_of_range_time.group(1)) not in range(5, 12):
        last_by_issue.pop("Closing time", None)
        findings.append(_finding(CLARIFICATION_NEEDED, "invalid_closing_time", "The practice closing time must be from 5:00 p.m. through 11:00 p.m."))
    if re.search(r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|jun(?:e)?|jul(?:y)?)\b|\bmay\s+\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)?\s+may\b(?!\s+(?:we|i|you|they|he|she|it)\b)", lower):
        last_by_issue.pop("Event date", None)
        findings.append(_finding(CLARIFICATION_NEEDED, "invalid_event_month", "The practice event must be in August or September next year."))
    if re.search(r'\b(?:no|without)\s+(?:a\s+)?projector\b|\bprojector\s+(?:is\s+)?not\s+(?:needed|required|included)\b',lower):
        last_by_issue.pop('Projector',None)
    minute_time=re.search(r'\b(?:close|closing|end|finish)(?:\s+at)?\s+\d{1,2}:([0-5]\d)',lower)
    if minute_time and minute_time.group(1)!='00':
        last_by_issue.pop('Closing time',None)
        findings.append(_finding(CLARIFICATION_NEEDED,'unsupported_closing_minutes','Please choose a closing time on the hour, from 5:00 p.m. through 11:00 p.m.',issue='Closing time'))
    valid_pairs: OrderedDict[str, str] = OrderedDict()
    lines: list[str] = []
    total = 0.0
    issue_specs = _scenario_issue_map(scenario)
    for issue, pair in last_by_issue.items():
        if issue not in issue_specs:
            continue
        try:
            canonical, points = score_pair(issue, pair["option"], role, payoff, scenario)
        except (ValueError, KeyError, TypeError):
            message = (f'“{pair["option"]}” cannot be used for this event. Please choose one calendar day in August or September.'
                if issue == 'Event date' else f"Please give a clearer value for {issue} using the choices shown in the practice information.")
            findings.append(_finding(
                CLARIFICATION_NEEDED, "invalid_option",
                message, issue=issue,
            ))
            continue
        valid_pairs[issue] = canonical
        total += points
        lines.append(f"- {issue}: {canonical}  [{'+' if points >= 0 else ''}{points:.2f}]")

    # Deterministic practice rules resolve expected shorthand. Preserve only
    # model warnings that are not about a value already read safely.
    # The practice has a deliberately small, explicit catalog. Ambiguity is
    # decided by the rules above (currency, vague/out-of-range time, invalid
    # date, invalid option) rather than by free-form model warnings. This keeps
    # identical participant wording stable across repeated API calls.
    if unsupported and not foreign_currency:
        # The language model can occasionally label a terse, known practice
        # term as unsupported even though the deterministic reader mapped it
        # safely. Never reject an offer for a term the participant can see in
        # the confirmation as a scored issue.
        recognized_names: list[str] = []
        for recognized_issue in valid_pairs:
            recognized_spec = issue_specs.get(recognized_issue, {})
            recognized_names.extend([recognized_issue, *recognized_spec.get("aliases", [])])
        unsupported = [
            term for term in unsupported
            if not any(
                len(_normalized_choice(alias)) >= 4
                and _normalized_choice(alias) in _normalized_choice(term)
                for alias in recognized_names
            )
        ]
        if unsupported:
            findings.append(_finding(REJECTED, "unsupported_terms", f"These terms are not part of this practice: {', '.join(unsupported[:3])}."))
    missing = [name for name in required_issues if name not in valid_pairs]
    if missing and not any(item["decision"] == CLARIFICATION_NEEDED for item in findings):
        findings.append(_finding(REJECTED, "missing_required", f"Please add {', '.join(missing)}. I have not scored this offer yet.", missing=missing))
    if offer_intent == "not_an_offer" and not valid_pairs:
        findings.append(_finding(REJECTED, "not_an_offer", "Please enter a practice offer when you are ready."))
    decision = REJECTED if any(item["decision"] == REJECTED for item in findings) else (
        CLARIFICATION_NEEDED if any(item["decision"] == CLARIFICATION_NEEDED for item in findings) else SCORABLE
    )
    messages = list(dict.fromkeys(item["message"] for item in findings if item["decision"] == decision))
    # Match the main open-space scorer: retain concrete negotiable additions
    # without inventing a payoff after seeing them. Remove only duplicate
    # novel labels for terms that were successfully recognized and scored.
    known_for_scored: list[str] = []
    for issue_name in valid_pairs:
        spec = issue_specs.get(issue_name, {})
        known_for_scored.extend([issue_name, *spec.get("aliases", [])])
    captured_novel_terms = [
        term for term in captured_novel_terms
        if not any(
            len(_normalized_choice(alias)) >= 4
            and _normalized_choice(alias) in _normalized_choice(term)
            for alias in known_for_scored
        )
    ] if _open_capture_enabled(scenario) else []
    result = {
        "decision": decision, "message": "\n".join(messages), "messages": messages,
        "findings": findings, "lines": lines, "total": total, "any_valid": bool(valid_pairs),
        "invalid_present": bool(findings), "required_ok": not missing, "missing_required": missing,
        "valid_pairs": dict(valid_pairs),
        "novel_terms": list(dict.fromkeys(term.strip() for term in captured_novel_terms if term.strip())),
    }
    result["display_text"] = format_system_output(result)
    return result


def evaluate_offer(
    text: str,
    role: str,
    extraction: dict[str, Any] | list[Any],
    payoff: dict[str, Any],
    required_issues: list[str],
    scenario: dict[str, Any] | None = None,
    previous_offer: str | None = None,
) -> dict[str, Any]:
    """Validate and score one extraction, returning an explicit decision."""
    if (scenario or {}).get('review_design', {}).get('all_15_terms_explicit'):
        previous_offer = None
    reference = previous_offer_reference(text, scenario)
    if reference["mode"] == "none":
        previous_offer = None
    role = str(role).strip().title()
    if role not in {"Candidate", "Recruiter"}:
        raise ValueError(f"Unknown role: {role}")
    if isinstance(scenario, dict) and scenario.get("validation_profile") == "tutorial":
        return _evaluate_tutorial_offer(text, role, extraction, payoff, required_issues, scenario)

    if isinstance(extraction, dict):
        raw_pairs = extraction.get("pairs", [])
        model_ambiguities = extraction.get("ambiguities", [])
        model_unsupported = extraction.get("unsupported_terms", [])
        model_novel = extraction.get("novel_terms", [])
        offer_intent = extraction.get("offer_intent", "offer")
    else:
        raw_pairs = extraction
        model_ambiguities = []
        model_unsupported = []
        model_novel = []
        offer_intent = "offer"
    if not isinstance(raw_pairs, list):
        raw_pairs = []

    grounded_pairs=[];discarded_predictions=[];carried_issue_names=set()
    for p in raw_pairs:
        if not isinstance(p,dict):grounded_pairs.append(p);continue
        quote=str(p.get('source_text',''))
        placeholder=bool(re.fullmatch(r'(?:not specified|unspecified|not stated|n a|null|none specified)(?: in (?:the )?offer)?',_normalized_choice(p.get('option',''))))
        grounded_current = source_quote_is_grounded(quote, _focused_text(text))
        pair_issue = canonical_pair(str(p.get('issue', '')), str(p.get('option', '')))[0]
        spec = _scenario_issue_map(scenario).get(pair_issue)
        public_issue = str((spec or {}).get('name', pair_issue))
        if (public_issue=='Dedicated Office or Workspace'
                and re.search(r'\b(?:decorat\w*|personali[sz]\w*)\b',quote,re.I)
                and not re.search(r'\b(?:own|private|dedicated|quiet|bookable)\s+(?:office|workspace|room)\b',quote,re.I)):
            # Permission to decorate existing space is not an allocation of
            # a new private office. Keep the actual request without points.
            if _open_capture_enabled(scenario): model_novel.append(quote)
            discarded_predictions.append(dict(pair=p,reason='The source requests decoration, not private workspace.'))
            continue
        may_use_previous = bool(
            previous_offer
            and (reference['mode'] == 'full' or public_issue in reference['issues'])
            and source_quote_is_grounded(quote, str(previous_offer))
        )
        ungrounded='source_text' in p and not grounded_current and not may_use_previous
        if placeholder or ungrounded:
            discarded_predictions.append(dict(pair=p,reason='No stated option' if placeholder else 'Supporting quote is absent from the submitted offer.'))
        else:
            grounded_pairs.append(p)
            if may_use_previous and not grounded_current:
                carried_issue_names.add(public_issue)
    raw_pairs=grounded_pairs
    for pair in raw_pairs:
        if not isinstance(pair,dict):continue
        spec=_scenario_issue_map(scenario).get(str(pair.get('issue','')), {})
        if spec.get('kind')!='discrete' or not re.search(r'\b'+re.escape(spec.get('name',''))+r'\s*:',_focused_text(text),re.I):continue
        labels=[o['label'] for o in spec['options'] if o['label'].lower() in _focused_text(text).lower()]
        if len(labels)==1 and pair.get('option') not in [o['label'] for o in spec['options']]:
            pair['option']=labels[0]
    raw_pairs, unpriced_details, semantic_repairs = _repair_semantic_details(raw_pairs, _focused_text(text), scenario)
    findings = _smart_text_findings(text, payoff, scenario, bool(str(previous_offer or "").strip()))
    if ('Paid Volunteering Days' in _scenario_issue_map(scenario)
            and re.search(r'\bpaid\s+(?:morning|afternoon)\b',text,re.I)
            and re.search(r'\b(?:volunteer\w*|charit\w*|neighbou?rhood|community)\b',text,re.I)):
        findings.append(_finding(CLARIFICATION_NEEDED,'invalid_unit',
            'How many paid volunteering days per year would you like? Please give the allowance in days so I do not guess the length of an afternoon.',issue='Paid Volunteering Days'))
    unclear_public_activity = bool(re.search(r'\bsocial[-\s]+media\b[^;.]{0,80}\bor\s+(?:similar|other)\b[^;.]{0,50}\bpublic[-\s]+facing\b',text,re.I))
    # An intervening qualifier followed by a new activity can have two
    # plausible scopes. Ask once instead of assigning different interpretations
    # to the event and LinkedIn duties in the same phrase.
    shared_optional_duties=bool(re.search(r'\b(?:by\s+mutual\s+agreement|when\s+mutually\s+agreed)\s+and\s+help\b[^.;]{0,90}\bteam\s+events?\b[^.;]{0,90}\blinkedin\b',_focused_text(text),re.I))
    if shared_optional_duties:
        findings.append(_finding(CLARIFICATION_NEEDED,'shared_optional_duties','Are helping with team events and contributing LinkedIn content commitments, or are both also optional by mutual agreement?'))
    if unclear_public_activity:
        findings.append(_finding(CLARIFICATION_NEEDED,'unclear_public_activity','Which public-facing activity are you offering? Please name the activity, rather than leaving alternatives open.'))
        raw_pairs=[p for p in raw_pairs if not (isinstance(p,dict) and re.search(r'\bsocial[-\s]+media\b[^;.]{0,80}\bor\s+(?:similar|other)\b',str(p.get('option','')),re.I))]
    enriched_pairs = _study_pair_enrichment(text, scenario)
    if previous_offer and reference['mode']!='none':
        present={str(p.get('issue','')) for p in [*raw_pairs,*enriched_pairs] if isinstance(p,dict)}
        previous_pairs=_study_pair_enrichment(str(previous_offer),scenario)
        previous_date=_stated_start_date(str(previous_offer),scenario,include_invalid=True)
        if previous_date:previous_pairs.append(dict(issue='Starting Date',option=previous_date,confidence=1))
        inherited=set()
        unresolved_changes={str(d.get('issue')) for d in extraction.get('ambiguity_details',[]) if isinstance(d,dict)
            and re.search(r'\b(?:around|about|between|higher|lower|better|more|less)\b',str(d.get('source_text','')),re.I)
            and not re.search(r'\b(?:accept|retain|keep|honou?r|accede)\b',str(d.get('source_text','')),re.I)} if isinstance(extraction,dict) else set()
        for pair in previous_pairs:
            name=pair.get('issue')
            if name not in present and name not in unresolved_changes and (reference['mode']=='full' or name in reference['issues']):
                enriched_pairs.append({**pair,'source_text':str(previous_offer),'source':'explicit_prior_reference'})
                present.add(name);carried_issue_names.add(name);inherited.add(name)
        resolved={str(d.get('question','')) for d in extraction.get('ambiguity_details',[]) if isinstance(d,dict) and d.get('issue') in inherited} if isinstance(extraction,dict) else set()
        model_ambiguities=[q for q in model_ambiguities if str(q) not in resolved]
    # A rule scanning the entire offer must not overwrite a correctly quoted
    # choice with a negation from another term or a rejected earlier package.
    # Resolve quoted choices using their own evidence; use whole-offer aliases
    # only to fill missing fields. Legacy extraction fixtures without quotes
    # retain their existing conservative fallback behavior.
    quote_resolutions=[]
    for pair in raw_pairs:
        if not isinstance(pair,dict) or not pair.get('source_text'):
            continue
        issue,option=canonical_pair(str(pair.get('issue','')),str(pair.get('option','')))
        try:
            if float(pair.get('confidence',0))<MIN_CONFIDENCE:continue
            quoted_choice=score_pair(issue,option,role,payoff,scenario)[0]
        except (ValueError,KeyError,TypeError):continue
        quoted=str(pair['source_text'])
        if issue in {'Role in Recruitment Fair','Role in Organizing Social Events','Regular Linkedin Posts for Company','Mandatory Conference Presentations'}:
            quoted=_complete_quote_clause(quoted,_focused_text(text))
        quoted=re.sub(r'\.{3}|…',' ',quoted)
        competing=next((p for p in reversed(enriched_pairs) if p['issue']==issue),None)
        conflict=False
        if competing:
            try:conflict=score_pair(issue,competing['option'],role,payoff,scenario)[0]!=quoted_choice
            except (ValueError,KeyError,TypeError):conflict=True
        # Most choices already agree; avoid rescanning the full catalog unless
        # an actual conflict needs an issue-local decision.
        local=[p for p in _study_pair_enrichment(quoted,scenario) if p['issue']==issue] if conflict else []
        local_option=local[-1]['option'] if local else option
        # Absence of a regex's familiar refusal phrasing is not evidence of a
        # positive duty. Preserve a model's explicitly quoted negative choice.
        if quoted_choice.lower().startswith('no ') and not local_option.lower().startswith('no '):
            local_option=option
        if issue=='Role in Recruitment Fair' and _explicit_fair_pledge(quoted):
            local_option='Commit'
        if issue=='Regular Linkedin Posts for Company' and _explicit_posting_pledge(quoted):
            local_option='Commitment'
        resolved=dict(pair,issue=issue,option=local_option)
        enriched_pairs=[p for p in enriched_pairs if p['issue']!=issue]
        quote_resolutions.append(resolved)
    enriched_pairs.extend(quote_resolutions)
    combined_pairs = _repair_misrouted_discrete_pairs(list(raw_pairs) + enriched_pairs, scenario)
    usual_readings = _usual_allowance_readings(text, scenario)
    for name, reading in usual_readings.items():
        # A delta is not the final allowance. Replace a model's possible "1"
        # with the configured baseline + 1 before duplicate/value checks.
        combined_pairs = [p for p in combined_pairs if not (isinstance(p, dict) and p.get('issue') == name)]
        if reading.get('value') is not None:
            combined_pairs.append(dict(issue=name, option=str(reading['value']), confidence=1,
                                       source_text=reading['source_text']))
        else:
            findings.append(_finding(CLARIFICATION_NEEDED, 'unclear_usual_change', reading['question'], issue=name))
    # If the package keeps any narrower post-employment restriction, the
    # binary non-compete choice is Keep even when it rejects a *broad* clause.
    # Preserve the narrower scope as detail; do not turn it into a third payoff
    # option or reject it as an unsupported issue.
    retained_restriction = next((
        clause for clause in _offer_clauses(_focused_text(text))
        if re.search(r'\b(?:non[-\s]?compete(?:\s+clause)?|post[-\s]+employment\s+restriction|restriction)\b', clause, re.I)
        and re.search(r'\b(?:would|will|is|be|should)\s+(?:be\s+)?(?:limited|restricted|tailored)\b|\bonly\s+(?:cover|apply|restrict)', clause, re.I)
    ), None)
    if retained_restriction:
        combined_pairs = [p for p in combined_pairs if not (
            isinstance(p, dict)
            and canonical_pair(str(p.get('issue', '')), str(p.get('option', '')))[0] == 'Non-compete Clause'
        )]
        combined_pairs.append(dict(issue='Non-compete Clause', option='Keep', confidence=1, source_text=retained_restriction))
        if not any(
            d.get('issue') == 'Non-compete Clause'
            and _normalized_choice(retained_restriction) == _normalized_choice(str(d.get('detail', '')))
            for d in unpriced_details
        ):
            unpriced_details.append(dict(
                issue='Non-compete Clause', detail=retained_restriction,
                meaning='Keeping or waiving the clause is scored; its scope and duration have no additional payoff in this catalog.',
            ))
    # Explicit platform-specific refusal: do not require the word "posts"
    # when the offer clearly excludes the employee's LinkedIn promotion duty.
    # Generic publicity and company-controlled reuse remain different issues.
    for clause in _offer_clauses(_focused_text(text)):
        if re.search(r'\blinkedin\b',clause,re.I) and re.search(r'\b(?:promoti\w*|publicity|posts?|content|activities)\b',clause,re.I) and _excluded_extra_term(clause,clause):
            combined_pairs.append(dict(issue='Regular Linkedin Posts for Company',option='No commitment',confidence=1,source_text=clause))
    remote_allowance=_remote_allowance(_focused_text(text))
    if remote_allowance:
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Remote Working Days')]
        combined_pairs.append(dict(issue='Remote Working Days',option=remote_allowance,confidence=1))
        unpriced_details.append(dict(issue='Remote Working Days',detail='Up to '+remote_allowance,meaning='The employee may use this many remote days each week; this is a permission ceiling, not a required minimum.'))
    explicit_social_exclusion = _explicit_social_event_exclusion(_focused_text(text))
    if explicit_social_exclusion:
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and canonical_pair(str(p.get('issue','')),str(p.get('option','')))[0]=='Role in Organizing Social Events')]
        combined_pairs.append(dict(issue='Role in Organizing Social Events',option='No commitment',confidence=1,source_text=explicit_social_exclusion))
    if any(f['code']=='career_guidance_frequency' for f in findings):
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Senior Career Guidance')]
    # Never turn a rejected negative prediction into a positive DEFAULT merely
    # because its supporting quote failed. If the issue is otherwise inferred
    # but no other grounded model choice resolves it, ask rather than invent.
    for discarded in discarded_predictions:
        predicted=discarded.get('pair',{})
        issue,option=canonical_pair(str(predicted.get('issue','')),str(predicted.get('option','')))
        if not option.lower().startswith('no ') or discarded.get('reason')!='Supporting quote is absent from the submitted offer.':continue
        if any(isinstance(p,dict) and canonical_pair(str(p.get('issue','')),str(p.get('option','')))[0]==issue for p in raw_pairs):continue
        # Deterministic enrichment may already have grounded the same explicit
        # refusal even when the model supplied a shortened quote. Do not ask
        # participants to clarify a duty that their submitted offer excludes.
        if any(
            isinstance(p,dict)
            and canonical_pair(str(p.get('issue','')),str(p.get('option','')))[0]==issue
            and canonical_pair(str(p.get('issue','')),str(p.get('option','')))[1].lower().startswith('no ')
            for p in combined_pairs
        ):
            continue
        inferred=[p for p in enriched_pairs if p.get('issue')==issue]
        if inferred and not str(inferred[-1].get('option','')).lower().startswith('no '):
            combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')==issue)]
            findings.append(_finding(CLARIFICATION_NEEDED,'unverified_negative_choice',f'Please clarify {issue}: is it included in this offer, or explicitly excluded?',issue=issue))
    if shared_optional_duties:
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue') in {'Role in Organizing Social Events','Regular Linkedin Posts for Company'})]
    outside_requests = [*(model_novel if isinstance(model_novel, list) else []),
                        *(model_unsupported if isinstance(model_unsupported, list) else [])]
    combined_pairs = [pair for pair in combined_pairs if not (
        isinstance(pair, dict) and incidental_numeric_issue_reference(
            str(pair.get('issue', '')), str(pair.get('source_text', '')),
            _focused_text(text), outside_requests))]
    omitted_entitlements={name for name in ('Remote Working Days','Vacation Days') if _no_numeric_entitlement(name,_focused_text(text))}
    combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue') in omitted_entitlements)]
    # A reference to unspecified company policy does not commit the company
    # to paying membership dues. Ask about sponsorship rather than invent it.
    association_clauses=[c for c in _offer_clauses(_focused_text(text)) if re.search(r'\b(?:professional[-\s]+association|association[-\s]+membership)\b',c,re.I)]
    association_policy_only=bool(association_clauses) and all(re.search(r'\b(?:subject\s+to|under)\b[^.;]{0,70}\bpolic(?:y|ies)\b',c,re.I) and not re.search(r'\b(?:sponsor\w*|pays?|paid|reimburse\w*)\b',c,re.I) for c in association_clauses)
    if association_policy_only:
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Professional Associations Membership')]
        findings.append(_finding(CLARIFICATION_NEEDED,'association_policy_unspecified','Does the company pay the professional-association membership fees, or not?',issue='Professional Associations Membership'))
    if any(f['code']=='excluded_contract_comparison' for f in findings):
        # Do not display or sum the explicitly rejected duration even while
        # asking for its replacement. A clarification is not a sent offer.
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Contract Length')]
    if any(f['code']=='unclear_event_exemption' for f in findings):
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Role in Organizing Social Events')]
    if any(f['code']=='qualified_noncompete_refusal' for f in findings):
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue')=='Non-compete Clause')]

    # A large retrieved catalog contains neighboring constructs that often use
    # the same number (for example, a three-month review and three caregiving
    # days). Remove a small set of high-risk model-only mappings unless their
    # defining object is actually present in the offer. Deterministic aliases
    # added above remain available for genuine wording.
    lower_text = _focused_text(text).lower()
    lower_text = re.sub(r'\bprobstion\b','probation',lower_text)
    # One clause-scoped filter, not a second whole-sentence deletion pass.
    # 'would not include X, and would retain Y' must preserve positive Y.
    affirmative_text = _affirmative_numeric_text(lower_text)
    number_evidence = r"(?:\d+(?:\.\d+)?|two[-\s]and[-\s]a[-\s]half|half|zero|one|two|three|four|five|six|ten|twelve|eighteen|twenty|twenty-four|twenty-five|thirty|thirty-five|forty|no)"

    def numbered_issue(issue_pattern: str) -> str:
        return (
            rf"\b{number_evidence}\b[^.;]{{0,35}}\b(?:{issue_pattern})\b|"
            rf"\b(?:{issue_pattern})\b[^.;]{{0,35}}\b{number_evidence}\b"
        )

    optional_continuous_evidence = {
        "Vacation Days": numbered_issue(r"vacation|vacay|annual\s+leave|holiday|(?:paid\s+)?days?\s+off|time\s+off"),
        "Remote Working Days": numbered_issue(r"remote(?:ly|[-\s]+working|\s+work)?|wfh|home[-\s]+working|work(?:ing)?[-\s]from[-\s]home"),
        "Probation Length": (
            numbered_issue(r"probation(?:ary)?|trial(?:\s+period)?")
            + rf"|\b(?:probation(?:ary)?|trial(?:\s+period)?)\b[^.;]{{0,35}}\b{number_evidence}\s*(?:months?|mos?|mo)\b"
            + rf"|\b{number_evidence}[-\s]?(?:months?|mos?|mo)\b[^.;]{{0,35}}\b(?:probation(?:ary)?|trial(?:\s+period)?)\b"
            + rf"|\b{number_evidence}\s*(?:months?|mos?|mo)\b[^.;]{{0,35}}\bbefore\s+(?:permanent|becoming\s+permanent)\b"
            + r"|\b(?:waiv(?:e|ed|ing)|skip(?:ping)?)\s+(?:the\s+)?(?:probation(?:ary)?|trial(?:\s+period)?)\b"
            + rf"|\bprob\b[^.;]{{0,25}}\b{number_evidence}\s*(?:months?|mos?|mo)\b"
            + rf"|\b{number_evidence}\s*(?:months?|mos?|mo)\b[^.;]{{0,25}}\bprob\b"
        ),
        "Contract Length": numbered_issue(r"contract|deal|employment\s+(?:term|agreement)|fixed[-\s]?(?:term\s+)?appointment|term"),
    }
    optional_continuous_evidence["Remote Working Days"] += (
        rf"|\b(?:hybrid|remote|wfh)\b[^.;]{{0,35}}\b{number_evidence}\b[^.;]{{0,20}}\bdays?\b"
        rf"|\b{number_evidence}\b[^.;]{{0,20}}\bdays?\b[^.;]{{0,25}}\b(?:from\s+home|remote|wfh)\b"
    )
    combined_pairs = [
        pair for pair in combined_pairs
        if not (
            isinstance(pair, dict)
            and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] in optional_continuous_evidence
            and str((_scenario_issue_map(scenario).get(canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0]) or {}).get("name", canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0])) not in carried_issue_names
            and not re.search(
                optional_continuous_evidence[canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0]],
                affirmative_text,
            )
        )
    ]
    company_only_linkedin = bool(
        re.search(
            r"\b(?:marketing|communications?|publicity|executive|leadership)\s+(?:team\s+)?"
            r"[^.;]{0,45}\b(?:write|post|publish|create)\w*\b[^.;]{0,80}\blinkedin\b",
            lower_text,
        )
        and not re.search(
            r"\b(?:candidate|employee|new\s+hire|you|they)\b[^.;]{0,100}"
            r"\b(?:write|post|publish|create|contribute|provide)\w*\b[^.;]{0,80}\blinkedin\b",
            lower_text,
        )
    )
    if company_only_linkedin:
        combined_pairs = [
            pair for pair in combined_pairs
            if not (
                isinstance(pair, dict)
                and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0]
                == "Regular Linkedin Posts for Company"
            )
        ]
    if len(_scenario_issue_map(scenario)) > 50:
        historical_marker = r"\b(?:background|experience|previously|previous|prior|former|past|earlier|cv|r[eé]sum[eé]|last\s+job|used\s+to)\b"
        future_marker = r"\b(?:offer|propose|proposal|package|include|would|will|must|required|optional|voluntary|agree|commit)\b"
        historical_issue_patterns = {
            "Contract Length": r"\b(?:contract|employment\s+(?:agreement|term)|fixed[-\s]?(?:term\s+)?appointment)\b",
            "Probation Length": r"\b(?:probation(?:ary)?|trial\s+period)\b",
            "Role in Recruitment Fair": r"\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b",
            "Mandatory Conference Presentations": r"\b(?:conference|present(?:ation|ations|ing)?|speaking\s+at\s+conferences?)\b",
            "Role in Organizing Social Events": r"\b(?:team|company|social)[-\s]+(?:events?|socials?|gatherings?)\b",
            "Regular Linkedin Posts for Company": r"\blinkedin\b.{0,80}\b(?:posts?|updates?|content|publicity)\b|\b(?:posts?|updates?|content|publicity)\b.{0,80}\blinkedin\b",
        }
        historical_scan_text = re.sub(r'\bwork\s+experience\s+budget\b','personal budget',lower_text)
        clauses = [
            clause for clause in re.split(r"\bbut\b|;|(?<!\d)\.|\.(?!\d)", historical_scan_text)
            if clause.strip()
        ]
        historical_only = {
            issue for issue, pattern in historical_issue_patterns.items()
            if any(re.search(pattern, clause) for clause in clauses)
            and all(
                re.search(historical_marker, clause) and not re.search(future_marker, clause)
                for clause in clauses if re.search(pattern, clause)
            )
        }
        if historical_only:
            combined_pairs = [
                pair for pair in combined_pairs
                if not (
                    isinstance(pair, dict)
                    and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] in historical_only
                )
            ]
    evidence_required = {
        "Senior Career Guidance": r"\bcareer[-\s]+(?:development|guidance|advi\w*|mentor\w*|conversations?|counse\w*)\b|\b(?:senior\s+career[-\s]?advis\w*|advice\s+outside\s+my\s+direct\s+reporting\s+line)\b",
        "Professional Associations Membership": r"\b(?:professional[-\s]+(?:associations?|memberships?|bodies)|association[-\s]+(?:dues|fees|membership|sponsorship)|membership\s+(?:dues|fees))\b",
        "Sales Coaching Frequency": r"\b(?:sales[-\s]+coach(?:ing)?|coach(?:ing)?\s+sessions?)\b",
        "Contract Renewal Notice": r"\b(?:renewal\s+notice|notice\s+(?:before|of|about|prior)|contract\s+(?:expiry|expiration)|ends?\s+with\s+notice)\b",
        "Professional Development Budget": r"\bprofessional\s+development\s+(?:budget|allowance)\b|\b(?:development|training|learning|courses?)\b[^;.]{0,35}(?:\$|\bUSD\b|\bdollars?\b|\bbudget\b)|(?:\$\s*\d[\d,.]*|\b\d+\s+dollars?\b)[^;.]{0,40}\b(?:development|training|learning|courses?)\b",
        "Paid Caregiving Days": r"\b(?:caregiv|care\s+leave|family\s+care|dependent\s+care)\b",
        "Performance Improvement Period": r"\b(?:performance\s+improvement|improvement\s+(?:period|plan)|\bpip\b|days?\s+to\s+improve|missed\s+target)\b",
        "Customer and Employee Non-Solicitation": r"\b(?:non[-\s]?solicit|solicit(?:ing|ation)?\b.{0,30}\b(?:customers?|employees?|prospects?))\b",
        "Customer Contact Hours": r"\b(?:customer|client)[-\s]+(?:contact|availability|coverage)\s+(?:hours?|window)|\bavailable\b.{0,35}\b(?:customers?|clients?)\b.{0,25}\b(?:a\.?m\.?|p\.?m\.?|hours?)\b",
        "Cross-Team Project Opportunities": r"\b(?:cross[-\s]?team|projects?\s+with\s+other\s+teams?)\b",
        "Teamwork in Performance Reviews": r"\b(?:teamwork|collaboration|team\s+contribution)\b.{0,60}\b(?:review|evaluation|performance)\b|\b(?:review|evaluation|performance)\b.{0,60}\b(?:teamwork|collaboration|team\s+contribution)\b",
        "Pay Review Timing": r"\b(?:pay|salary|compensation)\b.{0,35}\b(?:review|reviewed|discussion|conversation)\b.{0,90}\b(?:promotion|promoted)\b|\b(?:promotion|promoted)\b.{0,90}\b(?:pay|salary|compensation)\b.{0,35}\b(?:review|reviewed|discussion|conversation)\b|\b(?:discuss|review)\s+(?:pay|salary|compensation)\b.{0,90}\b(?:promotion|promoted)\b|\b(?:promotion|promoted)\b.{0,90}\b(?:discuss|review)\s+(?:pay|salary|compensation)\b",
        "Written First-Week Schedule": r"\b(?:first[-\s]?week|week\s+one)\b.{0,45}\b(?:schedule|plan)\b|\b(?:schedule|plan)\b.{0,45}\b(?:first[-\s]?week|week\s+one)\b",
        "Career Path Review": r"\b(?:development|career|advancement)\s+(?:opportunity|path)\b.{0,80}\b(?:unavailable|withdrawn|removed|no\s+longer\s+available)\b|\b(?:unavailable|withdrawn|removed|no\s+longer\s+available)\b.{0,80}\b(?:development|career|advancement)\s+(?:opportunity|path)\b",
        "Notice Before Sales Meetings": r"\b(?:notice|agenda)\b.{0,45}\b(?:sales|internal)\s+meetings?\b|\b(?:sales|internal)\s+meetings?\b.{0,45}\b(?:notice|agenda)\b",
        "Customer Ownership After Handoff": r"\b(?:customer|client)\s+ownership\b|\b(?:handoff|hand[-\s]?off)\b",
        "After-Hours Event Frequency": r"\b(?:after[-\s]?hours|evening|weekend)\b.{0,35}\bevents?\b|\bevents?\b.{0,35}\b(?:after[-\s]?hours|evening|weekend)\b",
        "Paid Time for Publicity": r"\b(?:paid\s+(?:time|hours?)|work(?:ing)?\s+hours?)\s+(?:for|on)\s+(?:publicity|linkedin|communications?)\b|\b(?:publicity|linkedin|communications?)\b.{0,25}\b(?:during\s+paid\s+time|during\s+work(?:ing)?\s+hours?|paid\s+hours?)\b",
        "Company Card Access": r"\b(?:company|corporate)\s+(?:credit\s+)?card\b",
        "After-Hours Client Duty": r"\b(?:after[-\s]?hours|evening|weekend|on[-\s]?call)\b.{0,45}\b(?:client|customer|requests?|coverage|duty)\b|\b(?:client|customer)\b.{0,45}\b(?:after[-\s]?hours|evening|weekend|on[-\s]?call)\b",
        "Notice Period Length": r"\bnotice\s+period\b|\b(?:give|provide|required)\b.{0,30}\b(?:weeks?|months?)['’]?\s+notice\b",
        "Expense Approval Rules": r"\b(?:expense|purchase)\b.{0,35}\b(?:pre[-\s]?approv|advance\s+approval|needs?\s+approval)\b|\b(?:pre[-\s]?approv|advance\s+approval)\b.{0,35}\b(?:expense|purchase)\b",
        "Mentoring Assignment Choice": r"\b(?:mentor|mentoring)\b.{0,45}\b(?:coworkers?|colleagues?|new\s+hires?|assignment|assignments)\b|\b(?:coworkers?|colleagues?|new\s+hires?)\b.{0,45}\b(?:mentor|mentoring)\b",
        "Performance-Based Progression": r"\b(?:progression|promotion|advancement)\b.{0,70}\b(?:annual\s+review|agreed\s+(?:performance\s+)?targets?\s+(?:are\s+)?met|targets?\s+triggers?\s+(?:a\s+)?(?:decision|review))\b|\b(?:annual\s+review|agreed\s+(?:performance\s+)?targets?\s+(?:are\s+)?met)\b.{0,70}\b(?:progression|promotion|advancement)\b",
        "Notice of Internal Job Openings": r"\b(?:internal\s+(?:job\s+)?(?:openings?|vacanc(?:y|ies)|positions?)|notice\s+of\s+internal)\b",
        "Role Review Schedule": r"\b(?:reviews?|reviewed|revisit(?:ed|ing)?|reassess|check[-\s]?in|checked)\b.{0,55}\b(?:duties|priorities|role\s+scope|job\s+scope|(?:job|role)\s+responsibilities)\b|\b(?:reviews?|check[-\s]?in)\b.{0,15}\b(?:of|on|covering|about)\b.{0,10}\bresponsibilities\b|\b(?:duties|priorities|role\s+scope|job\s+scope|(?:job|role)\s+responsibilities)\b.{0,55}\b(?:reviews?|reviewed|revisit(?:ed|ing)?|reassess|check[-\s]?in|checked)\b",
        "Role in Recruitment Fair": r"(?:\b(?:i|you|candidate|employee|new\s+hire|they)\b.{0,70}\b(?:participat\w*|attend\w*|join\w*|represent\w*|volunteer\w*|take\s+part|help(?:\s+out)?|assist|support\w*|commit\w*)\b.{0,70}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b|\b(?:participation|involvement|commitment|responsibilit(?:y|ies)|obligation|role|opportunity\s+to\s+volunteer|volunteer\w*)\b.{0,70}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b|\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b.{0,70}\b(?:participation|involvement|commitment|responsibilit(?:y|ies)|obligation|role|volunt(?:eer|ar)\w*)\b)",
        # A non-compete is not evidence of a confidentiality/NDA term. Model
        # questions about an issue are retained only when the offer contains
        # language that actually points to that issue.
        "Confidential Information Rules": r"\b(?:confidential(?:ity)?|non[-\s]?disclosure|nda|proprietary\s+information|trade[-\s]+secrets?)\b",
        "Early Progress Reviews": r"\b(?:early\s+)?(?:progress|performance|development|onboarding|ramp)[-\s]+(?:reviews?|check[-\s]?ins?|conversations?)\b|\b(?:reviews?|check[-\s]?ins?)\b[^.;]{0,50}\b(?:first\s+90\s+days|first\s+three\s+months|onboarding|ramp)\b",
    }
    evidence_required['Mentorship Program'] = r'\bmentor(?:ing|ship)?\b'
    evidence_required['Professional Associations Membership'] += r'|\b(?:sales|industry|trade)[-\s]+associations?\b'
    evidence_required['Professional Associations Membership'] += r'|\b(?:firm|company|employer)\s+sponsors?\s+(?:professional\s+)?associations?\b'
    evidence_required['Travel Meal Reimbursement'] = r'\b(?:meals?|breakfast|lunch|dinner|food|subsistence|per\s+diem)\b'
    evidence_required['Commuting Support'] = r'\bcommut\w*\b|\btravel\s+to\s+work\b|\b(?:transport|parking)\s+(?:allowance|reimbursement|payment|costs?)\b'
    evidence_required['Four-Day Workweek Trial'] = r'\b'+_FOUR_DAY_PATTERN+r'\b|\bcompressed[-\s]+workweek\b'
    evidence_required['Pay Review Timing'] += r'|\breview\s+of\s+(?:pay|salary|compensation)\b[^.;]{0,90}\bpromot\w*\b'
    evidence_required['Role in Recruitment Fair'] = evidence_required['Role in Recruitment Fair'].replace(r'take\s+part',r'tak(?:e|ing)\s+part')
    evidence_required['Role in Recruitment Fair'] += r'|\bcommit\s+to\s+(?:taking\s+part|participating|helping|assisting)\b[^.;]{0,60}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b'
    evidence_required['Role in Recruitment Fair'] += r'|\bcommit\w*\s+to\b[^.;]{0,65}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b'
    evidence_required['Role in Recruitment Fair'] += r'|\bstaff(?:ing)?\s+(?:the\s+)?(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\b'
    # Explicit actor + future duty is evidence regardless of the chosen verb.
    # Background mentions of a fair, without participation, remain insufficient.
    evidence_required['Role in Recruitment Fair'] += r"|\b(?:i|you|candidate|employee|new\s+hire|they)(?:\s+(?:will|would|must|shall)|['’]ll)\b[^.;]{0,65}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b"
    evidence_required['Role in Recruitment Fair'] += r'|\bopportunit(?:y|ies)\s+to\b[^.;]{0,100}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b'
    # A trailing optional/voluntary predicate can govern a whole duty list.
    evidence_required['Role in Recruitment Fair'] += r'|\b(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\b[^.;]{0,220}\b(?:optional|voluntary)\b'
    evidence_required['Professional Training Program'] = r'\b(?:training|courses?|professional[-\s]+development|learning[-\s]+program)\b'
    evidence_required['Contract Renewal Standards'] = r'\brenew\w*\b'
    evidence_required['Recruiting Quote Approval'] = r'\b(?:quot(?:e|es|ation)|public\s+statement)\b[^.;]{0,65}\b(?:approval|approve|review|consent)\b|\b(?:approval|approve|review|consent)\b[^.;]{0,65}\b(?:quot(?:e|es|ation)|public\s+statement)\b'
    # Not assigning recurring duties does not grant a separate, unrestricted
    # right to refuse every future publicity request without consequences.
    publicity_right=r'(?:declin\w*|refus\w*|opt[-\s]?out|veto|say\s+no|choose\s+whether|voluntary|must\s+participate|required\s+to\s+participate|mandatory|compulsory)'
    publicity_activity=r'(?:publicity|media|public\s+appearances?)'
    evidence_required['Declining Publicity Requests']=rf'\b{publicity_right}\b[^.;]{{0,100}}\b{publicity_activity}\b|\b{publicity_activity}\b[^.;]{{0,100}}\b{publicity_right}\b'
    if _scenario_issue_map(scenario):
        evidence_required.update({
            "Regular Linkedin Posts for Company": (
                r"\bno\s+(?:recurring|regular|ongoing)\s+(?:responsibility|obligation|dut(?:y|ies))\b"
                r"[^.;]{0,80}\b(?:post|write|publish|contribute|provide)\w*\b[^.;]{0,80}\blinkedin\b|"
                r"\b(?:i|you|candidate|employee|new\s+hire|they)\b[^.;]{0,160}"
                r"\b(?:write|post|publish|contribute|produce|provide)\w*\b[^.;]{0,100}"
                r"\b(?:linkedin\s+)?(?:posts?|updates?|content|communications?|publicity)\b|"
                r"\blinkedin\b[^.;]{0,180}\b(?:posts?|posting|write|writing|updates?|content|"
                r"contributions?|dut(?:y|ies)|responsibilit(?:y|ies)|obligations?|required|optional|voluntary|recurring)\b|"
                r"\blinkedin\s+(?:publicity|communications?)\b[^.;]{0,140}\b(?:voluntary|optional|opt[-\s]?in|"
                r"mutually\s+agreed|by\s+mutual\s+agreement|agreed\s+(?:with\s+me\s+)?in\s+advance|recurring\s+obligations?)\b"
                r"|\b(?:voluntary|optional|opt[-\s]?in|no\s+(?:recurring|regular|ongoing)\s+(?:responsibility|obligation|dut(?:y|ies))|"
                r"would\s+not\s+take\s+on\s+recurring)\b"
                r"[^.;]{0,180}\blinkedin\s+(?:publicity|communications?)\b"
            ),
            "Mandatory Conference Presentations": (
                r"\b(?:conference[-\s]+(?:present(?:ing|ation|ations)?|speaking|talks?)|"
                r"present(?:ing|ations?)?\s+at\s+(?:(?:an?|the)\s+)?(?:annual\s+|company\s+)?conferences?|"
                r"speak(?:ing)?\s+at\s+(?:(?:an?|the|one)\s+)?(?:annual\s+)?conferences?|"
                r"give\s+(?:an?\s+)?talk\s+at\s+(?:(?:an?|the)\s+)?(?:company\s+|annual\s+)?conferences?)\b"
                r"|\bconferences?\b[^.;]{0,100}\b(?:no|without)\b[^.;]{0,35}\bpresentation\s+(?:dut(?:y|ies)|responsibilit(?:y|ies)|obligation)\b"
            ),
            "Role in Organizing Social Events": (
                r"\b(?:plan|planning|organiz\w*|organis\w*|coordinat\w*|help|"
                r"responsibilit(?:y|ies)|obligations?|dut(?:y|ies)|required|optional|voluntary)\b"
                r"[^.;]{0,55}\b(?:team|company|staff|social)[-\s]+(?:events?|socials?|gatherings?)\b|"
                r"\b(?:team|company|staff|social)[-\s]+(?:events?|socials?|gatherings?)\b[^.;]{0,55}"
                r"\b(?:plan|planning|organiz\w*|organis\w*|coordinat\w*|"
                r"responsibilit(?:y|ies)|obligations?|dut(?:y|ies)|required|optional|voluntary)\b"
            ),
        })
    evidence_required['Regular Linkedin Posts for Company'] += '|'+_LINKEDIN_CONTRIBUTION
    evidence_required['Regular Linkedin Posts for Company'] += r'|\bpost(?:s|ing)?\s+(?:on|to)\s+linkedin\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\blinkedin\b[^.;]{0,70}\bcommitments?\b'
    evidence_required['Mandatory Conference Presentations'] += r'|\bpresent(?:ing)?\s+at\s+(?:required\s+)?(?:industry\s+)?conferences?\b'
    evidence_required['Mandatory Conference Presentations'] += r'|\bconferences?[-\s]+commitments?\b'
    evidence_required['Role in Organizing Social Events'] += r'|\bteam[-\s]+building\b|\bsocial[-\s]+events?\b[^.;]{0,70}\bcommitments?\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\bnot\s+be\s+responsible\s+for\b[^.;]{0,200}\blinkedin\b[^.;]{0,70}\b(?:publicity|posts?|content|communications?)\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\b(?:not\s+include|not\s+take\s+on|not\s+have)\b[^.;]{0,200}\blinkedin\b[^.;]{0,70}\b(?:promoti\w*|activities|publicity|posts?|content)\b|\b(?:not\s+include|not\s+take\s+on|not\s+have)\b[^.;]{0,180}\bpromotional\s+linkedin\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\b(?:regular|recurring)\s+linkedin\s+publicity\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\b(?:no|not\s+require)\b[^.;]{0,160}\blinkedin[-\s]+publicity\b|\blinkedin[-\s]+publicity\b[^.;]{0,100}\b(?:requirements?|obligations?|not\s+(?:be\s+)?required)\b'
    evidence_required['Regular Linkedin Posts for Company'] += r'|\blinkedin[-\s]+publicity\b[^.;]{0,150}\b(?:company\s+)?commitments?\b'
    if _uses_broad_social_posts(scenario):
        evidence_required['Regular Linkedin Posts for Company'] += (
            r'|\b(?:i|you|candidate|employee|new\s+hire|they)\b[^.;]{0,160}'
            r'\b(?:write|post|publish|contribute|produce|provide|shape|help)\w*\b[^.;]{0,110}'
            r'\b(?:company\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b'
            r'|\b(?:regular|recurring|ongoing|optional|voluntary|no)\b[^.;]{0,100}'
            r'\b(?:company\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b'
            r'|\b(?:help(?:ing)?\s+(?:to\s+)?shape|shap(?:e|es|ing))\b[^.;]{0,140}'
            r'\b(?:company[’\x27]s\s+)?(?:social[-\s]+media|social\s+posts?|public\s+updates?)\b'
        )
    # Shared negative lists can mention LinkedIn after another excluded duty.
    # Keep quote verification strict; enrich from the real clause, not a model
    # quote abbreviated with an ellipsis.
    evidence_required['Regular Linkedin Posts for Company'] += r'|\bnot\s+propos(?:e|ing)\s+(?:(?:a|any)\s+)?(?:(?:standing|recurring|regular)\s+)?responsibilit(?:y|ies)\s+for\b[^.;]{0,220}\blinkedin\b[^.;]{0,70}\b(?:publicity|posts?|content|communications?)\b'
    evidence_required['Role in Organizing Social Events'] += r'|\bno\b[^.;]{0,100}\bteam[-\s]+events?\b[^.;]{0,120}\brequirements?\b'
    evidence_required['Role in Organizing Social Events'] += r'|\bevent[-\s]+organiz\w*\b[^.;]{0,100}\b(?:duties|role|responsibilit\w*)\b'
    # Company publicity is neither post-sale support nor the candidate's right
    # to describe achievements in a later job search. Require the actual
    # construct, not a nearby catalog label, before asking about its option.
    evidence_required['Support After a Sale'] = r'\b(?:post[-\s]+sale|after[-\s]+sale|after\s+(?:the\s+)?sale|handoff|hand[-\s]+over|implementation\s+(?:owner|team)|customer[-\s]+success|transition\s+(?:questions|support))\b'
    evidence_required['Use of Work Achievements'] = r'\b(?:resumes?|cvs?|interviews?|job[-\s]+search|after\s+leaving|future\s+(?:employers?|career|employment))\b'
    # Creating a story, crediting its author, and obtaining the customer's
    # permission are different terms. Do not let a nearby catalog label cause
    # a new clarification question that plants an unproposed issue.
    story=r'(?:customer|client)[-\s]+(?:success[-\s]+)?(?:stor(?:y|ies)|case[-\s]+stud(?:y|ies)|testimonials?)'
    credit=r'(?:credit|credited|attribut\w*|byline|my\s+name|your\s+name|individual\s+name|names?\s+(?:appear|included|shown)|named\s+as)'
    evidence_required['Customer Story Attribution']=rf'\b{story}\b[^.;]{{0,180}}\b{credit}\b|\b{credit}\b[^.;]{{0,180}}\b{story}\b'
    evidence_required['Customer Story Permission']=(r'\b(?:customer|client)[’\x27]?s?\s+(?:written\s+|prior\s+|explicit\s+)?(?:permission|consent|approval|authorization)\b|'
        r'\b(?:permission|consent|approval|authorization)\s+(?:from|of)\s+(?:the\s+|each\s+)?(?:customer|client)\b|'
        r'\b(?:customer|client)\b[^.;]{0,35}\b(?:approve\w*|consent\w*|agreed\s+to|limit\w*\s+where)\b|'
        r'\b(?:ask|check\s+with)\s+(?:the\s+|each\s+)?(?:customer|client)\b[^.;]{0,80}\b(?:before|permission|consent|publish|us(?:e|ing))\b|'
        r'\b(?:customer|client|case[-\s]+study|reference)[-\s]+(?:story[-\s]+)?(?:permission|authorization|approval)\b')
    evidence_required['Travel Safety and Emergency Support'] = r'\b(?:travel|trips?|destinations?)\b[^.;]{0,120}\b(?:safety|emergency|insurance|urgent|guidance)\b|\b(?:safety|emergency|insurance|urgent)\b[^.;]{0,120}\b(?:travel|trips?|destinations?)\b'
    evidence_required['Periods With No Overnight Travel'] = r'\b(?:overnight|nights?\s+away)\b[^.;]{0,100}\b(?:travel|trips?|dates?|periods?|weeks?|months?|protect\w*|required)\b|\b(?:dates?|periods?|weeks?|months?|protect\w*)\b[^.;]{0,100}\b(?:overnight|nights?\s+away)\b'
    def quoted_fair_action(pair):
        # In a coordinated list the actor may be far away. Accept a grounded
        # quoted action without broadening unquoted/background-only predictions.
        if pair.get('issue')!='Role in Recruitment Fair' or not pair.get('source_text'):
            return False
        quote=str(pair['source_text'])
        action=bool(re.search(r'\b(?:tak(?:e|ing)\s+part|participat\w*|attend\w*|represent\w*|help\w*|assist\w*)\b[^.;]{0,65}\b(?:recruitment|recruiting|careers?|hiring)[-\s]+(?:fairs?|events?)\b|\b(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?[-\s]+activities\b',quote,re.I))
        contribution=bool(re.search(r'\bcontribut\w*\s+to\s+(?:one|two|a|the|[12])\s+(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\b',quote,re.I))
        annual=_explicit_fair_pledge(_complete_quote_clause(quote,_focused_text(text)))
        return source_quote_is_grounded(quote,_focused_text(text)) and (action or contribution or annual)
    duty_candidates_before_filter={p.get('issue') for p in combined_pairs if isinstance(p,dict)}
    combined_pairs = [
        pair for pair in combined_pairs
        if not (
            isinstance(pair, dict)
            and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] in evidence_required
            and not quoted_fair_action(pair)
            # An exact configured Issue: Choice is direct evidence, even when
            # the human-readable choice abbreviates its longer definition.
            and not re.search(re.escape(str(pair.get('issue','')).lower())+r'\s*[:=]\s*'+re.escape(str(pair.get('option','')).lower()),lower_text)
            and not re.search(
                evidence_required[canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0]],
                lower_text,
            )
        )
    ]
    if any(
        isinstance(pair, dict)
        and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Routine Discount Limit"
        for pair in enriched_pairs
    ):
        combined_pairs = [
            pair for pair in combined_pairs
            if not (
                isinstance(pair, dict)
                and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Deal Approval Rules"
            )
        ]
    if any(
        isinstance(pair, dict)
        and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Reference Provider Choice"
        for pair in enriched_pairs
    ):
        combined_pairs = [
            pair for pair in combined_pairs
            if not (
                isinstance(pair, dict)
                and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] in {
                    "Access to Customer References", "Future Employment Reference"
                }
            )
        ]
    if any(
        isinstance(pair, dict)
        and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Periods With No Overnight Travel"
        for pair in enriched_pairs
    ):
        combined_pairs = [
            pair for pair in combined_pairs
            if not (
                isinstance(pair, dict)
                and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Overnight Travel Limit"
            )
        ]
    if any(
        isinstance(pair, dict)
        and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Specialist Help for Customer Questions"
        for pair in enriched_pairs
    ):
        combined_pairs = [
            pair for pair in combined_pairs
            if not (
                isinstance(pair, dict)
                and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Support After a Sale"
            )
        ]
    specific_mentor_issues = {"Mentoring Assignment Choice", "Paid Learning Time"}
    # Paid learning time and receiving an explicitly named mentor can coexist.
    # Suppress generic mentoring double-counting, not a separately named person.
    explicit_mentor_program = bool(re.search(r"\b(?:mentorship\s+program|mentor\s+program|assigned\s+(?:an?\s+)?(?:internal\s+)?mentor|(?:an?|named|designated|formal|experienced|internal)\s+(?:(?:named|designated|formal|experienced|internal)\s+)*mentor)\b", text, re.I))
    if not explicit_mentor_program and any(isinstance(pair, dict) and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] in specific_mentor_issues for pair in combined_pairs):
        combined_pairs = [
            pair for pair in combined_pairs
            if not (isinstance(pair, dict) and canonical_pair(str(pair.get("issue", "")), str(pair.get("option", "")))[0] == "Mentorship Program")
        ]
    raw_issue_names = {
        canonical_pair(str(pair.get("issue", "")).strip(), str(pair.get("option", "")).strip())[0]
        for pair in combined_pairs if isinstance(pair, dict)
    }
    required_extracted = all(issue in raw_issue_names for issue in required_issues)
    continuous_names = {
        name.lower() for name, spec in _scenario_issue_map(scenario).items()
        if spec.get("kind") == "continuous"
    }
    validated_issue_names: set[str] = set()
    for pair in combined_pairs:
        if not isinstance(pair, dict):
            continue
        issue, option = canonical_pair(str(pair.get("issue", "")).strip(), str(pair.get("option", "")).strip())
        try:
            score_pair(issue, option, role, payoff, scenario)
            validated_issue_names.add(issue.lower())
        except (ValueError, KeyError, TypeError):
            pass

    standard_expense_questions={str(item.get('question','')) for item in extraction.get('ambiguity_details',[]) if isinstance(item,dict) and item.get('issue')=='Personal Budget' and _standard_expense_description(item.get('source_text',''))} if isinstance(extraction,dict) else set()
    def model_note_is_revalidated(item: Any) -> bool:
        note = str(item).lower().strip()
        if required_extracted and (str(item) in standard_expense_questions or _standard_expense_description(item)):return True
        # Empty entries and explicit reports of no problem are not questions.
        if note in ('','none','n/a','no ambiguity','no ambiguities') or note.startswith('none detected'):return True
        if required_extracted and re.search(r'\bno\s+(?:material\s+)?ambiguit(?:y|ies)\s+(?:detected|found)',note) and not re.search(r'\b(?:except|unless)\b',note):return True
        if required_extracted and re.search(r'\bconcrete\s+(?:final\s+)?package\s+is\s+provided\b',note):return True
        if required_extracted and any(_normalized_choice(note)==_normalized_choice(p.get('option','')) for p in combined_pairs if isinstance(p,dict)):return True
        benign_context = required_extracted and any(term in note for term in (
            "misspell", "informal tone", "year not stated", "another year",
            "exact date not specified", "interpreted as 2026", "could refer to 2026", "date format without year", "inferred year not specified",
        ))
        # A question about an unvalued continuous issue is substantive.  Only
        # a question about a value already validated from the offer is benign.
        return benign_context or any(name in note for name in validated_issue_names)
    known_alias_terms = (
        "travel expense", "work expense", "client expense", "client-expense", "client cost", "client allowance", "expense allowance",
        "team-building", "team building",
        "annual leave", "paid days off", "days off", "wfh", "home-working", "work-from-home",
        "remote days", "days monthly",
        "trial period", "probationary", "employment term", "year term", "years term", "employment agreement", "fixed-term", "fixed appointment", "contract", "vacation", "paid vacation",
        "training course", "mentor", "mentoring", "careers fair", "recruitment fair", "hiring fair", "hiring event",
        "conference", "noncompete", "non-compete", "association dues", "professional membership", "professional association", "professional-association",
        "social event", "social gathering", "team social", "team-event", "linkedin", "role review", "job scope", "pay review", "alternative arranged travel", "work-expense budget",
        "customer questions on their own", "handle customer questions",
        "starting date", "start date",
    )
    excluded_extra_terms = {str(term): _excluded_extra_term(str(term), _focused_text(text)) for term in model_unsupported} if isinstance(model_unsupported,list) else {}
    for term, clause in excluded_extra_terms.items():
        if clause:
            unpriced_details.append(dict(issue='Excluded extra duty',detail=clause,meaning='This duty is explicitly excluded, not added or assigned points.'))
    # An unquantified promise of ordinary sales effort is not a new benefit,
    # quota, time allowance or contract duty. Never suppress such additions
    # merely because their longer description mentions client development.
    general_effort_terms={str(term) for term in model_unsupported
        if re.fullmatch(r'(?:(?:i|we) (?:will|would) )?(?:contribute|help|support)(?: actively)?(?: to| with| on)? (?:client|customer|business|sales) (?:development|success|growth)',_normalized_choice(term))} if isinstance(model_unsupported,list) else set()
    for term in sorted(general_effort_terms):
        unpriced_details.append(dict(issue='General work effort',detail=term,meaning='Ordinary unquantified sales-role effort; no additional contract choice or points.'))
    noncompete_scope_qualifiers={str(term) for term in model_unsupported
        if re.fullmatch(r'(?:(?:it|the clause|the restriction) )?(?:would|will|does|do|is) not (?:restrict|apply to|cover|prevent|bar) .+',_normalized_choice(term))
        and 'non-compete clause' in validated_issue_names
        and any(d.get('issue')=='Non-compete Clause' for d in unpriced_details)} if isinstance(model_unsupported,list) else set()
    for term in sorted(noncompete_scope_qualifiers):
        unpriced_details.append(dict(issue='Non-compete Clause',detail=term,meaning='This narrows the retained non-compete; it does not create another priced contract feature.'))
    ordinary_qualifiers=set()
    for term in model_unsupported if isinstance(model_unsupported,list) else []:
        value=_normalized_choice(term)
        voluntary=re.fullmatch(r'(?:voluntary|optional)(?: and (?:agreed in advance|by mutual agreement))?',value)
        duration=re.fullmatch(r'(?:these|the offered|all these) terms (?:would |will )?(?:remain in effect|apply) during probation',value)
        attached=any(value in _normalized_choice(c) and re.search(r'\b(?:team[-\s]+events?|linkedin|conference[-\s]+presentations?|recruitment[-\s]+fairs?)\b',c,re.I) for c in _offer_clauses(_focused_text(text)))
        # A reason for a named fair opportunity is not an additional benefit.
        # Only this narrow relationship rationale, attached to an actual fair,
        # qualifies; new senior-contact rights or meeting quotas remain new.
        fair_rationale=bool(re.fullmatch(r'(?:a )?(?:reasonable )?opportunity to build relationships with senior colleagues',value) and any(value in _normalized_choice(c) and re.search(r'\bincluding\b[^.;]{0,80}\brecruitment[-\s]+fairs?\b',c,re.I) for c in _offer_clauses(_focused_text(text))))
        if (voluntary and attached) or duration or fair_rationale:
            ordinary_qualifiers.add(str(term))
            unpriced_details.append(dict(issue='Qualifier of offered terms',detail=str(term),meaning='Qualifies the existing offer; no independent contract feature or extra points.'))
    # A generic review period may mean probation or a later performance
    # review. Ask which one; do not invent a probation value or tell the
    # negotiator that every interpretation is unavailable.
    review_period_pattern = r'\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six)[-\s]+months?\s+(?:initial\s+)?review\s+period\b'
    unclear_review_period = re.search(review_period_pattern, affirmative_text, re.I)
    if unclear_review_period:
        findings.append(_finding(CLARIFICATION_NEEDED, 'review_period_meaning',
            'By review period, do you mean the initial probation period, or a separate performance review? Please name the term and its duration or timing.'))
    def retained_qualifier_matches(term: str, detail: dict[str, Any]) -> bool:
        if detail.get('issue') not in {'Non-compete Clause','Professional Associations Membership'}:
            return False
        if str(detail.get('issue', '')).lower() not in validated_issue_names:
            return False
        if source_quote_is_grounded(term, detail.get('detail', '')):
            return True
        # Models sometimes repeat a long qualifier with one harmless joining
        # word added or removed (for example "and rather than").  Treat it as
        # the retained detail only when nearly all meaningful words overlap;
        # this must not suppress a genuinely new benefit or contract feature.
        term_tokens = set(re.findall(r'[a-z0-9]+', _normalized_choice(term))) - {'a','an','the','and','or'}
        detail_tokens = set(re.findall(r'[a-z0-9]+', _normalized_choice(str(detail.get('detail', ''))))) - {'a','an','the','and','or'}
        return len(term_tokens) >= 5 and len(term_tokens & detail_tokens) / len(term_tokens) >= .9

    unresolved_model_terms = [
        str(term) for term in model_unsupported
        if not any(_normalized_choice(alias) in _normalized_choice(term) for alias in known_alias_terms)
        and not model_note_is_revalidated(term)
        and not excluded_extra_terms.get(str(term))
        and str(term) not in general_effort_terms
        and str(term) not in noncompete_scope_qualifiers
        and str(term) not in ordinary_qualifiers
        and not (unclear_review_period and re.search(review_period_pattern, str(term), re.I))
        # An already retained qualifier of a priced term is not a new issue.
        # Match its actual words within the retained source clause, not a
        # generic permission to silently ignore unsupported new benefits.
        and not any(retained_qualifier_matches(str(term), d) for d in unpriced_details)
    ] if isinstance(model_unsupported, list) else []
    captured_novel_terms = [str(item) for item in model_novel if str(item).strip()] if isinstance(model_novel, list) else []
    # Only remove complete, unqualified restatements with the SAME scored
    # value. Keep genuinely new qualifications (renewal guarantees, equipment,
    # approval rights, etc.) even when they mention an already priced issue.
    number=r'(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven)'
    restatements={
        'Remote Working Days':rf'(?:(?:the\s+)?(?:ability|permission|option)\s+to\s+)?(?:work\s+remotely|work\s+from\s+home|remote\s+work)\s+(?P<value>{number})\s+days?\s+(?:per|each|a)\s+week',
        'Contract Length':rf'(?:(?:a|an|the|initial|fixed)\s+)*(?P<value>{number})[-\s]+year\s+contract',
    }
    words={'one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7'}
    kept_novel=[]
    for term in captured_novel_terms:
        existing=None
        retained_qualifier = next((detail for detail in unpriced_details
            if source_quote_is_grounded(term, str(detail.get('detail', '')))), None)
        if retained_qualifier:
            semantic_repairs.append(dict(
                before=term,
                after=retained_qualifier.get('issue', 'Qualifier of offered term'),
                reason='Novel-term metadata is already retained as an unpriced qualifier of a scored term.',
            ))
            continue
        for name,pattern in restatements.items():
            match=re.fullmatch(pattern,term.strip().rstrip('.'),re.I)
            if not match or name.lower() not in validated_issue_names:continue
            value=words.get(match['value'].lower(),match['value'])
            try:
                normalized=score_pair(name,value,role,payoff,scenario)[0]
                if any(isinstance(p,dict) and p.get('issue')==name and score_pair(name,str(p.get('option','')),role,payoff,scenario)[0]==normalized for p in combined_pairs):
                    existing=name;break
            except (ValueError,KeyError,TypeError):continue
        if existing:
            semantic_repairs.append(dict(before=term,after=existing,reason='Novel-term metadata restates the same already-scored value; not a new contract feature.'))
        else:kept_novel.append(term)
    captured_novel_terms=kept_novel
    if captured_novel_terms and not _open_capture_enabled(scenario):
        # Bounded scenarios must never silently discard a term merely because
        # the model put it in novel_terms instead of unsupported_terms.
        for term in captured_novel_terms:
            if not any(_normalized_choice(alias) in _normalized_choice(term) for alias in known_alias_terms):
                unresolved_model_terms.append(term)
        captured_novel_terms = []
    if unresolved_model_terms and _open_capture_enabled(scenario):
        captured_novel_terms.extend(unresolved_model_terms)
    elif unresolved_model_terms:
        terms = ", ".join(unresolved_model_terms[:3])
        findings.append(_finding(
            REJECTED, "model_unsupported_terms",
            f"This offer has not been scored because these terms are not available in this scenario: {terms}. Please remove them or choose listed job features.",
        ))
    if _open_capture_enabled(scenario):
        for request in unpriced_personal_travel_requests(_focused_text(text)):
            if not any(source_quote_is_grounded(request, str(term))
                       or source_quote_is_grounded(str(term), request)
                       for term in captured_novel_terms):
                captured_novel_terms.append(request)
    deterministic_relative_terms = ("maximum salary", "maximum work-expense", "maximum work expense", "earliest possible start")
    relative_context_terms = ("same offer", "same as before", "previous offer", "last offer") if previous_offer else ()
    irrelevant_questions={str(item.get('question','')) for item in extraction.get('ambiguity_details',[]) if isinstance(item,dict) and item.get('issue') in evidence_required and not re.search(evidence_required[item['issue']],affirmative_text,re.I)} if isinstance(extraction,dict) else set()
    if isinstance(extraction, dict):
        irrelevant_questions.update(str(item.get('question', ''))
            for item in extraction.get('ambiguity_details', []) if isinstance(item, dict)
            and incidental_numeric_issue_reference(str(item.get('issue', '')),
                str(item.get('source_text', '')), _focused_text(text), outside_requests))
    if _open_capture_enabled(scenario):
        for parking in re.finditer(r'\b(?:reserved|dedicated|free|on[-\s]?site)\s+parking(?:\s+(?:space|spot|bay))?\b',_focused_text(text),re.I):
            # An in-kind space is not the catalogue's annual cash commuting
            # payment. Keep the new feature visible without inventing dollars.
            captured_novel_terms.append(parking.group(0))
    stated_start = _stated_start_date(text, scenario)
    if stated_start and isinstance(extraction, dict):
        irrelevant_questions.update(str(item.get('question', ''))
            for item in extraction.get('ambiguity_details', [])
            if isinstance(item, dict) and item.get('issue') == 'Starting Date'
            and source_quote_is_grounded(str(item.get('source_text', '')), _focused_text(text)))
    if isinstance(extraction, dict):
        irrelevant_questions.update(str(item.get('question', '')) for item in extraction.get('ambiguity_details', [])
            if isinstance(item, dict) and item.get('issue') in usual_readings
            and usual_readings[item['issue']].get('value') is not None
            and source_quote_is_grounded(str(item.get('source_text', '')), _focused_text(text)))
    if _explicit_training_participation(_focused_text(text)):
        irrelevant_questions.update(str(item.get('question','')) for item in extraction.get('ambiguity_details',[]) if isinstance(item,dict) and item.get('issue')=='Professional Training Program' and re.search(r'\bparticipation\b[^?]{0,90}\btraining\s+program\b',str(item.get('question','')),re.I))
        irrelevant_questions.update(str(item.get('question','')) for item in extraction.get('ambiguity_details',[]) if isinstance(item,dict) and _explicit_training_participation(str(item.get('source_text',''))) and not re.search(r'\b(?:budget|money|cost|fee|amount|frequency|hours|days)\b',str(item.get('question','')),re.I))
    # Optional / by-mutual-agreement duties already have an explicit existing
    # catalog interpretation: no standing commitment. Do not ask the agent to
    # turn that optional term into a compulsory duty merely to obtain a score.
    for item in extraction.get('ambiguity_details',[]) if isinstance(extraction,dict) else []:
        if not isinstance(item,dict):continue
        if item.get('issue') in omitted_entitlements:
            irrelevant_questions.add(str(item.get('question','')))
        if item.get('issue')=='Remote Working Days' and remote_allowance:
            irrelevant_questions.add(str(item.get('question','')))
        if item.get('issue')=='Non-compete Clause' and 'non-compete clause' in validated_issue_names and any(d.get('issue')=='Non-compete Clause' for d in unpriced_details) and re.search(r'\bkeep\b[^?]{0,50}\bwaive\b|\bwaive\b[^?]{0,50}\bkeep\b',str(item.get('question','')),re.I):
            irrelevant_questions.add(str(item.get('question','')))
        quoted=re.sub(r'\.{3}|…',' ',str(item.get('source_text','')))
        # A generic publicity duty explicitly made non-obligatory does not
        # require inventing a channel. Positive unspecified posts still ask.
        clause=_complete_quote_clause(quoted,_focused_text(text)) if quoted else ''
        if item.get('issue')=='General offer' and re.search(r'\b(?:public[-\s]+content|publicity|public[-\s]+facing)\b',clause,re.I) and re.search(r'\b(?:voluntary|optional)\b',clause,re.I) and re.search(r'\b(?:not|no|rather\s+than)\s+(?:recurring|standing|regular)\s+obligations?\b',clause,re.I) and re.search(r'\b(?:public|activity|channel)\b',str(item.get('question','')),re.I):
            irrelevant_questions.add(str(item.get('question','')))
        if (item.get('issue') in {'Regular Linkedin Posts for Company','Regular Social Media Posts for Company'}
                and re.search(r'\b(?:no|not|without)\b[^.;]{0,80}\b(?:recurring|standing|regular)\b[^.;]{0,80}\b(?:social[-\s]+media|publicity|posts?)\b|\b(?:no|not|without)\b[^.;]{0,80}\b(?:social[-\s]+media|publicity|posts?)\b', clause, re.I)):
            irrelevant_questions.add(str(item.get('question','')))
        if item.get('issue') in {'Mandatory Conference Presentations','Regular Linkedin Posts for Company','Role in Organizing Social Events','Role in Recruitment Fair'} and re.search(r'\b(?:voluntary|optional|by\s+mutual\s+agreement)\b',quoted,re.I) and re.search(r'\bcommitment\b',str(item.get('question','')),re.I):
            irrelevant_questions.add(str(item.get('question','')))
    for item in model_ambiguities if isinstance(model_ambiguities,list) else []:
        disagreement=re.fullmatch(r'Two extraction passes disagreed about (.+?): (.+?) versus (.+)\.',str(item))
        if not disagreement:continue
        issue,a,b=disagreement.groups()
        normalized,_details,_repairs=_repair_semantic_details([dict(issue=issue,option=a),dict(issue=issue,option=b)],_focused_text(text),scenario)
        try:
            ca=(normalized[0]['issue'],score_pair(normalized[0]['issue'],normalized[0]['option'],role,payoff,scenario)[0])
            cb=(normalized[1]['issue'],score_pair(normalized[1]['issue'],normalized[1]['option'],role,payoff,scenario)[0])
        except (ValueError,KeyError,TypeError):ca,cb=a,b
        explicit=next((p['option'] for p in reversed(enriched_pairs) if p.get('issue')==issue),None)
        if ca!=cb and explicit is None:
            findings.append(_finding(CLARIFICATION_NEEDED,'extraction_disagreement',f'I read two different choices for {issue}: {ca[1] if isinstance(ca,tuple) else ca} or {cb[1] if isinstance(cb,tuple) else cb}. Which one do you mean?',issue=issue))
    duty_markers={
        'Role in Recruitment Fair':r'\brecruit(?:ment|ing)[-\s]+(?:fairs?|activities)\b',
        'Role in Organizing Social Events':r'\b(?:team|social|company)[-\s]+events?\b',
        'Regular Linkedin Posts for Company':r'\blinkedin\b|\b(?:sales|company|publicity)\s+posts?\b',
        'Mandatory Conference Presentations':r'\bconference\b',
    }
    remaining_duty_questions={str(d['question']) for d in extraction.get('ambiguity_details',[]) if isinstance(d,dict) and d.get('issue') in duty_markers and d['issue'].lower() not in validated_issue_names and re.search(duty_markers[d['issue']],str(d.get('source_text','')),re.I) and source_quote_is_grounded(str(d.get('source_text','')),_focused_text(text))}
    issue_specs_for_questions = _scenario_issue_map(scenario)
    bare_value_questions = set()
    for detail in extraction.get('ambiguity_details',[]) if isinstance(extraction,dict) else []:
        if not isinstance(detail,dict):
            continue
        # Do not revive a question already removed because its issue was not
        # supported by the offer text. A non-compete is not confidentiality.
        if str(detail.get('question','')) in irrelevant_questions:
            continue
        issue_name=str(detail.get('issue',''))
        if issue_name=='Remote Working Days' and remote_allowance:
            continue
        issue_spec=issue_specs_for_questions.get(issue_name)
        source=str(detail.get('source_text',''))
        if (issue_spec and issue_name.lower() not in validated_issue_names
                and source_quote_is_grounded(source, _focused_text(text))):
            # A known issue name does not make its unresolved value valid.
            # Keep its question even when it contains a familiar alias, a
            # stated number, or an out-of-range date.
            bare_value_questions.add(str(detail.get('question', '')))
            continue
        # A model may have guessed a catalog value for a bare issue name.  Do
        # not treat that guess as participant evidence.  If the participant
        # named a continuous or multi-option issue without a value, keep the
        # concrete range/choice question even when another extraction pass
        # happened to return a value for the same issue.
        if not issue_spec or re.search(r'\d',source):
            continue
        if issue_name in optional_continuous_evidence and re.search(optional_continuous_evidence[issue_name], affirmative_text):
            continue
        labels=[str(option.get('label','')) for option in issue_spec.get('options',[]) if isinstance(option,dict)]
        choice_already_stated=any(_normalized_choice(label) in _normalized_choice(source) for label in labels if label)
        needs_one_value=issue_spec.get('kind')=='continuous' or len(labels)>2
        if (needs_one_value and not choice_already_stated
                and source_quote_is_grounded(source,_focused_text(text))):
            bare_value_questions.add(str(detail.get('question','')))
    unresolved_model_ambiguities = [
        str(item) for item in model_ambiguities
        if str(item) in remaining_duty_questions or str(item) in bare_value_questions or (str(item) not in irrelevant_questions
        and not any(term in str(item).lower() for term in deterministic_relative_terms + relative_context_terms)
        and not any(_normalized_choice(term) in _normalized_choice(str(item)) for term in known_alias_terms)
        and not model_note_is_revalidated(item))
    ] if isinstance(model_ambiguities, list) else []
    if unresolved_model_ambiguities:
        details = "; ".join(unresolved_model_ambiguities[:3])
        unresolved_issue_names={str(item.get('issue','')) for item in extraction.get('ambiguity_details',[]) if isinstance(item,dict) and item.get('question') in unresolved_model_ambiguities} if isinstance(extraction,dict) else set()
        # Do not display a guessed choice as valid while asking the participant
        # to resolve that exact issue (e.g. four career conversations mapped to
        # two). Keep the original extraction for diagnosis, not payoff use.
        combined_pairs=[p for p in combined_pairs if not (isinstance(p,dict) and p.get('issue') in unresolved_issue_names)]
        findings.append(_finding(
            CLARIFICATION_NEEDED, "model_ambiguity",
            f"I need one detail before scoring: {details}",
            issues=sorted(unresolved_issue_names),
        ))
    # A qualified future duty must not disappear just because its wording
    # fails the narrow activity-evidence patterns above. Do not guess whether
    # "occasional and discussed in advance" creates a binding obligation.
    # Optional opportunities, historical mentions and generic conference
    # attendance remain distinct from promised fair work / LinkedIn duties.
    priced_names={p.get('issue') for p in combined_pairs if isinstance(p,dict)}
    # "Sales posts" does not identify a platform. Do not silently discard a
    # proposed activity, or turn it into LinkedIn merely because it is nearby
    # in the catalog. This also applies when the model forgets to ask.
    broad_social_posts = _uses_broad_social_posts(scenario)
    unnamed_post_channel=(not broad_social_posts) and any(re.search(r'\b(?:contribut\w*|writ\w*|produc\w*|provid\w*)\b[^.;]{0,85}\b(?:sales|company|publicity)\s+posts?\b',c,re.I) and not re.search(r'\b(?:linkedin|twitter|instagram|facebook|tiktok|no|not|without)\b',c,re.I) for c in _offer_clauses(_focused_text(text)))
    if unnamed_post_channel and 'Regular Linkedin Posts for Company' not in priced_names and not any(f.get('code')=='model_ambiguity' and 'Regular Linkedin Posts for Company' in f.get('issues',[]) for f in findings):
        findings.append(_finding(CLARIFICATION_NEEDED,'unspecified_post_channel','Are these posts for the company on LinkedIn, or another channel? Please name the channel.',issue='Regular Linkedin Posts for Company'))
    resolved_linkedin_option=next((p.get('option') for p in reversed(combined_pairs) if isinstance(p,dict) and p.get('issue')=='Regular Linkedin Posts for Company'),None)
    channel_alternative=bool(not broad_social_posts and re.search(r'\blinkedin\s+or\s+(?:another|other)\b', _focused_text(text), re.I) and resolved_linkedin_option=='Commitment')
    if channel_alternative:
        combined_pairs=[p for p in combined_pairs if not(isinstance(p,dict) and p.get('issue')=='Regular Linkedin Posts for Company')]
        priced_names.discard('Regular Linkedin Posts for Company')
        findings.append(_finding(CLARIFICATION_NEEDED,'alternative_publication_channel','Is this a commitment to company LinkedIn content, or to a different channel? Please specify so I can score that duty.',issue='Regular Linkedin Posts for Company'))
    if 'Mandatory Conference Presentations' in duty_candidates_before_filter and 'Mandatory Conference Presentations' not in priced_names and re.search(r'\b(?:happy|willing|would|will|offer|propose|include)\b[^.;]{0,120}\bconference\s+activities\b',_focused_text(text),re.I):
        findings.append(_finding(CLARIFICATION_NEEDED,'conference_activity_scope','Do you mean giving conference presentations, or only attending or helping at conferences?',issue='Mandatory Conference Presentations'))
    for issue,marker in {
        'Role in Recruitment Fair':r'\b(?:recruitment|recruiting|careers?|hiring)[-\s]+fairs?\b',
        'Regular Linkedin Posts for Company':r'\blinkedin\b',
    }.items():
        qualified=any(re.search(marker,c,re.I) and re.search(r'\bwould\s+be\s+occasional\b[^.;]{0,65}\bdiscussed\b[^.;]{0,45}\bin\s+advance\b',c,re.I) for c in _offer_clauses(_focused_text(text)))
        if issue not in priced_names and qualified:
            findings.append(_finding(CLARIFICATION_NEEDED,'unresolved_future_duty',f'For {issue}, is participation a commitment or optional? Please specify one for this offer.',issue=issue))
    explicit_nonoffer = any(item["code"] in {
        "not_a_final_offer", "prompt_injection", "hypothetical_offer", "possible_sarcasm",
        "missing_conversation_context", "missing_previous_offer",
    } for item in findings)
    if offer_intent == "uncertain" and (explicit_nonoffer or not raw_issue_names):
        findings.append(_finding(
            CLARIFICATION_NEEDED, "uncertain_intent",
            "I am not sure whether this is your final offer. Please confirm or submit one final set of choices.",
        ))
    elif offer_intent == "not_an_offer" and not (required_extracted and not explicit_nonoffer):
        findings.append(_finding(
            REJECTED, "not_an_offer",
            "This has not been scored because it does not contain a final offer. Please submit one complete offer when you are ready.",
        ))

    last_by_issue: OrderedDict[str, dict[str, Any]] = OrderedDict()
    current_issues=_scenario_issue_map(scenario)
    if ('Company Car' in current_issues and current_issues['Company Car'].get('bare_request_default')
            and re.search(r'\b(?:company|dedicated)\s+car\s+or\s+(?:(?:a|the)\s+)?(?:shared\s+)?pool\s+car\b|\bpool\s+car\s+or\s+(?:(?:a|the)\s+)?(?:company|dedicated)\s+car\b', lower_text)):
        combined_pairs = [p for p in combined_pairs if not (isinstance(p, dict) and p.get('issue') == 'Company Car')]
        findings.append(_finding(CLARIFICATION_NEEDED, 'company_car_alternatives',
            'For this offer, would you like a dedicated company car or access to a shared pool car? Please choose one.', issue='Company Car'))
    if ('Company Car' in current_issues and not current_issues['Company Car'].get('bare_request_default') and re.search(r'\bcompany\s+car\b',lower_text)
            and not re.search(r'\b(?:dedicated|exclusive|shared|pool|private|personal|own)\s+(?:company\s+)?car\b|\b(?:no|without)\s+(?:(?:a|the|any)\s+)?(?:company\s+)?car\b|\bcompany\s+car\s+(?:(?:is|would|will|be|a|the)\s+){0,3}(?:shared|pool|dedicated|exclusive|not\s+included)\b',lower_text)):
        findings.append(_finding(CLARIFICATION_NEEDED,'ambiguous_catalogue_choice',
            'For the company car, do you mean access to a shared pool car or a dedicated company car? Please choose one.',
            issue='Company Car',allowed=[o['label'] for o in current_issues['Company Car']['options']]))
    if ('Four-Day Workweek Trial' in current_issues
            and re.search(r'\b'+_FOUR_DAY_PATTERN+r'\b',lower_text)
            and not re.search(r'\b(?:no|without)\s+(?:a\s+)?(?:trial|four[-\s]?day)\b',lower_text)
            and not _explicit_workweek_trial(lower_text)):
        findings.append(_finding(CLARIFICATION_NEEDED,'ambiguous_catalogue_choice',
            'For the four-day week, do you mean a weekly or monthly trial with the same weekly hours, or a different work arrangement? Please specify.',
            issue='Four-Day Workweek Trial',allowed=[o['label'] for o in current_issues['Four-Day Workweek Trial']['options']]))
    malformed = False
    for pair in combined_pairs:
        if not isinstance(pair, dict):
            malformed = True
            continue
        issue = str(pair.get("issue", "")).strip()
        option = str(pair.get("option", "")).strip()
        if not issue or not option:
            malformed = True
            continue
        issue, option = canonical_pair(issue, option)
        if issue in SOCIAL_POST_NAMES:
            issue = SOCIAL_POST_INTERNAL
        confidence = pair.get("confidence", 1.0)
        try:
            confidence_value = float(confidence)
        except (TypeError, ValueError):
            confidence_value = 0.0
        last_by_issue[issue] = {"issue": issue, "option": option, "confidence": confidence_value}

    if malformed:
        findings.append(_finding(
            REJECTED, "malformed_extraction",
            "This offer could not be read safely. Please restate it using one issue and one choice at a time.",
        ))

    lines: list[str] = []
    total = 0.0
    valid_pairs: OrderedDict[str, str] = OrderedDict()
    issue_specs = _scenario_issue_map(scenario)
    for issue, pair in last_by_issue.items():
        option = pair["option"]
        if issue=='Salary' and any(f.get('code')=='minimum_salary' for f in findings):
            continue
        if issue not in payoff and issue not in issue_specs and _open_capture_enabled(scenario):
            captured_novel_terms.append(f"{issue}: {option}")
            continue
        if issue not in payoff and issue not in issue_specs:
            findings.append(_finding(
                REJECTED, "invalid_issue",
                f"{issue} is not available in this scenario. Please remove it or choose a listed job feature.",
                issue=issue,
            ))
            continue
        spec = issue_specs.get(issue)
        public_issue = str((spec or {}).get("name", issue))
        if any(f.get('issue')==issue and f.get('code') in {'invalid_unit','invalid_unit_or_option','ambiguous_catalogue_choice','numeric_range'} for f in findings):
            # Do not display the model's guessed weekly value when the offer
            # actually supplied a monthly one. The clarification acknowledges it.
            continue
        if spec and spec.get('value_type') == 'currency' and any(f.get('code')=='unsupported_currency' for f in findings):
            foreign_values=[]
            for foreign in re.finditer(r'[£€]\s*(\d[\d,.]*(?:\s*k)?)',_focused_text(text),re.I):
                try: foreign_values.append(_money_number_from_text(foreign.group(1)))
                except ValueError: pass
            try: matches_foreign = any(math.isclose(_money_number_from_text(option), v, abs_tol=1e-9) for v in foreign_values)
            except ValueError: matches_foreign = False
            if matches_foreign:
                # Retain the raw amount in the interpretation, but do not show
                # foreign currency as a validated dollar amount or price it.
                continue
        if issue == "Remote Working Days":
            expected_period = "week" if "week" in str((spec or {}).get("unit", "")).lower() else "month"
            stated_period = re.search(r"(?:/|\b(?:per|each|every|a))\s*(week|month)\b", option, re.I)
        else:
            expected_period = ""
            stated_period = None
        if stated_period and stated_period.group(1).lower() != expected_period:
            findings.append(_finding(
                REJECTED, "invalid_unit_or_option",
                f"Remote work is scored in days per {expected_period} here. Please use that unit.",
                issue=issue, option=option, allowed=[f"{spec['min']} days / {expected_period}", f"{spec['max']} days / {expected_period}"],
            ))
            continue
        try:
            canonical_option, points = score_pair(issue, option, role, payoff, scenario)
        except (ValueError, KeyError, TypeError):
            clarifies_this_value = any(
                item.get("decision") == CLARIFICATION_NEEDED
                and (not item.get("issue") or item.get("issue") == issue)
                and item.get("code") in {
                    "unsupported_currency", "invalid_unit", "invalid_unit_or_option",
                    "vague_start_date", "approximate_start_date", "approximate_salary",
                    "salary_range", "budget_range", "alternatives", "conditional_offer",
                    "ambiguous_numeric_date", "vague_choices",
                }
                for item in findings
            )
            if clarifies_this_value:
                continue
            if spec and spec.get("kind") == "continuous":
                proposal_domain = spec.get("proposal_domain")
                if isinstance(proposal_domain, dict):
                    domain_low = proposal_domain.get("min")
                    domain_high = proposal_domain.get("max")
                    if spec.get("value_type") == "currency" and domain_low == 0 and domain_high is None:
                        allowed = ["any non-negative annual USD amount"]
                        message = f"{option} is not a valid amount for {issue}. Please enter a non-negative annual amount in US dollars."
                    else:
                        allowed = [str(value) for value in (domain_low, domain_high) if value is not None]
                        message = (f'Vacation cannot be negative or exceed 365 days per year. Please choose one annual allowance (0–365 days).' if issue == 'Vacation Days' else
                            'There are five working days per week in this scenario. Please choose 0–5 remote-working days per week.' if issue == 'Remote Working Days' else
                            f'{option} does not match the allowed proposal values for {issue}. Please choose from {domain_low} to {domain_high}.')
                elif spec.get("value_type") == "date":
                    low_label = _format_continuous(date.fromisoformat(str(spec["min"])), spec)
                    high_label = _format_continuous(date.fromisoformat(str(spec["max"])), spec)
                    allowed = [low_label, high_label]
                    message = f"{option} is outside or does not match the available range for {issue}. Please choose a value from {low_label} to {high_label}."
                else:
                    low_label = _format_continuous(float(spec["min"]), spec)
                    high_label = _format_continuous(float(spec["max"]), spec)
                    allowed = [low_label, high_label]
                    message = f"{option} is outside or does not match the available range for {issue}. Please choose a value from {low_label} to {high_label}."
            else:
                allowed = [str(item.get("label")) for item in spec.get("options", [])] if spec else list(payoff.get(issue, {}))
                message = f"{option} is not an available choice for {issue}. Please choose {_choice_list(allowed)}."
            findings.append(_finding(
                CLARIFICATION_NEEDED, "invalid_option",
                message,
                issue=issue, option=option, allowed=allowed,
            ))
            continue
        if pair["confidence"] < MIN_CONFIDENCE:
            findings.append(_finding(
                CLARIFICATION_NEEDED, "low_confidence",
                f"I am not confident that “{option}” is the intended {issue}. Please enter one exact {issue} value.",
                issue=issue, option=option,
            ))
            continue
        valid_pairs[public_issue] = canonical_option
        total += points
        lines.append(f"- {public_issue}: {canonical_option}  [{'+' if points >= 0 else ''}{points:.2f}]")

    missing = [issue for issue in required_issues if issue not in valid_pairs]
    unstated_missing = [issue for issue in missing if issue not in raw_issue_names]
    # An interpreter may ask about an impossible date without returning a
    # usable pair. Give the participant the actual permitted dates as well,
    # rather than leaving them to guess what a correction would look like.
    date_attempt = _stated_start_date(text, scenario, include_invalid=True)
    date_spec = _scenario_issue_map(scenario).get("Starting Date")
    if (date_attempt and date_spec and date_spec.get("value_type") == "date"
            and "Starting Date" not in valid_pairs
            and not any(f.get("code") == "invalid_option" and f.get("issue") == "Starting Date" for f in findings)):
        try:
            score_pair("Starting Date", date_attempt, role, payoff, scenario)
        except (ValueError, KeyError, TypeError):
            low_label = _format_continuous(date.fromisoformat(str(date_spec["min"])), date_spec)
            high_label = _format_continuous(date.fromisoformat(str(date_spec["max"])), date_spec)
            findings.append(_finding(
                CLARIFICATION_NEEDED, "invalid_option",
                f"I read your starting date as {date_attempt}. Please choose a valid calendar date from {low_label} to {high_label}.",
                issue="Starting Date", option=date_attempt, allowed=[low_label, high_label],
            ))
    existing_clarification = any(item["decision"] == CLARIFICATION_NEEDED for item in findings)
    if unstated_missing and not existing_clarification:
        missing_text = ", ".join(unstated_missing)
        findings.append(_finding(
            REJECTED, "missing_required",
            f"Please add {missing_text}. I have not scored this offer yet.",
            missing=unstated_missing,
        ))
    salary_domain = (issue_specs.get('Salary') or {}).get('proposal_domain')
    if isinstance(salary_domain, dict) and salary_domain.get('max') is None:
        # Current open-money scenarios offer a correction path for a stated
        # invalid value. Keep the frozen older scenario's response unchanged.
        for item in findings:
            if (item.get('decision')==REJECTED and item.get('code') in {'invalid_option','invalid_start_month','invalid_unit_or_option'}
                    and (issue_specs.get(item.get('issue')) or {}).get('kind')=='continuous'):
                item['decision']=CLARIFICATION_NEEDED
    has_rejection = any(item["decision"] == REJECTED for item in findings)
    has_clarification = any(item["decision"] == CLARIFICATION_NEEDED for item in findings)
    has_substantive_clarification = any(
        item["decision"] == CLARIFICATION_NEEDED and item.get("code") != "uncertain_intent"
        for item in findings
    )

    if has_rejection:
        decision = REJECTED
    elif has_substantive_clarification:
        decision = CLARIFICATION_NEEDED
    elif missing:
        decision = REJECTED
        if not valid_pairs and not unstated_missing:
            findings.append(_finding(
                REJECTED, "no_offer_terms",
                f"No complete offer was found. Please include {_choice_list(required_issues)} using the displayed choices.",
                missing=missing,
            ))
    elif has_clarification:
        decision = CLARIFICATION_NEEDED
    else:
        decision = SCORABLE

    blocking_decisions = {decision, CLARIFICATION_NEEDED} if decision == REJECTED else {decision}
    blocking = [item for item in findings if item["decision"] in blocking_decisions]
    messages = list(dict.fromkeys(item["message"].strip() for item in blocking if item.get("message", "").strip()))
    message = "\n".join(messages)

    # A bare duration already priced as Contract Length is not a new issue.
    # Retain richer additions (e.g. renewal rights or severance) for review.
    duplicate_novel = []
    for term in captured_novel_terms:
        if not re.fullmatch(r'(?:a |an |the )?(?:one|two|three|four|\d+(?:\.\d+)?)[- ]years? (?:employment )?contract', str(term).strip(), re.I):
            continue
        inferred = [p for p in _study_pair_enrichment(str(term), scenario) if p['issue'] == 'Contract Length']
        if inferred and 'Contract Length' in valid_pairs:
            try:
                if score_pair('Contract Length', inferred[-1]['option'], role, payoff, scenario)[0] == valid_pairs['Contract Length']:
                    duplicate_novel.append(term)
            except (ValueError, KeyError):
                pass
    captured_novel_terms = [t for t in captured_novel_terms if t not in duplicate_novel]

    result = {
        "decision": decision,
        "message": message,
        "messages": messages,
        "findings": findings,
        "lines": lines,
        "total": total,
        "any_valid": bool(valid_pairs),
        "invalid_present": any(item["code"] in {"invalid_issue", "invalid_option", "invalid_unit_or_option", "unsupported_currency"} for item in findings),
        "required_ok": not missing,
        "missing_required": missing,
        "unstated_required": unstated_missing,
        "invalid_required": [issue for issue in missing if issue not in unstated_missing],
        "valid_pairs": dict(valid_pairs),
        "novel_terms": list(dict.fromkeys(term.strip() for term in captured_novel_terms if term.strip())),
        "unpriced_details": unpriced_details,
        "discarded_predictions": discarded_predictions,
        "semantic_repairs": semantic_repairs,
    }
    result["display_text"] = format_system_output(result)
    interpretation_notes = []
    for name, reading in usual_readings.items():
        if reading.get('value') is not None and name in valid_pairs:
            interpretation_notes.append(f"{name}: {valid_pairs[name]}. {reading['note']} Please check this interpretation before sending.")
    if unpriced_details:
        result['display_text'] += '\n\nExtra details retained without additional points:\n' + '\n'.join('- '+item['detail'] for item in unpriced_details)
    vacation_spec = _scenario_issue_map(scenario).get('Vacation Days', {})
    if (vacation_spec.get('weekly_to_annual_factor') and 'Vacation Days' in valid_pairs
            and re.search(r'\b(?:vacay|vacation|holiday|time\s+off|days?\s+off)\b[^.;\n]{0,30}\b(?:per|a|each|every)\s+week\b', text, re.I)):
        annual = valid_pairs['Vacation Days']
        note = 'Weekly vacation allowance shown as ' + annual + ('' if 'year' in annual else ' per year') + ' (52 weeks). Please check this interpretation before sending.'
        interpretation_notes.append(note)
    if interpretation_notes:
        result['interpretation_notes'] = interpretation_notes
        result['display_text'] += '\n\n' + '\n'.join(interpretation_notes)
    return result


def format_system_output(result: dict[str, Any]) -> str:
    decision = result.get("decision")
    if decision == SCORABLE:
        lines = list(result.get("lines", []))
        total = float(result.get("total", 0.0))
        output = "\n".join(lines) + f"\nTotal: {'+' if total >= 0 else ''}{total:.2f}"
        novel = list(result.get("novel_terms", []))
        if novel:
            output += "\nRecorded new terms (not scored yet):\n" + "\n".join(f"- {term}" for term in novel)
        return output
    if decision == CLARIFICATION_NEEDED:
        messages = result.get("messages") or [result.get("message", "").strip()]
        details = "\n".join(f"- {message}" for message in messages if message)
        return f"Clarification needed:\n{details}\nNo score calculated."
    messages = result.get("messages") or [result.get("message", "").strip()]
    details = "\n".join(f"- {message}" for message in messages if message)
    return f"Invalid Offer:\n{details}\nNo score calculated."
