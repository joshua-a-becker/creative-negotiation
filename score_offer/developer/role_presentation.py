"""Approved feedback-material wording/layout; frozen scenarios stay untouched.

The Empirica export retains its narrative-string schema and paragraph breaks.
Literal bullet characters work without Markdown list support. Italics/colors use
small inline HTML tags, because single-asterisk Markdown was displayed literally.
The researcher requested this HTML compatibility trial in the deployed reader.
"""
import html
import re
from copy import deepcopy

GREEN = '#166534'
RED = '#b91c1c'
BLUE = '#1d4ed8'
DARK_BLUE = '#1e3a8a'
SCORING_HEADING = 'Important notes on offers and scoring'
LIST_WRAPPER = '<span style="display:block;margin-left:1.5em;padding-left:1.25em;text-indent:-1.25em;">'


def unwrap_list_item(paragraph):
    """Read the exact list wrapper we generate; leave other spans untouched."""
    if paragraph.startswith(LIST_WRAPPER):
        assert paragraph.endswith('</span>')
        return paragraph[len(LIST_WRAPPER):-len('</span>')]
    return paragraph


def review_blocks(blocks, policy='open'):
    """Apply the researcher's explicit preview edits without mutating the source.

    10 September review: replace the long budget explanation with the short
    parenthetical; add the final scoring heading; emphasize the payment sentence.
    These are reviewed feedback-material edits, not a rewrite of frozen experiments.
    """
    if policy not in {'open', 'bounded', 'fixed'}:
        raise ValueError('Unknown role-material presentation policy: ' + str(policy))
    revised = []
    for original in blocks:
        block = deepcopy(original)
        text = ''.join(r.get('text', '') for r in block['runs'])
        if text.startswith('You are an ambitious sales professional negotiating a role'):
            old = 'You are an ambitious sales professional negotiating a role with a young company.'
            assert text.startswith(old)
            block['runs'] = [
                {'text': 'You are an ambitious job '},
                {'text': 'Candidate', 'italic': True},
                {'text': ' negotiating a sales role with a young company.' + text[len(old):]},
            ]
        elif text == 'Your Task':
            block['runs'] = [{'text': 'INSTRUCTIONS', 'bold': True}]
        elif text.startswith('Your objective is to reach'):
            required_phrase = ('Every offer must address all 15 job terms' if policy == 'fixed'
                               else 'Every complete offer must include')
            assert text.count(required_phrase) == 1
            assert 'The budget is an annual allowance for approved work expenses' in text
            cutoff = text.index(required_phrase)
            kept, used = [], 0
            for run in block['runs']:
                available = min(len(run.get('text', '')), max(0, cutoff - used))
                if available:
                    kept.append({**run, 'text': run['text'][:available]})
                used += len(run.get('text', ''))
            if policy == 'fixed':
                block['runs'] = kept + [
                    {'text': 'Every offer must address all 15 job terms in your private payoff table. '
                             'These include '},
                    {'text': 'salary', 'bold': True}, {'text': ', a '},
                    {'text': 'starting date', 'bold': True}, {'text': ', and a '},
                    {'text': 'personal budget for work expenses', 'bold': True},
                    {'text': ' such as client travel, meals, and lodging (but not take-home pay!).'},
                ]
            else:
                block['runs'] = kept + [
                    {'text': 'Every complete offer must include three terms: '},
                    {'text': 'salary', 'bold': True}, {'text': ', a '},
                    {'text': 'starting date', 'bold': True}, {'text': ', and a '},
                    {'text': 'personal budget for work expenses', 'bold': True},
                    {'text': ' such as client travel, meals, and lodging (but not take-home pay!).'},
                ]
        elif text.startswith('You prefer a '):
            replacements = {
                '$20,000 to $80,000': '$35,000 to $65,000',
                '$20,000 gives you −2 points, $40,000 gives you 0, and $80,000 gives you +2': '$35,000 gives you −2 points, $50,000 gives you 0, and $65,000 gives you +2',
                '$20,000 gives you +2 points, $40,000 gives you 0, and $80,000 gives you −2': '$35,000 gives you +2 points, $50,000 gives you 0, and $65,000 gives you −2',
                '$1,000 to $20,000': '$5,000 to $15,000',
                '$1,000 gives you −2, $10,500 gives you 0, and $20,000 gives you +2': '$5,000 gives you −2, $10,000 gives you 0, and $15,000 gives you +2',
                '$1,000 gives you +2, $10,500 gives you 0, and $20,000 gives you −2': '$5,000 gives you +2, $10,000 gives you 0, and $15,000 gives you −2',
                'a $7,000 budget is worth about −0.74 points': 'a $7,000 budget is worth about −1.2 points',
                'a $7,000 budget is worth about +0.74 points': 'a $7,000 budget is worth about +1.2 points',
            }
            for before, after in replacements.items():
                text = text.replace(before, after)
            # Put budget last in both roles, adjacent to its worked example.
            marks = [text.index(s) for s in ('Annual salary may range',
                     'The personal budget may range', 'Starting dates may range',
                     'The platform calculates')]
            a, b, c, d = marks
            block['runs'] = [{'text': text[:a] + text[a:b] + text[c:d] + text[b:c] + text[d:]}]
        elif text.startswith('These headline contract terms'):
            changed = 0
            for run in block['runs']:
                changed += run.get('text', '').count('The interview also left you thinking')
                run['text'] = run.get('text', '').replace('The interview also left you thinking',
                                                       'However, the interview also left you thinking')
            assert changed == 1, 'Expected the interview transition in both roles.'
        elif text.startswith('Other stories were less appealing.'):
            for run in block['runs']:
                run['text'] = run.get('text', '').replace(
                    'Good client stories are turned into LinkedIn posts, and confident employees sometimes present at conferences.',
                    'The company regularly shares strong client stories on social media. Employees close to those accounts may be asked to help shape the posts, and confident employees sometimes present at conferences.',
                )
                run['text'] = run.get('text', '').replace('You enjoy people,', '… You enjoy people,')
        elif text.startswith('Other parts of the conversation'):
            # The equivalent turn from possibilities to reservations for Recruiter.
            for run in block['runs']:
                run['text'] = run.get('text', '').replace(
                    'Their sales work could provide material for LinkedIn posts and other public communications.',
                    "The company regularly shares strong client stories on social media. Because the Candidate would be close to those accounts, they might be a natural person to help shape the posts.",
                )
                run['text'] = run.get('text', '').replace('Conference presentations sounded less useful.',
                                                       '… Conference presentations sounded less useful.')
        elif text.startswith('The interview contained small details') and policy == 'open':
            role_heading = ''.join(r.get('text', '') for r in blocks[0]['runs'])
            closing = ('what matters to you.' if role_heading.startswith('CANDIDATE')
                       else 'what matters to the company.')
            block['runs'] = [{'text':
                'The interview also touched on everyday work resources, spending support, health and wellbeing benefits, '
                'and how people are evaluated and rewarded as their responsibilities grow. Some details may simply be '
                'background; others could become useful terms if you connect them to ' + closing}]
        elif text.startswith('For example:'):
            old = 'any other terms I choose to raise'
            if policy == 'fixed':
                assert 'other terms in the table' in text
            else:
                assert text.count(old) == 1
                for run in block['runs']:
                    run['text'] = run.get('text', '').replace(old, '[list any job features you want to bring up]')
        elif text.startswith('Your score is private'):
            sentence = 'Your score is private and translates directly into the bonus payment you can earn from this task.'
            assert text.startswith(sentence)
            fallback_at = text.index('Without a deal,')
            role_heading = ''.join(r.get('text', '') for r in blocks[0]['runs'])
            assert role_heading in ('CANDIDATE ROLE INFORMATION', 'RECRUITER ROLE INFORMATION')
            counterpart = 'Recruiter' if role_heading.startswith('CANDIDATE') else 'Candidate'
            old_acceptance = ('An agreement requires both parties to accept the same offer, '
                              'with a positive total score for each. Individual terms may still be worth zero or less.')
            acceptance_text = text[len(sentence):fallback_at].rstrip()
            assert acceptance_text.count(old_acceptance) == 1
            acceptance_text = acceptance_text.replace(old_acceptance,
                'An agreement requires both parties to accept the same offer, '
                'with a positive total score for you and the ' + counterpart + '.')
            block['runs'] = [
                {'text': 'Your score', 'bold': True}, {'text': ' is private and '},
                {'text': 'translates', 'bold': True}, {'text': ' directly into the '},
                {'text': 'bonus payment you', 'bold': True}, {'text': ' can '},
                {'text': 'earn', 'bold': True}, {'text': ' from this task.'},
                {'text': acceptance_text},
            ]
            revised.append(block)
            revised.append({'type': 'heading', 'runs': [{'text': SCORING_HEADING, 'bold': True}]})
            revised.append({'type': 'numbered', 'number': 1, 'runs': [{'text': text[fallback_at:]}]})
            continue
        elif text.startswith('The researchers set the scoring rules'):
            revised.append({'type': 'numbered', 'number': 2,
                            'runs': [{'text': 'The researchers set the scoring rules in advance, and the platform '
                                      'calculates points automatically; you do not assign or calculate points yourself.'}]})
            if policy == 'fixed':
                assert 'Your private table shows all 15 terms and their values to you.' in text
                revised.append({'type': 'numbered', 'number': 3, 'runs': [{'text':
                    'Your private table shows all 15 terms and their values to you. Include a choice for every row in every offer.'}]})
                revised.append({'type': 'numbered', 'number': 4, 'runs': [{'text':
                    'Separate terms are scored separately and added together. Rewording a term does not earn extra points.'}]})
                revised.append({'type': 'numbered', 'number': 5, 'runs': [{'text':
                    'Do not add terms outside the private payoff table.', 'bold': True}]})
            else:
                additional = text.index('Each additional supported feature')
                separate = text.index('Separate commitments are scored separately')
                remainder = text[additional:separate].strip()
                prefix = 'Each additional supported feature is worth between '
                assert remainder.startswith(prefix)
                revised.append({'type': 'numbered', 'number': 3, 'runs': [
                    {'text': 'Each additional contract feature introduced in the negotiation is worth '},
                    {'text': 'between', 'bold': True, 'underline': True},
                    {'text': ' ' + remainder[len(prefix):]},
                ]})
                if policy == 'open':
                    revised.append({'type': 'numbered', 'number': 4,
                                    'runs': [{'text': 'You are not limited to the job features described or suggested here. '
                                              'You may creatively introduce other plausible contract features or job arrangements.',
                                              'bold': True}]})
                    revised.append({'type': 'numbered', 'number': 5, 'runs': [{'text':
                        "Some features you introduce may not fit the situation and will be worth 0 points. "
                        "But that doesn't mean you should hold back on creative and thoughtful ideas!"}]})
                else:
                    revised.append({'type': 'numbered', 'number': 4, 'runs': [{'text':
                        'You are limited to the job features described or suggested in these materials. '
                        'Features outside this set are not negotiable and do not affect your score.', 'bold': True}]})
            continue
        revised.append(block)
    return revised


def normalize_words(value):
    return re.sub(r'\s+', ' ', value).strip()


def presentation_parts(blocks):
    """Split selected long paragraphs at exact source phrases, without rewriting.

    Each item is (source block, start, end, kind). Exact phrase checks make a
    future role rewrite fail visibly instead of silently putting bullets wrong.
    """
    output = []
    for block in blocks:
        text = ''.join(r.get('text', '') for r in block['runs'])
        kind = 'heading' if block.get('type') == 'heading' else (
            'number_' + str(block['number']) if block.get('type') == 'numbered' else 'paragraph')
        starts = [(0, kind)]
        boundaries = []
        if block.get('type') == 'numbered':
            pass
        elif text.startswith('You prefer a '):
            boundaries = [('Annual salary may range', 'bullet'),
                          ('Starting dates may range', 'bullet'),
                          ('The personal budget may range', 'bullet'),
                          ('The platform calculates', 'paragraph'),
                          ('For example,', 'worked_example')]
        elif text.startswith('On the way home,'):
            boundaries = [('Still, more flexibility', 'paragraph'),
                          ('For vacation,', 'bullet'), ('For remote work,', 'bullet'),
                          ('The two terms are scored', 'paragraph')]
        elif text.startswith('Looking over your notes,'):
            boundaries = [('Still, the sales manager', 'paragraph'),
                          ('A longer probation', 'bullet'),
                          ('Contract length works', 'bullet'),
                          ('The two terms are scored', 'paragraph')]
        elif text.startswith("You also remember the Recruiter's stories"):
            boundaries = [('One new hire', 'bullet'), ('Someone else', 'bullet'),
                          ('Those examples appealed', 'paragraph')]
        elif text.startswith('Other stories were less appealing.'):
            boundaries = [('The Recruiter joked', 'bullet'),
                          ('The company regularly shares', 'bullet'),
                          ('… You enjoy people,', 'paragraph')]
        elif text.startswith('Other parts of the conversation'):
            boundaries = [('The Candidate was personable', 'bullet'),
                          ('The company regularly shares', 'bullet'),
                          ('… Conference presentations', 'bullet')]
        elif text.startswith("You also remember the Candidate's interest"):
            boundaries = [('The Candidate was also curious', 'paragraph')]
        elif text.startswith('That evening, your spouse asked'):
            boundaries = [('Sponsored membership', 'bullet'),
                          ('The question about leaving', 'bullet'),
                          ('You want to show commitment', 'bullet')]
        elif text.startswith("The Candidate's question about waiving"):
            boundaries = [('You understand why future flexibility', 'bullet'),
                          ('But if they later leave', 'bullet'),
                          ('You want the new hire to develop', 'bullet')]
        elif text.startswith('Your objective is to reach'):
            required_transition = ('Every complete offer must include'
                                   if 'Every complete offer must include' in text
                                   else 'Every offer must address all 15 job terms')
            boundaries = [(required_transition, 'paragraph')]
        elif text.startswith('Your score is private'):
            starts[0] = (0, 'payment_note')
            boundaries = [('You may propose', 'bullet'),
                          ('An agreement requires', 'bullet')]
        elif text.startswith('The researchers set the scoring rules'):
            boundaries = [('Each additional supported feature', 'paragraph'),
                          ('Separate commitments', 'paragraph'),
                          ('You are not limited', 'paragraph'),
                          ('If an idea has no scoring rule', 'paragraph')]
        elif text.startswith('For example:'):
            starts[0] = (0, 'example')
        for phrase, kind in boundaries:
            assert text.count(phrase) == 1, 'Update presentation boundary: ' + phrase
            starts.append((text.index(phrase), kind))
        assert [a for a, _ in starts] == sorted(a for a, _ in starts)
        for i, (start, kind) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            output.append((block, start, end, kind))
    return output


def inline_text(block, start, end):
    text = ''.join(r.get('text', '') for r in block['runs'])
    bold = [flag for run in block['runs']
            for flag in [bool(run.get('bold'))] * len(run.get('text', ''))]
    underline = [flag for run in block['runs']
                 for flag in [bool(run.get('underline'))] * len(run.get('text', ''))]
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    # Match zero only in explicit payoff contexts, never inside dates or money.
    special = re.compile(r'\b(?:Candidate|Recruiter)\b|[+−-]\d+(?:\.\d+)?'
                         r'|(?<=gives you )0\b(?![.,]\d)|(?<![\w.,$])0(?= points\b)', re.I)
    result = []

    def ordinary(a, b):
        # Combine contiguous formatting before adding delimiters, so no ****.
        while a < b:
            stop = a + 1
            while stop < b and (bold[stop], underline[stop]) == (bold[a], underline[a]):
                stop += 1
            raw = text[a:stop]
            if bold[a] and raw.strip():
                lead = raw[:len(raw) - len(raw.lstrip())]
                trail = raw[len(raw.rstrip()):]
                value = html.escape(raw.strip(), quote=False)
                if underline[a]:
                    value = '<u>' + value + '</u>'
                result.append(lead + '**' + value + '**' + trail)
            else:
                value = html.escape(raw, quote=False)
                result.append('<u>' + value + '</u>' if underline[a] else value)
            a = stop

    cursor = start
    for match in special.finditer(text, start, end):
        ordinary(cursor, match.start())
        value = html.escape(match.group(), quote=False)
        if match.group()[0] in '+−-':
            positive = match.group()[0] == '+'
            date_endpoint = (text[start:end].startswith('Starting dates may range') and
                             match.group() in ('+1', '−3', '-3'))
            if match.group() in ('+2', '−2', '-2') or date_endpoint:
                value = '<u>' + value + '</u>'
            result.append('<strong style="color:' + (GREEN if positive else RED) + ';">' + value + '</strong>')
        elif match.group() == '0':
            result.append('<strong style="color:' + BLUE + ';">0</strong>')
        else:
            value = '<em>' + value + '</em>'
            result.append('**' + value + '**' if bold[match.start()] else value)
        cursor = match.end()
    ordinary(cursor, end)
    return ''.join(result)


def role_narrative(blocks, policy='open'):
    parts = []
    for block, start, end, kind in presentation_parts(review_blocks(blocks, policy=policy)):
        value = inline_text(block, start, end)
        # A soft break keeps each neutral option within its original bullet.
        # Retain a space too so tag-stripping readers do not join adjacent words.
        if kind == 'bullet':
            for opening, neutral in (
                ('Annual salary may range', '$50,000 gives you '),
                ('Starting dates may range', 'around 8 June gives you '),
                ('The personal budget may range', '$10,000 gives you '),
            ):
                if value.startswith(opening):
                    assert value.count(', ' + neutral) == 1
                    value = value.replace(', ' + neutral, ', <br>' + neutral, 1)
        if kind in ('example', 'worked_example'):
            value = '<span style="display:block;margin-left:1.5em;"><em>' + value + '</em></span>'
        elif kind == 'payment_note':
            value = '<em style="color:' + RED + ';">' + value + '</em>'
        elif kind == 'number_4':
            value = '<span style="color:' + DARK_BLUE + ';">' + value + '</span>'
        prefix = '• ' if kind == 'bullet' else (kind.split('_')[1] + '. ' if kind.startswith('number_') else '')
        # The external reader treats each blank-line chunk as a paragraph.
        # Explicit block styling therefore indents the marker and aligns every
        # wrapped line with the item text, without relying on list CSS support.
        item = prefix + value
        parts.append(LIST_WRAPPER + item + '</span>' if prefix else item)
    output = []
    for part in parts:
        separator = ('\n' if output and output[-1].startswith(LIST_WRAPPER)
                     and part.startswith(LIST_WRAPPER) else '\n\n')
        if output:
            output.append(separator)
        output.append(part)
    return ''.join(output)


def narrative_blocks(narrative):
    """Split paragraphs plus compact consecutive display-block list items."""
    return [part for part in re.split(
        r'\n\n|(?<=</span>)\n(?=<span style="display:block)', narrative
    ) if part]


def narrative_to_html(narrative):
    """Preview our generated/escaped narrative, NOT arbitrary external HTML.

    This is not a sanitizer. Only call on role_narrative output. Participant
    input is never rendered by this function. No script, iframe or external asset
    is generated. The deployed Empirica reader must still be checked separately.
    """
    output = []
    listing = None
    for paragraph in narrative_blocks(narrative):
        paragraph = unwrap_list_item(paragraph)
        bullet = paragraph.startswith('• ')
        number = re.match(r'^([1-5])\. ', paragraph)
        current_list = 'ul' if bullet else ('ol' if number else None)
        value = paragraph[2:] if bullet else (paragraph[number.end():] if number else paragraph)
        value = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', value, flags=re.S)
        if current_list != listing:
            if listing:
                output.append('</' + listing + '>')
            if current_list:
                output.append('<' + current_list + ' style="padding-left:2.75em;margin:0 0 1em;list-style-position:outside;">')
            listing = current_list
        if current_list:
            output.append('<li style="margin:.4em 0;">' + value + '</li>')
        elif re.fullmatch(r'\*\*.*\*\*', paragraph) and len(re.sub('<[^>]+>', '', value)) < 60:
            output.append('<h3 style="font-size:1.1em;margin:1.6em 0 .6em;">' + value + '</h3>')
        else:
            output.append('<p style="margin:0 0 1em;">' + value + '</p>')
    if listing:
        output.append('</' + listing + '>')
    return '\n'.join(output)
