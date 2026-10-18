"""Check this Empirica folder locally, without API keys or paid model calls."""

from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PACKAGE = Path(__file__).resolve().parents[1]


def main() -> None:
    for name in ('score_offer.py', 'score_tutorial_offer.py', 'flexible-215.json'):
        assert (PACKAGE / name).is_file(), f'Missing package file: {name}'
    for source in (PACKAGE / 'app/backend').glob('*.py'):
        ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    for definition in (PACKAGE / 'app/config').glob('*.json'):
        json.loads(definition.read_text(encoding='utf-8'))

    env = {key: value for key, value in os.environ.items()
           if 'KEY' not in key.upper()
           and key not in {'PYTHONPATH', 'PYTHONHOME', 'SCORER_DEFAULT_SPACE'}
           and not key.startswith('NEGOTIATOR_')}
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    defaults = {'Salary': 31213, 'Personal Budget': 7000, 'Starting Date': '2026-05-01',
                'Probation Length': 3, 'Contract Length': 3, 'Vacation Days': 30,
                'Remote Working Days': 3, 'Venue fee': 300, 'Event date': '2027-09-15'}
    spaces = {'15': ('small-15.json', 15), '215': ('large-215.json', 215),
              'fixed-15': ('fixed-15.json', 15), 'tutorial': ('tutorial.json', 9),
              '200': ('large-200.json', 200)}
    count = 0
    with tempfile.TemporaryDirectory(prefix='Empirica unrelated working directory ') as working:
        def call(script: str, *arguments: str) -> dict:
            nonlocal count
            result = subprocess.run([sys.executable, str(PACKAGE / script), *arguments],
                                    cwd=working, env=env, capture_output=True,
                                    text=True, encoding='utf-8', timeout=20)
            assert result.returncode == 0, result.stderr or result.stdout
            response = json.loads(result.stdout)
            count += 1
            return response

        for space, (filename, issue_count) in spaces.items():
            definition = json.loads((PACKAGE / 'app/config' / filename).read_text(encoding='utf-8'))
            version = call('score_offer.py', '--issue-space', space, '--version')
            assert version['issue_count'] == issue_count, version
            choices = {issue['name']: defaults.get(issue['name'], issue.get('min'))
                       if issue['kind'] == 'continuous' else issue['options'][-1]['label']
                       for issue in definition['issues'] if issue['name'] in definition['required_issues']}
            for role in ('Candidate', 'Recruiter'):
                response = call('score_offer.py', '--issue-space', space, '--role', role,
                                '--choices-json', json.dumps(choices), '--json')
                assert response['decision'] == 'scorable', response
                assert response['model'] == 'deterministic' and response['scorer_routing']['calls'] == 0, response
                assert set(response['valid_pairs']) == set(choices), response
                assert math.isfinite(response['total_for_proposer']), response

        tutorial = {'Venue fee': 300, 'Event date': '2027-09-15', 'Closing time': '9:00 p.m.'}
        for role in ('Candidate', 'Recruiter'):
            response = call('score_tutorial_offer.py', '--role', role,
                            '--choices-json', json.dumps(tutorial), '--json')
            assert response['decision'] == 'scorable' and response['scenario_id'].startswith('community-'), response

        for literal in ('2026-02-29', '2026-02-30', '2026-04-31'):
            choices = {'Salary': 25000, 'Personal Budget': 19000, 'Starting Date': literal}
            response = call('score_offer.py', '--issue-space', '215',
                            '--choices-json', json.dumps(choices), '--json')
            assert response['decision'] != 'scorable' and response['total_for_proposer'] is None, response
            assert not response.get('error'), response

        for role, expected in [('Candidate', 1 + 2/3 - .4), ('Recruiter', 1 - 2/3 + .4)]:
            choices = {'Salary': 55000, 'Personal Budget': 9000, 'Starting Date': '2026-01-01'}
            response = call('score_offer.py', '--scenario-file', str(PACKAGE / 'flexible-215.json'),
                            '--role', role, '--choices-json', json.dumps(choices), '--json')
            assert response['decision'] == 'scorable', response
            assert math.isclose(response['total_for_proposer'], expected, abs_tol=1e-9), response
            choices['Starting Date'] = '2026-10-01'
            response = call('score_offer.py', '--issue-space', '215', '--role', role,
                            '--choices-json', json.dumps(choices), '--json')
            assert response['decision'] == 'scorable' and response['total_for_proposer'] < -999, response

    print(f'PASS: {count} offline command-line checks. Main and tutorial scorers, both roles, '
          'all five bundled issue spaces, external 215 JSON, invalid dates, and September deadline. '
          'No sibling repository files, API keys, or model calls required.')


if __name__ == '__main__':
    main()
