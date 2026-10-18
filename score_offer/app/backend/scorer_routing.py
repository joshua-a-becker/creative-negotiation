"""Transparent nano-first routing. No private counterpart values or model confidence alone certify accuracy."""
from __future__ import annotations
import re

VERSION = 'nano-luna-cascade-2026-09-09-v1'
PRIMARY = 'gpt-5-nano'
FALLBACK = 'gpt-5.6-luna'

def escalation_reasons(text, extraction, evaluated):
    """One independent stronger interpretation for potentially difficult inputs.

    Negative/zero payoff is never a trigger. Genuine ambiguity may remain after
    escalation; the stronger model is not authorized to invent an answer.
    """
    reasons = []
    if evaluated.get('decision') != 'scorable':
        reasons.append('interpretation_needs_review')
    if extraction.get('_discarded_ambiguities') or evaluated.get('discarded_predictions'):
        reasons.append('ungrounded_prediction')
    if any(float(p.get('confidence', 1)) < .80 for p in extraction.get('pairs', []) if isinstance(p, dict)):
        reasons.append('uncertain_mapping')
    if extraction.get('novel_terms') or extraction.get('unsupported_terms'):
        reasons.append('catalog_boundary')
    if len(extraction.get('pairs', [])) >= 8 or text.count(';') >= 3:
        reasons.append('dense_package_completeness')
    # A short extra request can otherwise disappear while the three required
    # choices make the offer look complete. Ask the independent reviewer to
    # inspect uncovered coordinated clauses; do not assign them any points.
    def normalized(value):
        return re.sub(r'[^a-z0-9]+',' ',str(value).lower()).strip()
    sources=[normalized(p.get('source_text','')) for p in extraction.get('pairs',[]) if isinstance(p,dict)]
    sources += [normalized(s) for s in [*extraction.get('novel_terms',[]),*extraction.get('unsupported_terms',[])]]
    for clause in re.split(r'\s+(?:and|plus|together\s+with)\s+',text,flags=re.I)[1:]:
        value=normalized(clause)
        if re.match(r'^(?:an?|the\s+right\s+to|access\s+to|free)\s+',value) and not any(value in source for source in sources if source):
            reasons.append('unaccounted_offer_clause')
            break
    names = set(evaluated.get('valid_pairs', {}))
    for name, pattern in {
        'Probation Length': r'\b(?:probation|trial period)\b',
        'Contract Length': r'\b(?:contract|employment term)\b',
        'Senior Career Guidance': r'\bcareer[-\s]+(?:development|guidance|advi\w*)\b',
        'Role in Recruitment Fair': r'\b(?:recruitment|recruiting|career)\s+fair',
        'Regular Linkedin Posts for Company': r'\blinkedin\b',
        'Role in Organizing Social Events': r'\b(?:social|team|company)\s+events?\b',
    }.items():
        if re.search(pattern, text, re.I) and name not in names:
            reasons.append('mentioned_issue_not_priced:' + name)
    return list(dict.fromkeys(reasons))
