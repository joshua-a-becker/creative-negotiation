"""Offline checks for the public feedback materials; standard library only."""
import hashlib
import json
import re
import unittest
from build_experiment_materials import CONFIG, OUT, HTML_NAME, ROOT, Document, role_markdown, surveys_from_html, survey_yaml
from role_presentation import role_narrative, narrative_to_html, normalize_words, review_blocks, GREEN, RED, SCORING_HEADING
from role_presentation import BLUE, DARK_BLUE, LIST_WRAPPER, unwrap_list_item, inline_text, narrative_blocks
from html import unescape
import sys

sys.path.insert(0, str(ROOT / 'mockup'))
from build_mockup import load_scenarios


class MaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(CONFIG.read_text(encoding='utf-8'))
        cls.roles = json.loads((OUT / 'role_materials_200.json').read_text(encoding='utf-8'))
        cls.html = (OUT / HTML_NAME).read_text(encoding='utf-8')
        cls.surveys = surveys_from_html(cls.html)

    def test_narrative_schema_matches_existing_format(self):
        self.assertEqual(set(self.roles), {'roles', 'tips'})
        self.assertEqual([r['role_name'] for r in self.roles['roles']], ['Candidate', 'Recruiter'])
        for role in self.roles['roles']:
            self.assertEqual(set(role), {'role_name', 'narrative', 'RP', 'scoresheet'})
            self.assertEqual(role['RP'], 0)
            self.assertEqual(role['scoresheet'], {})

    def test_narratives_have_current_wording_and_formatting(self):
        for role in self.roles['roles']:
            source = self.source['roles'][role['role_name']]
            self.assertEqual(role['narrative'], role_narrative(source['full_blocks']))
            # Inline tags should not split words; block boundaries may add space.
            html = narrative_to_html(role['narrative'])
            html = re.sub(r'</(?:p|h3|li)>', ' ', html)
            plain = normalize_words(unescape(re.sub('<[^>]*>', '', html)))
            expected = ' '.join(''.join(r.get('text', '') for r in b['runs'])
                                for b in review_blocks(source['full_blocks']))
            self.assertEqual(plain, normalize_words(expected))
            self.assertIn('**salary**', role['narrative'])
            self.assertIn('You are not limited to the job features', role['narrative'])
            self.assertIn('accept only an offer worth more than zero', role['narrative'])

    def test_separate_role_exports(self):
        for role in self.roles['roles']:
            path = OUT / (role['role_name'].lower() + '_role_materials_200.json')
            single = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(single, {'roles': [role], 'tips': self.roles['tips']})
            self.assertEqual(len(single['roles']), 1)

    def test_empirica_reader_leaves_no_visible_asterisks(self):
        # Reproduce the bold-only behavior visible in the participant screenshot.
        # Check the combined/legacy link and both single-role links, not just one.
        for name in ('role_materials_200.json', 'candidate_role_materials_200.json',
                     'recruiter_role_materials_200.json'):
            exported = json.loads((OUT / name).read_text(encoding='utf-8'))
            for role in exported['roles']:
                text = role['narrative']
                self.assertNotIn('***', text)
                visible = re.sub(r'\*\*(.+?)\*\*', r'\1', text, flags=re.S)
                self.assertNotIn('*', visible, name + ': unsupported emphasis')
                self.assertIn('**You are not limited to the job features', text)

    def test_requested_readability_and_point_styles(self):
        for role in self.roles['roles']:
            text = role['narrative']
            self.assertGreaterEqual(text.count('• '), 8)
            self.assertIn('<em>For example,', text)
            self.assertIn('<em>**For example:**', text)
            self.assertIn('<u>+2</u>', text)
            self.assertIn('<u>−2</u>', text)
            self.assertIn('color:' + BLUE, text)
            self.assertIn('color:' + GREEN, text)
            self.assertIn('color:' + RED, text)
            for name in ('Candidate', 'Recruiter'):
                self.assertNotRegex(text, r'(?<!<em>)\b' + name + r'\b')
            self.assertNotIn('<script', text)
            self.assertNotIn('<iframe', text)
            self.assertNotRegex(text, r'\bon\w+=')
            self.assertNotIn('javascript:', text)
            self.assertIn('<ul ', narrative_to_html(text))

    def test_formatted_payload_matches_local_reading_and_review(self):
        match = re.search(r'const ROLE_PRESENTATION = (\{.*?\});\n', self.html)
        presentation = json.loads(match.group(1))
        for role in self.roles['roles']:
            self.assertEqual(presentation[role['role_name']], narrative_to_html(role['narrative']))
        self.assertIn('return ROLE_PRESENTATION[role]', self.html)

    def test_short_budget_instruction_and_final_scoring_section(self):
        for role in self.roles['roles']:
            text = role['narrative']
            self.assertIn('**salary**, a **starting date**, and a **personal budget for work expenses**', text)
            self.assertIn('(but not take-home pay!).', text)
            self.assertNotIn('The budget is an annual allowance', text)
            self.assertNotIn('unused money stays with the company', text)
            self.assertNotIn('bonus cap', text.lower())
            self.assertNotIn('maximum bonus', text.lower())
            self.assertIn('<span style="display:block;margin-left:1.5em;"><em>For example,', text)
            self.assertIn('<em style="color:' + RED + ';">**Your score**', text)
            for phrase in ('translates', 'bonus payment you', 'earn'):
                self.assertIn('**' + phrase + '**', text)
            self.assertLess(text.index('**INSTRUCTIONS**'), text.index('**' + SCORING_HEADING + '**'))
            self.assertIn('Starting dates may range from 1 May to 30 September: 1 May gives you '
                          '<strong style="color:' + GREEN + ';"><u>+1</u></strong>', text)
            self.assertIn('around 8 June gives you <strong style="color:' + BLUE + ';">0</strong>', text)
            self.assertIn('30 September gives you <strong style="color:' + RED + ';"><u>−3</u></strong>', text)
            headings = re.findall(r'<h3[^>]*>(.*?)</h3>', narrative_to_html(text), flags=re.S)
            self.assertEqual(re.sub('<[^>]+>', '', headings[-1]), SCORING_HEADING)
        candidate = self.roles['roles'][0]['narrative']
        for phrase in ('Sponsored membership', 'The question about leaving', 'You want to show commitment'):
            self.assertIn('• ' + phrase, candidate)

    def test_review_edits_do_not_mutate_approved_source(self):
        from copy import deepcopy
        for role in ('Candidate', 'Recruiter'):
            blocks = deepcopy(self.source['roles'][role]['full_blocks'])
            before = deepcopy(blocks)
            revised = review_blocks(blocks)
            self.assertEqual(blocks, before)
            self.assertNotEqual(revised, blocks)
            self.assertNotIn(SCORING_HEADING, self.source['roles'][role]['full_text'])

    def test_acceptance_names_the_italicized_counterpart(self):
        for role in self.roles['roles']:
            other = 'Recruiter' if role['role_name'] == 'Candidate' else 'Candidate'
            self.assertIn('An agreement requires both parties to accept the same offer, '
                          'with a positive total score for you and the <em>' + other + '</em>.',
                          role['narrative'])
            self.assertNotIn('Individual terms may still be worth zero or less.', role['narrative'])
            self.assertNotIn('with a positive total score for each.', role['narrative'])

    def test_symmetric_order_transitions_and_five_numbered_notes(self):
        notes_by_role = []
        for role in self.roles['roles']:
            text = role['narrative']
            self.assertLess(text.index('Annual salary may range'), text.index('Starting dates may range'))
            self.assertLess(text.index('Starting dates may range'), text.index('The personal budget may range'))
            self.assertLess(text.index('The personal budget may range'), text.index('The platform calculates'))
            self.assertIn('However, the interview also left you thinking', text)
            self.assertEqual(text.count('… '), 1)
            parts = [unwrap_list_item(p) for p in narrative_blocks(text)]
            at = parts.index('**' + SCORING_HEADING + '**')
            notes = parts[at + 1:]
            self.assertEqual(len(notes), 5)
            self.assertEqual([p[:3] for p in notes], [f'{i}. ' for i in range(1, 6)])
            self.assertTrue(notes[0].startswith('1. Without a deal,'))
            self.assertTrue(notes[1].startswith('2. The researchers set'))
            self.assertIn('Each additional contract feature introduced in the negotiation is worth **<u>between</u>**', notes[2])
            self.assertEqual(notes[1], '2. The researchers set the scoring rules in advance, and the platform '
                             'calculates points automatically; you do not assign or calculate points yourself.')
            self.assertEqual(notes[3], '4. <span style="color:' + DARK_BLUE + ';">'
                             '**You are not limited to the job features described or suggested here. '
                             'You may creatively introduce other plausible contract features or job arrangements.**</span>')
            self.assertEqual(notes[4], '5. Some features you introduce may not fit the situation and will be worth '
                             '<strong style="color:' + BLUE + ';">0</strong> points. '
                             "But that doesn't mean you should hold back on creative and thoughtful ideas!")
            self.assertNotIn('Separate commitments are scored separately', text)
            self.assertNotIn('Each additional supported feature', text)
            self.assertNotIn('If an idea has no scoring rule', text)
            self.assertLess(text.index('**Your score**'), text.index('**' + SCORING_HEADING + '**'))
            ordered = re.findall(r'<ol[^>]*>(.*?)</ol>', narrative_to_html(text), flags=re.S)
            self.assertEqual(len(ordered), 1)
            self.assertEqual(ordered[0].count('<li '), 5)
            notes_by_role.append([re.sub(r'<em>(?:Candidate|Recruiter)</em>', 'OTHER_ROLE', p) for p in notes[1:]])
        self.assertEqual(notes_by_role[0], notes_by_role[1])
        self.assertIn('… You enjoy people,', self.roles['roles'][0]['narrative'])
        recruiter = self.roles['roles'][1]['narrative']
        for phrase in ('You understand why future flexibility', 'But if they later leave', 'You want the new hire to develop'):
            self.assertIn('• ' + phrase, recruiter)

    def test_offer_example_is_indented_italic_and_uses_reviewed_placeholder(self):
        examples = []
        for role in self.roles['roles']:
            matches = [p for p in role['narrative'].split('\n\n') if 'For example:' in p]
            self.assertEqual(len(matches), 1)
            example = matches[0]
            self.assertTrue(example.startswith('<span style="display:block;margin-left:1.5em;"><em>**For example:**'))
            self.assertTrue(example.endswith('</em></span>'))
            self.assertIn('together with [list any job features you want to bring up].” Use your own values and wording.', example)
            self.assertNotIn('any other terms I choose to raise', role['narrative'])
            self.assertEqual(unwrap_list_item(example), example)
            rendered = narrative_to_html(example)
            self.assertIn('<em><strong>For example:</strong>', rendered)
            self.assertNotIn('*', rendered)
            examples.append(example)
        self.assertEqual(examples[0], examples[1])

    def test_neutral_choices_break_inside_the_same_bullet(self):
        zero = '<strong style="color:' + BLUE + ';">0</strong>'
        for role in self.roles['roles']:
            narrative = role['narrative']
            self.assertEqual(narrative.count('<br>'), 3)
            for clause in ('$50,000 gives you ', 'around 8 June gives you ', '$10,000 gives you '):
                matching = [p for p in narrative_blocks(narrative) if clause in p]
                self.assertEqual(len(matching), 1)
                self.assertTrue(matching[0].startswith(LIST_WRAPPER + '• '))
                self.assertEqual(matching[0].count('• '), 1)
                self.assertEqual(matching[0].count('<br>'), 1)
                self.assertIn(', <br>' + clause + zero, matching[0])
            rendered = narrative_to_html(narrative)
            self.assertEqual(rendered.count('<li '), narrative.count('• ') + 5)
            self.assertEqual(rendered.count('<br>'), 3)

    def test_point_styles_do_not_change_money_dates_or_values(self):
        raw = '$40,000 gives you 0, $7,000 gives you −0.74 points; +2, −2 and -2. '
        raw += '16 July, $0.50, 0.74, 10,500, 20 and 0 points; an example gives you 0.74 points or 10.0 points.'
        rendered = inline_text({'runs': [{'text': raw}]}, 0, len(raw))
        self.assertEqual(rendered.count('color:' + BLUE), 2)
        for value in ('+2', '−2', '-2'):
            self.assertIn('<u>' + value + '</u>', rendered)
        self.assertNotIn('<u>−0.74</u>', rendered)
        self.assertEqual(unescape(re.sub('<[^>]*>', '', rendered)), raw.rstrip())

    def test_all_lists_have_explicit_hanging_indents(self):
        for role in self.roles['roles']:
            paragraphs = narrative_blocks(role['narrative'])
            wrapped = [p for p in paragraphs if p.startswith(LIST_WRAPPER)]
            self.assertEqual(len(wrapped), role['narrative'].count('• ') + 5)
            for p in wrapped:
                self.assertRegex(unwrap_list_item(p), r'^(?:• |[1-5]\. )')
                self.assertTrue(p.endswith('</span>'))
                self.assertIn('padding-left:1.25em;text-indent:-1.25em;', p)
            self.assertFalse(any(re.match(r'^(?:• |[1-5]\. )', p) for p in paragraphs))
            # Indentation must not change item wording, numbering or text count.
            unwrapped = '\n\n'.join(unwrap_list_item(p) for p in paragraphs)
            self.assertEqual(narrative_to_html(role['narrative']), narrative_to_html(unwrapped))
            example = next(p for p in paragraphs if 'margin-left:1.5em;"><em>For example,' in p)
            self.assertEqual(unwrap_list_item(example), example)

    def test_italic_and_mixed_runs_keep_words_spacing_and_bold(self):
        blocks = [{'runs': [
            {'text': 'The '}, {'text': 'Candidate', 'italic': True},
            {'text': "'s example: "}, {'text': 'For example:', 'bold': True},
            {'text': ' “An offer.”', 'italic': True},
        ]}, {'runs': [
            {'text': 'Important ', 'bold': True, 'italic': True},
            {'text': 'instruction', 'bold': True},
            {'text': ' and a note.', 'italic': True},
        ]}]
        self.assertEqual(role_markdown(blocks),
                         'The Candidate\'s example: **For example:** “An offer.”\n\n'
                         '**Important instruction** and a note.')
        self.assertIn('*Candidate*', role_markdown(blocks, preserve_italics=True))
        self.assertTrue(blocks[0]['runs'][1]['italic'])

    def test_surveys_have_no_unsupported_emphasis_markers(self):
        for survey in self.surveys.values():
            self.assertNotIn('*', json.dumps(survey, ensure_ascii=False))

    def test_q11_is_one_names_only_box_with_persistent_gray_guide(self):
        document = Document(self.html)
        field = document.by_id('otherFeatures')
        self.assertEqual(field.tag, 'textarea')
        self.assertEqual(field.attrs['name'], 'q11')
        self.assertIn('required', field.attrs)
        self.assertEqual(field.attrs['aria-describedby'], 'featureFormatHint')
        self.assertNotIn('id="addIssue"', self.html)
        self.assertNotIn('id="ideaRows"', self.html)
        self.assertIn('white-space:pre-line;color:#666', document.by_id('featureFormatHint').attrs['style'])
        for survey in self.surveys.values():
            q = survey['questions'][10]
            self.assertEqual(q['type'], 'open_text')
            self.assertEqual(q['hint'].count('\n'), 1)
            self.assertIn('only the name', q['hint'])
            self.assertEqual(q['placeholder'], '1. [Job feature]\n2. [Job feature]\n3. [Job feature]')
            for phrase in ('why', 'reason', 'justification', 'explain'):
                self.assertNotIn(phrase, json.dumps(q).lower())

    def test_counteroffer_has_intro_offer_and_response_in_that_order(self):
        for role, survey in self.surveys.items():
            other = 'Recruiter' if role == 'Candidate' else 'Candidate'
            parts = survey['questions'][8]['label'].split('\n\n')
            self.assertEqual(len(parts), 3)
            self.assertEqual(parts[0], f'Imagine that the {other} sends you this counteroffer:')
            self.assertTrue(parts[1].startswith(other + '’s counteroffer: “'))
            self.assertEqual(parts[2], 'What offer would you make to respond to them?')
        self.assertLess(self.html.index('id="candidateCounter"'), self.html.index('id="counterResponsePrompt"'))
        self.assertLess(self.html.index('id="recruiterCounter"'), self.html.index('id="counterResponsePrompt"'))

    def test_updated_labels_and_role_switch_preserve_inputs(self):
        for role, survey in self.surveys.items():
            other = 'Recruiter' if role == 'Candidate' else 'Candidate'
            self.assertEqual(survey['questions'][1]['label'],
                             f'The role materials helped me understand what may matter to the {other}.')
            self.assertEqual(survey['questions'][5]['label'],
                             'In your own words, what three job-contract terms must appear in every offer?')
            self.assertIn('multiple job/contract features', survey['questions'][7]['label'])
            self.assertIn('maximum 5', survey['questions'][10]['label'])
            self.assertNotIn('{other_role}', json.dumps(survey))
        role_switch = self.html.split('function preview(role){', 1)[1].split('\n  }', 1)[0]
        self.assertIn("document.getElementById('counterpartyName').textContent = otherRole", role_switch)
        self.assertNotIn('innerHTML', role_switch)

    def test_html_uses_exact_same_role_blocks(self):
        match = re.search(r'const ROLE_BLOCKS\s*=\s*(\{.*?\});(?=\s*let assignedRole)', self.html, re.S)
        blocks = json.loads(match.group(1))
        self.assertEqual(blocks, {r: self.source['roles'][r]['full_blocks'] for r in ('Candidate', 'Recruiter')})
        self.assertIn(hashlib.sha256(CONFIG.read_bytes()).hexdigest(), self.html)
        self.assertEqual(len(self.source['issues']), 215)

    def test_main_experiment_uses_shared_readable_role_presentation(self):
        scenarios = load_scenarios()
        for space in ('small', 'large', 'fixed'):
            for role in ('Candidate', 'Recruiter'):
                rendered = scenarios[space]['role_html'][role]
                self.assertIn('Important notes on offers and scoring', rendered)
                self.assertIn('<ul ', rendered)
                self.assertIn('<ol ', rendered)
                self.assertIn('color:' + GREEN, rendered)
                self.assertIn('color:' + RED, rendered)
                self.assertIn('color:' + BLUE, rendered)
                self.assertNotIn('The budget is an annual allowance', rendered)
                self.assertNotIn('*', rendered)
        for role in ('Candidate', 'Recruiter'):
            self.assertIn('You are not limited to the job features', scenarios['large']['role_html'][role])
            self.assertIn('You are limited to the job features described or suggested in these materials',
                          scenarios['small']['role_html'][role])
            self.assertIn('Do not add terms outside the private payoff table',
                          scenarios['fixed']['role_html'][role])
        self.assertIsNone(scenarios['small']['agreement_bonus_cap_usd'])
        self.assertIsNone(scenarios['fixed']['agreement_bonus_cap_usd'])
        self.assertEqual(scenarios['large']['agreement_bonus_cap_usd'], 15)

    def test_survey_schema_and_questions(self):
        allowed = {'likert', 'single_select', 'multi_select', 'open_text'}
        for role, survey in self.surveys.items():
            self.assertEqual(set(survey), {'scales', 'questions'})
            self.assertEqual([q['n'] for q in survey['questions']], list(range(1, 16)))
            self.assertEqual([q['id'] for q in survey['questions']], [f'q{i}' for i in range(1, 16)])
            self.assertTrue(all(q['type'] in allowed for q in survey['questions']))
            self.assertEqual((OUT / (role.lower() + '_feedback_survey.yaml')).read_text(encoding='utf-8'), survey_yaml(survey))
            self.assertEqual(survey['questions'][7]['options'], ['Yes', 'No'])
            self.assertEqual(len(survey['questions'][11]['options']), 8)
            self.assertIn('List 3 features. You may add up to 2 more (maximum 5).', survey['questions'][10]['hint'])

    def test_only_role_dependent_questions_differ(self):
        different = [i + 1 for i, (a, b) in enumerate(zip(self.surveys['Candidate']['questions'], self.surveys['Recruiter']['questions'])) if a != b]
        self.assertEqual(different, [2, 9, 12])
        self.assertIn('Recruiter’s counteroffer', self.surveys['Candidate']['questions'][8]['label'])
        self.assertIn('six-month probation', self.surveys['Candidate']['questions'][8]['label'])
        self.assertIn('Candidate’s counteroffer', self.surveys['Recruiter']['questions'][8]['label'])
        self.assertIn('four remote-working days', self.surveys['Recruiter']['questions'][8]['label'])

    def test_experience_is_five_point_likert(self):
        expected = ['None', 'A little', 'Some', 'Quite a lot', 'A great deal']
        for survey in self.surveys.values():
            q = survey['questions'][13]
            self.assertEqual(q['id'], 'q14')
            self.assertEqual(q['type'], 'likert')
            self.assertEqual(q['scale'], 'experience_5')
            self.assertEqual(survey['scales'][q['scale']], expected)
            self.assertNotIn('options', q)

    def test_participant_exports_do_not_contain_researcher_keys(self):
        for role, survey in self.surveys.items():
            text = json.dumps(survey)
            self.assertNotIn('Correct:', text)
            self.assertNotIn('Researcher answer key', text)
            self.assertNotIn('Noise:', text)
        self.assertIn('20%', self.roles['tips'])
        self.assertIn('2 to 7 days', self.roles['tips'])

    def test_no_credentials_or_broken_unicode_in_outputs(self):
        for path in OUT.iterdir():
            if path.suffix not in {'.json', '.yaml', '.html'}:
                continue
            content = path.read_text(encoding='utf-8')
            self.assertNotRegex(content, r'sk-[A-Za-z0-9_-]{20,}')
            self.assertNotIn('\ufffd', content)
            self.assertFalse(any(0xD800 <= ord(c) <= 0xDFFF for c in content))


if __name__ == '__main__':
    unittest.main(verbosity=2)
