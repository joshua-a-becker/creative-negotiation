"""Small, synthetic release checks; no keys, API calls or research data needed.

Run from the repository folder: python developer/test_scorer.py
These checks cover known rules, not every possible natural-language offer.
"""
import itertools
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app/backend'))
import offer_engine as engine
from scenario_rules import own_acceptance_allowed, private_payoff_rows
from scorer_routing import escalation_reasons

BASE = 'Salary $50,000, personal budget $15,000, starting date June 1. '
LINK = 'Regular Social Media Posts for Company'
OLD_LINK = 'Regular Linkedin Posts for Company'


def link_for(name):
    return OLD_LINK if name == 'large-200' else LINK


def scenario(name='small-15'):
    return json.loads((ROOT / 'app/config' / (name + '.json')).read_text(encoding='utf-8'))


def evaluate(text, name='small-15', extraction=None):
    config = scenario(name)
    return engine.evaluate_offer(text, 'Candidate', extraction or {
        'pairs': [], 'ambiguities': [], 'unsupported_terms': [],
        'novel_terms': [], 'offer_intent': 'offer',
    }, {}, config['required_issues'], config)


def interpreted_core(salary='$50,000', budget='$15,000', start='June 1'):
    # Supply the interpretation normally returned by the LLM. These offline
    # checks exercise validation/arithmetic, not a substitute language model.
    return {'offer_intent': 'offer', 'pairs': [
        {'issue': issue, 'option': value, 'confidence': 1}
        for issue, value in zip(('Salary', 'Personal Budget', 'Starting Date'),
                                (salary, budget, start))
    ]}


def interpreted_terms(terms=None, novel_terms=None):
    extraction = interpreted_core()
    extraction['pairs'].extend(
        {'issue': issue, 'option': value, 'confidence': 1}
        for issue, value in (terms or {}).items()
    )
    extraction['novel_terms'] = novel_terms or []
    return extraction


class ScorerChecks(unittest.TestCase):
    def test_all_scenarios_are_distinct(self):
        ids = []
        for name, count, required in [('tutorial', 9, 3), ('small-15', 15, 3),
                                      ('large-200', 200, 3), ('fixed-15', 15, 15)]:
            config = scenario(name)
            ids.append(config['scenario_id'])
            self.assertEqual(len(config['issues']), count)
            self.assertEqual(len(config['required_issues']), required)
        self.assertEqual(len(set(ids)), 4)

    def test_flexible_core_and_fixed_omission(self):
        for name in ('small-15', 'large-200'):
            self.assertEqual(evaluate(BASE, name, interpreted_core())['decision'], 'scorable')
        self.assertNotEqual(evaluate(BASE, 'fixed-15', interpreted_core())['decision'], 'scorable')

    def test_negative_proposals_are_not_system_errors(self):
        result = evaluate('Salary $35,000, personal budget $5,000, starting September 30.',
                          extraction=interpreted_core('$35,000', '$5,000', 'September 30'))
        self.assertEqual(result['decision'], 'scorable')
        self.assertLess(result['total'], 0)
        self.assertEqual(escalation_reasons('simple offer', {'pairs': []},
                         {'decision': 'scorable', 'total': -6, 'valid_pairs': {}}), [])

    def test_agreement_requires_positive_finite_value(self):
        for name in ('small-15', 'large-200', 'fixed-15'):
            for value in (None, False, -1, 0, float('nan'), float('inf')):
                self.assertFalse(own_acceptance_allowed(scenario(name), value))
            self.assertTrue(own_acceptance_allowed(scenario(name), 0.0001))

    def test_fixed_private_table_uses_current_matrix(self):
        for role in ('Candidate', 'Recruiter'):
            self.assertEqual(len(private_payoff_rows(scenario('fixed-15'), role)), 15)

    def test_recalibrated_starting_date_and_large_bonus_cap(self):
        for name in ('fixed-15', 'small-15', 'large-200'):
            config = scenario(name)
            start = next(issue for issue in config['issues'] if issue['id'] == 'starting_date')
            self.assertEqual(start['payoff'], {
                'Candidate': {'min': 1, 'max': -3},
                'Recruiter': {'min': 1, 'max': -3},
            })
            self.assertIn('2026-06-08', start['samples'])
            for role in ('Candidate', 'Recruiter'):
                self.assertEqual(engine.score_pair('Starting Date', 'May 1', role, {}, config)[1], 1)
                self.assertEqual(engine.score_pair('Starting Date', 'June 8', role, {}, config)[1], 0)
                self.assertEqual(engine.score_pair('Starting Date', 'July 16', role, {}, config)[1], -1)
                self.assertEqual(engine.score_pair('Starting Date', 'September 30', role, {}, config)[1], -3)
        self.assertIsNone(scenario('fixed-15')['payment']['agreement_bonus_cap_usd'])
        self.assertIsNone(scenario('small-15')['payment']['agreement_bonus_cap_usd'])
        self.assertEqual(scenario('large-200')['payment']['agreement_bonus_cap_usd'], 15)

    def test_negative_duty_list_in_any_order(self):
        duties = ['organizing team events', 'LinkedIn publicity', 'conference presentations']
        for name, parts in itertools.product(('small-15', 'large-200'), itertools.permutations(duties)):
            text = BASE + 'I am not proposing recurring responsibility for ' + ', '.join(parts[:-1]) + ', or ' + parts[-1] + '.'
            with self.subTest(scenario=name, order=parts):
                self.assertEqual(evaluate(text, name)['valid_pairs'].get(link_for(name)), 'No commitment')

    def test_negative_list_grammar_variants(self):
        for prefix in ('We are not proposing responsibilities for',
                       'The company is not proposing any regular responsibility for',
                       'I do not propose recurring responsibility for'):
            self.assertEqual(evaluate(BASE + prefix + ' conference presentations and LinkedIn publicity.')['valid_pairs'].get(LINK), 'No commitment')

    def test_positive_posting_after_other_refusal(self):
        result = evaluate(BASE + 'I am not proposing responsibility for organizing team events, but I will write two LinkedIn posts per month.')
        self.assertEqual(result['valid_pairs'].get(LINK), 'Commitment')

    def test_generic_publicity_does_not_invent_a_platform(self):
        result = evaluate(BASE + 'I am not proposing recurring responsibility for generic publicity or conference presentations.')
        self.assertNotIn(LINK, result['valid_pairs'])

    def test_source_quotes_must_be_grounded(self):
        text = 'I am not proposing recurring responsibility for LinkedIn publicity.'
        self.assertTrue(engine.source_quote_is_grounded('not proposing ... LinkedIn publicity', text))
        self.assertFalse(engine.source_quote_is_grounded('I will write LinkedIn posts', text))

    def test_neighboring_numbers_do_not_change_noncompete_scope(self):
        for text in ('Six months of probation and retaining the standard non-compete',
                     'Keep the non-compete and six months probation',
                     'A two-year contract, only two remote days, and keep the non-compete',
                     'Keep the standard non-compete, with a six-month probation period'):
            self.assertIsNone(engine._noncompete_scope_detail(text), text)

    def test_real_noncompete_scope_is_preserved(self):
        for text in ('A six-month non-compete and a two-year contract',
                     'Keep the non-compete for six months and allow 40 vacation days',
                     'The non-compete remains and is limited to six months'):
            self.assertIsNotNone(engine._noncompete_scope_detail(text), text)
        detail = engine._noncompete_scope_detail('A non-compete limited to direct competitors and active company clients and the western region, and a six-month probation')
        self.assertIn('active company clients', detail)
        self.assertIn('western region', detail)
        self.assertNotIn('probation', detail)

    def test_scope_identity_does_not_change_with_other_terms(self):
        a = engine._noncompete_scope_detail('A three-month probation, a two-year contract, and a non-compete limited to six months')
        b = engine._noncompete_scope_detail('A six-month probation, a four-year contract, and a non-compete limited to six months')
        self.assertEqual(a, b)

    def test_scope_continues_across_clauses(self):
        _, details, _ = engine._repair_semantic_details([], 'Keep the non-compete, but it is limited to direct competitors.', scenario())
        self.assertTrue(any(item['issue'] == 'Non-compete Clause' for item in details))

    def test_tutorial_shorthand_and_punctuation(self):
        for text in (': “I can pay $300 for the venue on August 8 next year and close at 7 p.m.”',
                     '300 bucks for the venue on 8 Aug, end at 7, and include projector use.',
                     'Close at 7pm, August 8 next year, 300 for the venue.'):
            result = evaluate(text, 'tutorial')
            self.assertEqual(result['decision'], 'scorable', result)
            self.assertEqual(len(result['valid_pairs']) >= 3, True)
            self.assertNotIn('Salary', result['valid_pairs'])

    def test_tutorial_door_staff_and_food_are_scored(self):
        cases = (
            ('$500, sept 1, end at 10pm, door staff provided, free food',
             'Venue provides door staff', 'Venue provides refreshments at no extra charge'),
            ('Free snacks, entrance staff included, September 1, close at 10, $500 venue fee',
             'Venue provides door staff', 'Venue provides refreshments at no extra charge'),
            ('Our volunteers bring refreshments and staff the door; end at 10, fee $500, 1 Sep',
             'Organizer provides door staff', 'Organizer provides refreshments'),
            ('No food included; venue security staff provided; close at 10pm; Sept 1; venue costs 500 USD',
             'Venue provides door staff', 'No refreshments included'),
        )
        for text, staffing, food in cases:
            with self.subTest(text=text):
                result = evaluate(text, 'tutorial')
                self.assertEqual(result['decision'], 'scorable', result)
                self.assertEqual(result['valid_pairs'].get('Door staffing'), staffing)
                self.assertEqual(result['valid_pairs'].get('Food and refreshments'), food)
                self.assertEqual(len(result['valid_pairs']), 5)

    def test_tutorial_recognized_terms_override_model_unsupported_warning(self):
        text = '$500, sept 1, end at 10pm, door staff provided, free food'
        extraction = {
            'pairs': [], 'ambiguities': [], 'offer_intent': 'offer',
            'unsupported_terms': ['door staff provided', 'free food'],
            'novel_terms': [],
        }
        result = evaluate(text, 'tutorial', extraction)
        self.assertEqual(result['decision'], 'scorable', result)
        self.assertFalse(any(item['code'] == 'unsupported_terms' for item in result['findings']))

    def test_tutorial_keeps_a_genuine_new_term_unscored(self):
        text = '$500, sept 1, end at 10pm, with reserved parking for guests'
        extraction = {
            'pairs': [], 'ambiguities': [], 'unsupported_terms': [],
            'novel_terms': ['reserved parking for guests'], 'offer_intent': 'offer',
        }
        result = evaluate(text, 'tutorial', extraction)
        self.assertEqual(result['decision'], 'scorable', result)
        self.assertEqual(result['novel_terms'], ['reserved parking for guests'])
        self.assertIn('Recorded new terms (not scored yet)', result['display_text'])

    def test_agreeing_post_content_is_not_optional_participation(self):
        for name, verb in itertools.product(('small-15', 'large-200'),
                                            ('I will write', 'You would make', 'The candidate will publish')):
            text = BASE + verb + ' regular LinkedIn posts with mutually agreed topics and timing.'
            issue = link_for(name)
            result = evaluate(text, name, interpreted_terms({issue: 'Commitment'}))
            self.assertEqual(result['valid_pairs'].get(issue), 'Commitment', text)

    def test_actual_posting_opt_outs_remain_optional(self):
        for qualification in ('if I choose to participate', 'only when mutually agreed',
                              'on a voluntary basis', 'subject to mutual agreement about whether to participate'):
            text = BASE + 'I would make regular LinkedIn posts ' + qualification + '.'
            result = evaluate(text, 'large-200', interpreted_terms({OLD_LINK: 'No commitment'}))
            self.assertEqual(result['valid_pairs'].get(OLD_LINK), 'No commitment', text)
        text = BASE + 'I may write regular LinkedIn posts with mutually agreed content, but participation is voluntary.'
        self.assertEqual(evaluate(text, extraction=interpreted_terms({LINK: 'No commitment'}))['valid_pairs'].get(LINK), 'No commitment')

    def test_duty_alternatives_need_one_chosen_package(self):
        for name, alternatives in itertools.product(('small-15', 'large-200'),
                ('a recruitment fair or a conference presentation',
                 'a conference presentation or a recruitment fair')):
            result = evaluate(BASE + 'I will participate in ' + alternatives + '.', name, interpreted_core())
            self.assertEqual(result['decision'], 'clarification_needed')
            self.assertTrue(any(f['code'] == 'alternative_duties' for f in result['findings']))

    def test_refusing_both_duties_is_not_an_unresolved_alternative(self):
        text = BASE + 'No recruitment fair or conference presentations would be required.'
        result = evaluate(text, extraction=interpreted_core())
        self.assertFalse(any(f['code'] == 'alternative_duties' for f in result['findings']))

    def test_voluntary_predicate_applies_to_whole_duty_list(self):
        for duties in ('Recruitment fairs, conference presentations, team-event organization, and LinkedIn publicity',
                       'Conference presentations, team-event organization, LinkedIn publicity, and recruitment fairs'):
            text = BASE + duties + ' would be occasional and voluntary.'
            result = evaluate(text, 'large-200', interpreted_terms({'Role in Recruitment Fair': 'No commitment'}))
            self.assertEqual(result['valid_pairs'].get('Role in Recruitment Fair'), 'No commitment')

    def test_mentor_frequency_does_not_change_training_frequency(self):
        text = BASE + 'Professional training sessions, mentoring with weekly meetings, and 30 vacation days.'
        result = evaluate(text, extraction=interpreted_core())
        self.assertFalse(any(d['issue'] == 'Professional Training Program' for d in result['unpriced_details']))
        text = BASE + 'Weekly professional training sessions, mentoring, and 30 vacation days.'
        result = evaluate(text, extraction=interpreted_core())
        self.assertTrue(any(d['issue'] == 'Professional Training Program' for d in result['unpriced_details']))

    def test_same_scored_value_is_not_a_new_issue(self):
        for issue, value, term in (
            ('Contract Length', '3 years', 'an initial three-year contract'),
            ('Remote Working Days', '4 days per week', 'the ability to work remotely four days per week'),
        ):
            result = evaluate(BASE + term + '.', 'large-200', interpreted_terms({issue: value}, [term]))
            self.assertEqual(result['novel_terms'], [])
            self.assertIn(issue, result['valid_pairs'])

    def test_genuine_new_qualifications_are_preserved(self):
        terms = {'Contract Length': '3 years', 'Remote Working Days': '4 days per week'}
        for term in ('an initial three-year contract with automatic renewal',
                     'the ability to work remotely four days per week with free home equipment'):
            text = BASE + 'A three-year contract and four remote days per week. ' + term + '.'
            result = evaluate(text, 'large-200', interpreted_terms(terms, [term]))
            self.assertIn(term, result['novel_terms'])

    def test_unknown_terms_are_visible_in_open_space_and_blocked_in_bounded_spaces(self):
        term = 'reserved parking for visiting clients'
        open_result = evaluate(BASE + term + '.', 'large-200', interpreted_terms(novel_terms=[term]))
        self.assertEqual(open_result['decision'], 'scorable', open_result)
        self.assertIn(term, open_result['novel_terms'])
        self.assertIn('Recorded new terms (not scored yet)', open_result['display_text'])
        for name in ('small-15', 'fixed-15'):
            result = evaluate(BASE + term + '.', name, interpreted_terms(novel_terms=[term]))
            self.assertEqual(result['decision'], 'rejected', result)
            self.assertTrue(any(item['code'] == 'model_unsupported_terms' for item in result['findings']))
            self.assertEqual(result['novel_terms'], [])

    def test_unscored_or_different_value_is_not_silently_dropped(self):
        term = 'the ability to work remotely four days per week'
        for terms, suffix in (({}, ''), ({'Remote Working Days': '3 days per week'}, 'Three remote days per week.')):
            result = evaluate(BASE + suffix, 'large-200', interpreted_terms(terms, [term]))
            self.assertIn(term, result['novel_terms'])

    def test_one_fallback_and_no_retry_on_transport_failure(self):
        # Mock model interpretation only; run the real routing and rule checks.
        import stream
        first = {'pairs': [], 'offer_intent': 'offer', '_usage': {'input_tokens': 10, 'output_tokens': 5}}
        second = {'pairs': [], 'offer_intent': 'offer', '_usage': {'input_tokens': 20, 'output_tokens': 9}, '_model': 'gpt-5.6-luna'}
        with patch.object(stream, 'SCENARIO', scenario()), patch.object(stream, 'PROVIDER', 'openai'), patch.object(stream, 'ROUTING', 'nano-luna'):
            with patch.object(stream, '_llm_extract_once', side_effect=[first, second]) as call:
                result = stream.llm_extract('Salary 50k; budget 15k; start June 1; contract two years')
                self.assertEqual(call.call_count, 2)
                self.assertEqual(call.call_args_list[0].args, call.call_args_list[1].args)
                self.assertEqual(result['_usage']['input_tokens'], 30)
            with patch.object(stream, '_llm_extract_once', side_effect=RuntimeError('connection unavailable')) as call:
                with self.assertRaises(RuntimeError):
                    stream.llm_extract(BASE)
                self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
