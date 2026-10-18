"""Convert explicitly selected choices into the shared scorer's input format."""
import math
import re
from decimal import Decimal
from offer_engine import score_pair, format_system_output, SCORABLE, REJECTED, CLARIFICATION_NEEDED


def structured_interpretation(choices, scenario):
    if not isinstance(choices, dict) or not choices:
        raise ValueError('choices must be a non-empty object mapping issue names to values.')
    known = {issue['name']: issue for issue in scenario['issues']}
    names_by_id = {issue['id']: issue['name'] for issue in scenario['issues'] if issue.get('id')}
    pairs, lines, seen = [], [], set()
    for key, value in choices.items():
        name = names_by_id.get(key, key)
        if name not in known:
            raise ValueError(f'Unknown issue: {key}')
        if name in seen:
            raise ValueError(f'Duplicate issue: {name}')
        seen.add(name)
        if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
            raise ValueError(f'Please provide one choice for {name}.')
        if isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError(f'Please provide a finite value for {name}.')
        option = format(Decimal(str(value)), 'f') if isinstance(value, (int, float)) else str(value).strip()
        if not option:
            raise ValueError(f'Please provide one choice for {name}.')
        spec = known[name]
        if spec['kind'] == 'continuous':
            if spec['value_type'] == 'date':
                month = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)'
                pattern = rf'(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{month}(?:\s+\d{{4}})?|{month}(?:\s+\d{{1,2}}(?:st|nd|rd|th)?)?(?:,?\s+\d{{4}})?)'
            else:
                number = r'-?\d[\d,]*(?:\.\d+)?(?:e[+-]?\d+)?\s*k?'
                unit = re.escape(spec.get('unit', ''))
                pattern = rf'(?:USD\s*)?\$?{number}(?:\s*(?:USD|{unit}))?'
            if not re.fullmatch(pattern, option, re.I):
                raise ValueError(f'Please provide one exact value for {name}, with the configured units.')
        pairs.append({'issue': name, 'option': option, 'confidence': 1})
        lines.append(f'{name}: {option}')
    return '; '.join(lines), {
        'pairs': pairs, 'ambiguities': [], 'unsupported_terms': [], 'novel_terms': [],
        'offer_intent': 'offer', '_model': 'deterministic',
        '_routing': {'policy': 'structured_choices', 'selected': 'deterministic', 'calls': 0},
        '_usage': {'input_tokens': 0, 'output_tokens': 0},
    }


def evaluate_structured_offer(extraction, role, scenario):
    """Explicit form values need arithmetic validation, not language inference."""
    pairs, lines, findings, total = {}, [], [], 0.0
    for pair in extraction['pairs']:
        issue, option = pair['issue'], pair['option']
        try:
            canonical, points = score_pair(issue, option, role, {}, scenario)
        except (ValueError, TypeError, KeyError) as exc:
            findings.append({'decision':CLARIFICATION_NEEDED, 'code':'invalid_option',
                             'issue':issue, 'option':option,
                             'message':f'Please check the value for {issue}: {exc}.'})
            continue
        pairs[issue] = canonical
        total += points
        lines.append(f'- {issue}: {canonical}  [{points:+.2f}]')
    missing = [name for name in scenario['required_issues'] if name not in pairs]
    attempted = {pair['issue'] for pair in extraction['pairs']}
    absent = [name for name in missing if name not in attempted]
    if absent:
        findings.append({'decision':REJECTED,'code':'missing_required','missing':absent,
                         'message':'Please include a choice for '+', '.join(absent)+'.'})
    decision = REJECTED if absent else CLARIFICATION_NEEDED if findings else SCORABLE
    messages = [item['message'] for item in findings]
    result = dict(decision=decision,message='\n'.join(messages),messages=messages,findings=findings,
                  lines=lines,total=total,any_valid=bool(pairs),invalid_present=bool(findings),
                  required_ok=not missing,missing_required=missing,valid_pairs=pairs,
                  novel_terms=[],unpriced_details=[],discarded_predictions=[],semantic_repairs=[])
    result['display_text'] = format_system_output(result)
    return result
